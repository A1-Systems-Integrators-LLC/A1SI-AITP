"""Tests for BTC dominance regime signal."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.market_data.coingecko import (
    clear_cache,
    fetch_btc_dominance,
    get_dominance_signal,
)


@pytest.fixture(autouse=True)
def _clean():
    clear_cache()
    yield
    clear_cache()


class TestFetchBtcDominance:
    @patch("common.market_data.coingecko.requests")
    def test_fetches_dominance(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"market_cap_percentage": {"btc": 52.3}}}
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        result = fetch_btc_dominance()
        assert result == 52.3

    @patch("common.market_data.coingecko.requests")
    def test_cache_hit(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"market_cap_percentage": {"btc": 52.3}}}
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        fetch_btc_dominance()
        fetch_btc_dominance()
        assert mock_requests.get.call_count == 1

    @patch("common.market_data.coingecko.requests")
    def test_api_failure_returns_none(self, mock_requests):
        mock_requests.get.side_effect = Exception("timeout")
        result = fetch_btc_dominance()
        assert result is None

    @patch("common.market_data.coingecko.requests")
    def test_missing_data_returns_none(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"market_cap_percentage": {}}}
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        result = fetch_btc_dominance()
        assert result is None


class TestDominanceSignal:
    def test_btc_dominant(self):
        result = get_dominance_signal(60.0)
        assert result["regime_label"] == "btc_dominant"
        assert result["modifier"] == -5

    def test_alt_season(self):
        result = get_dominance_signal(35.0)
        assert result["regime_label"] == "alt_season"
        assert result["modifier"] == 5

    def test_neutral(self):
        result = get_dominance_signal(50.0)
        assert result["regime_label"] == "neutral"
        assert result["modifier"] == 0

    def test_none_dominance(self):
        with patch("common.market_data.coingecko.fetch_btc_dominance", return_value=None):
            result = get_dominance_signal()
            assert result["regime_label"] == "unknown"
            assert result["modifier"] == 0

    def test_boundary_55(self):
        result = get_dominance_signal(55.0)
        assert result["regime_label"] == "neutral"

    def test_boundary_above_55(self):
        result = get_dominance_signal(55.1)
        assert result["regime_label"] == "btc_dominant"

    def test_boundary_40(self):
        result = get_dominance_signal(40.0)
        assert result["regime_label"] == "neutral"

    def test_boundary_below_40(self):
        result = get_dominance_signal(39.9)
        assert result["regime_label"] == "alt_season"


class TestAggregatorIntegration:
    def test_btc_dominance_applies_to_crypto(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        with patch(
            "common.market_data.coingecko.get_dominance_signal",
            return_value={"dominance": 60.0, "regime_label": "btc_dominant", "modifier": -5},
        ):
            result = agg.compute(
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy_name="CryptoInvestorV1",
                technical_score=70.0,
            )
            # Score should be reduced by 5 points from BTC dominance
            assert result.composite_score == 65.0
            assert any("BTC dominance" in r for r in result.reasoning)

    def test_btc_dominance_does_not_apply_to_equity(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        with patch("common.market_data.coingecko.get_dominance_signal") as mock_dom:
            agg.compute(
                symbol="AAPL",
                asset_class="equity",
                strategy_name="EquityMomentum",
                technical_score=70.0,
            )
            mock_dom.assert_not_called()  # noqa: F841

    def test_btc_dominance_alt_season_boosts_score(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        with patch(
            "common.market_data.coingecko.get_dominance_signal",
            return_value={"dominance": 35.0, "regime_label": "alt_season", "modifier": 5},
        ):
            result = agg.compute(
                symbol="ETH/USDT",
                asset_class="crypto",
                strategy_name="CryptoInvestorV1",
                technical_score=70.0,
            )
            assert result.composite_score == 75.0

    def test_btc_dominance_neutral_no_change(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        with patch(
            "common.market_data.coingecko.get_dominance_signal",
            return_value={"dominance": 50.0, "regime_label": "neutral", "modifier": 0},
        ):
            result = agg.compute(
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy_name="CryptoInvestorV1",
                technical_score=70.0,
            )
            assert result.composite_score == 70.0
            # No BTC dominance reasoning when modifier is 0
            assert not any("BTC dominance" in r for r in result.reasoning)

    def test_btc_dominance_failure_graceful(self):
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()

        with patch(
            "common.market_data.coingecko.get_dominance_signal",
            side_effect=Exception("API down"),
        ):
            result = agg.compute(
                symbol="BTC/USDT",
                asset_class="crypto",
                strategy_name="CryptoInvestorV1",
                technical_score=70.0,
            )
            # Should still compute without BTC dominance
            assert result.composite_score == 70.0
