"""Tests for funding rate signal integration."""

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestFundingRateScoring:
    def test_positive_rate_bearish(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        # High positive funding rate = overleveraged longs = bearish
        mock_df = pd.DataFrame({"funding_rate": [0.001]})
        with patch("common.data_pipeline.pipeline.load_funding_rates", return_value=mock_df):
            score = agg._score_funding_rate("BTC/USDT")
            assert score is not None
            assert score < 50  # Bearish

    def test_negative_rate_bullish(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        mock_df = pd.DataFrame({"funding_rate": [-0.001]})
        with patch("common.data_pipeline.pipeline.load_funding_rates", return_value=mock_df):
            score = agg._score_funding_rate("BTC/USDT")
            assert score is not None
            assert score > 50  # Bullish

    def test_zero_rate_neutral(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        mock_df = pd.DataFrame({"funding_rate": [0.0]})
        with patch("common.data_pipeline.pipeline.load_funding_rates", return_value=mock_df):
            score = agg._score_funding_rate("BTC/USDT")
            assert score == 50.0

    def test_empty_data_returns_none(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        with patch("common.data_pipeline.pipeline.load_funding_rates", return_value=pd.DataFrame()):
            score = agg._score_funding_rate("BTC/USDT")
            assert score is None

    def test_no_data_returns_none(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        with patch("common.data_pipeline.pipeline.load_funding_rates", return_value=None):
            score = agg._score_funding_rate("BTC/USDT")
            assert score is None

    def test_extreme_positive_rate_clamped(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        # Extremely high positive rate should clamp to 0
        mock_df = pd.DataFrame({"funding_rate": [0.01]})
        with patch("common.data_pipeline.pipeline.load_funding_rates", return_value=mock_df):
            score = agg._score_funding_rate("BTC/USDT")
            assert score == 0  # Clamped at 0

    def test_extreme_negative_rate_clamped(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        # Extremely high negative rate should clamp to 100
        mock_df = pd.DataFrame({"funding_rate": [-0.01]})
        with patch("common.data_pipeline.pipeline.load_funding_rates", return_value=mock_df):
            score = agg._score_funding_rate("BTC/USDT")
            assert score == 100  # Clamped at 100

    def test_import_error_returns_none(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        with patch(
            "common.data_pipeline.pipeline.load_funding_rates",
            side_effect=ImportError("no module"),
        ):
            score = agg._score_funding_rate("BTC/USDT")
            assert score is None

    def test_non_crypto_skips_funding(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        # Funding rate source should not appear for equity
        result = agg.compute(
            symbol="AAPL",
            asset_class="equity",
            strategy_name="EquityMomentum",
            technical_score=60.0,
        )
        assert "funding" not in result.sources_available

    def test_crypto_includes_funding_when_available(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        mock_df = pd.DataFrame({"funding_rate": [0.0005]})
        with patch("common.data_pipeline.pipeline.load_funding_rates", return_value=mock_df):
            result = agg.compute(
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy_name="CryptoInvestorV1",
                technical_score=60.0,
            )
            assert "funding" in result.sources_available

    def test_crypto_no_funding_data_excludes_source(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        with patch("common.data_pipeline.pipeline.load_funding_rates", return_value=None):
            result = agg.compute(
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy_name="CryptoInvestorV1",
                technical_score=60.0,
            )
            assert "funding" not in result.sources_available


class TestFundingRateConstants:
    def test_funding_weight_in_defaults(self):
        from common.signals.constants import DEFAULT_WEIGHTS

        assert "funding" in DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["funding"] == 0.05


@pytest.mark.django_db
class TestFundingRateScheduledTask:
    def test_task_in_settings(self):
        from django.conf import settings

        assert "funding_rate_refresh" in settings.SCHEDULED_TASKS
        task = settings.SCHEDULED_TASKS["funding_rate_refresh"]
        assert task["task_type"] == "funding_rate_refresh"
        assert task["interval_seconds"] == 28800

    def test_executor_in_registry(self):
        from core.services.task_registry import TASK_REGISTRY

        assert "funding_rate_refresh" in TASK_REGISTRY

    def test_executor_empty_watchlist(self):
        from core.services.task_registry import TASK_REGISTRY

        executor = TASK_REGISTRY["funding_rate_refresh"]
        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch("core.platform_bridge.get_platform_config", return_value={"data": {}}),
        ):
            result = executor({}, lambda p, m: None)
            assert result["status"] == "skipped"

    def test_executor_fetches_rates(self):
        from core.services.task_registry import TASK_REGISTRY

        executor = TASK_REGISTRY["funding_rate_refresh"]
        mock_rates = pd.DataFrame({"funding_rate": [0.001], "timestamp": [1710000000]})

        with patch("core.platform_bridge.ensure_platform_imports"), patch(
            "core.platform_bridge.get_platform_config",
            return_value={"data": {"watchlist": ["BTC/USDT", "ETH/USDT"]}},
        ), patch(
            "common.data_pipeline.pipeline.fetch_funding_rates",
            return_value=mock_rates,
        ), patch("common.data_pipeline.pipeline.save_funding_rates"):
            result = executor({}, lambda p, m: None)
            assert result["status"] == "completed"
            assert result["fetched"] == 2
            assert result["total"] == 2
