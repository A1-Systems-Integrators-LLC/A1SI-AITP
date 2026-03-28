"""Tests for funding rate signal integration."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class TestPerpetualSymbolConversion:
    """Tests for _to_perpetual_symbol helper."""

    def test_bybit_usdt_pair(self):
        from common.data_pipeline.pipeline import _to_perpetual_symbol

        assert _to_perpetual_symbol("BTC/USDT", "bybit") == "BTC/USDT:USDT"

    def test_bybit_eth_pair(self):
        from common.data_pipeline.pipeline import _to_perpetual_symbol

        assert _to_perpetual_symbol("ETH/USDT", "bybit") == "ETH/USDT:USDT"

    def test_krakenfutures_converts_to_usd(self):
        from common.data_pipeline.pipeline import _to_perpetual_symbol

        # Kraken futures perps are quoted in USD, not USDT
        assert _to_perpetual_symbol("BTC/USDT", "krakenfutures") == "BTC/USD:USD"

    def test_already_perpetual_format_unchanged(self):
        from common.data_pipeline.pipeline import _to_perpetual_symbol

        assert _to_perpetual_symbol("BTC/USDT:USDT", "bybit") == "BTC/USDT:USDT"

    def test_default_exchange_uses_quote_as_settle(self):
        from common.data_pipeline.pipeline import _to_perpetual_symbol

        assert _to_perpetual_symbol("SOL/USDC", "binance") == "SOL/USDC:USDC"


class TestFundingRateExchangeFallback:
    """Tests for fetch_funding_rates exchange fallback logic."""

    def test_default_tries_bybit_first(self):
        from common.data_pipeline.pipeline import _FUNDING_RATE_EXCHANGES

        assert _FUNDING_RATE_EXCHANGES[0] == "bybit"
        assert "krakenfutures" in _FUNDING_RATE_EXCHANGES

    def test_skips_exchange_without_support(self):
        """Exchange that doesn't support fetchFundingRateHistory is skipped."""
        from common.data_pipeline.pipeline import fetch_funding_rates

        mock_exchange = MagicMock()
        mock_exchange.has = {"fetchFundingRateHistory": False}

        with patch(
            "common.data_pipeline.pipeline.get_exchange",
            return_value=mock_exchange,
        ):
            result = fetch_funding_rates("BTC/USDT", exchange_id="kraken")
            assert result.empty
            # Should not have tried to call fetch_funding_rate_history
            mock_exchange.fetch_funding_rate_history.assert_not_called()

    def test_skips_symbol_not_in_markets(self):
        """Exchange supports funding rates but doesn't have the perpetual symbol."""
        from common.data_pipeline.pipeline import fetch_funding_rates

        mock_exchange = MagicMock()
        mock_exchange.has = {"fetchFundingRateHistory": True}
        mock_exchange.markets = {"ETH/USDT:USDT": {}}  # BTC not available

        with patch(
            "common.data_pipeline.pipeline.get_exchange",
            return_value=mock_exchange,
        ):
            result = fetch_funding_rates("BTC/USDT", exchange_id="bybit")
            assert result.empty
            mock_exchange.fetch_funding_rate_history.assert_not_called()

    def test_successful_fetch_returns_dataframe(self):
        """Successful fetch returns properly formatted DataFrame."""
        from common.data_pipeline.pipeline import fetch_funding_rates

        mock_exchange = MagicMock()
        mock_exchange.has = {"fetchFundingRateHistory": True}
        mock_exchange.markets = {"BTC/USDT:USDT": {}}
        mock_exchange.fetch_funding_rate_history.return_value = [
            {"timestamp": 1710000000000, "fundingRate": 0.0001},
            {"timestamp": 1710028800000, "fundingRate": -0.0002},
        ]

        with patch(
            "common.data_pipeline.pipeline.get_exchange",
            return_value=mock_exchange,
        ):
            result = fetch_funding_rates("BTC/USDT", exchange_id="bybit")
            assert not result.empty
            assert "funding_rate" in result.columns
            assert len(result) == 2

    def test_fallback_to_second_exchange(self):
        """If first exchange fails, tries the second one."""
        from common.data_pipeline.pipeline import fetch_funding_rates

        call_count = {"n": 0}

        def mock_get_exchange(eid, sandbox=False):
            call_count["n"] += 1
            ex = MagicMock()
            if eid == "bybit":
                # Bybit: supports but doesn't have the symbol
                ex.has = {"fetchFundingRateHistory": True}
                ex.markets = {}  # symbol not found
            else:
                # krakenfutures: has the symbol
                ex.has = {"fetchFundingRateHistory": True}
                ex.markets = {"BTC/USD:USD": {}}
                ex.fetch_funding_rate_history.return_value = [
                    {"timestamp": 1710000000000, "fundingRate": 0.0003},
                ]
            return ex

        with patch(
            "common.data_pipeline.pipeline.get_exchange",
            side_effect=mock_get_exchange,
        ):
            result = fetch_funding_rates("BTC/USDT")  # No exchange_id -> fallback
            assert not result.empty
            assert call_count["n"] == 2  # Tried both exchanges


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

    def test_executor_zero_fetched_includes_warning(self):
        """When no funding rates are fetched, result includes a warning."""
        from core.services.task_registry import TASK_REGISTRY

        executor = TASK_REGISTRY["funding_rate_refresh"]

        with patch("core.platform_bridge.ensure_platform_imports"), patch(
            "core.platform_bridge.get_platform_config",
            return_value={"data": {"watchlist": ["BTC/USDT", "ETH/USDT"]}},
        ), patch(
            "common.data_pipeline.pipeline.fetch_funding_rates",
            return_value=pd.DataFrame(),
        ):
            result = executor({}, lambda p, m: None)
            assert result["status"] == "completed"
            assert result["fetched"] == 0
            assert "warning" in result
            assert "failed_symbols" in result
            assert "BTC/USDT" in result["failed_symbols"]

    def test_executor_partial_success_reports_failed(self):
        """When some symbols fail, failed_symbols is populated."""
        from core.services.task_registry import TASK_REGISTRY

        executor = TASK_REGISTRY["funding_rate_refresh"]
        mock_rates = pd.DataFrame({"funding_rate": [0.001]})

        def mock_fetch(symbol):
            if symbol == "BTC/USDT":
                return mock_rates
            return pd.DataFrame()

        with patch("core.platform_bridge.ensure_platform_imports"), patch(
            "core.platform_bridge.get_platform_config",
            return_value={"data": {"watchlist": ["BTC/USDT", "DOGE/USDT"]}},
        ), patch(
            "common.data_pipeline.pipeline.fetch_funding_rates",
            side_effect=mock_fetch,
        ), patch("common.data_pipeline.pipeline.save_funding_rates"):
            result = executor({}, lambda p, m: None)
            assert result["status"] == "completed"
            assert result["fetched"] == 1
            assert "DOGE/USDT" in result["failed_symbols"]
            assert "BTC/USDT" not in result.get("failed_symbols", [])
