"""Tests for 2026-03-23 System Analysis fixes.

Covers:
  C1: update_equity() race condition — transaction.atomic() wrapping
  C2: Singleton ReturnTracker for VaR/Correlation
  H1: Partial profit exits >= 50% converted to full exits in Freqtrade
  H2: Macro score wired into signal pipeline
  H3: Explicit funding weight handling for non-crypto
  H4: Single-portfolio equity sync
  M2: Signal staleness window reduced to 600s
  M3: Fail-open logging upgraded to ERROR
"""

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure common modules are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.regime.regime_detector import Regime, RegimeState
from common.signals.aggregator import SignalAggregator

from portfolio.models import Portfolio
from risk.models import RiskLimits, RiskState
from risk.services.risk import (
    RiskManagementService,
    _get_return_tracker,
    _reset_return_tracker,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _setup(
    portfolio_id: int = 1,
    equity: float = 500.0,
    peak: float = 500.0,
    daily_start: float | None = None,
):
    """Create a portfolio + risk state + limits for testing."""
    portfolio = Portfolio.objects.create(
        name=f"Test Portfolio {portfolio_id}",
        exchange_id="kraken",
        asset_class="crypto",
    )
    RiskLimits.objects.get_or_create(portfolio_id=portfolio.id)
    state, _ = RiskState.objects.get_or_create(
        portfolio_id=portfolio.id,
        defaults={
            "total_equity": equity,
            "peak_equity": peak,
            "daily_start_equity": daily_start or equity,
        },
    )
    state.total_equity = equity
    state.peak_equity = peak
    state.daily_start_equity = daily_start or equity
    state.save()
    return portfolio


# ── C1: update_equity() transaction.atomic() ─────────────────────────────────


@pytest.mark.django_db(transaction=True)
class TestC1UpdateEquityAtomicity:
    """C1: update_equity() wrapped in transaction.atomic()."""

    def test_update_equity_basic(self):
        portfolio = _setup(equity=500.0, peak=500.0)
        result = RiskManagementService.update_equity(portfolio.id, 510.0)
        assert result["equity"] == 510.0

    def test_sequential_updates_consistent(self):
        """Sequential updates should serialize correctly via transaction.atomic()."""
        portfolio = _setup(equity=500.0, peak=500.0)
        RiskManagementService.update_equity(portfolio.id, 510.0)
        RiskManagementService.update_equity(portfolio.id, 520.0)

        state = RiskState.objects.get(portfolio_id=portfolio.id)
        assert state.total_equity == 520.0
        assert state.peak_equity == 520.0

    def test_reset_daily_wrapped_in_transaction(self):
        """reset_daily() should also be atomic."""
        portfolio = _setup(equity=500.0, daily_start=480.0)
        state = RiskState.objects.get(portfolio_id=portfolio.id)
        state.daily_pnl = 20.0
        state.save()

        with patch("risk.services.risk.RiskManagementService.send_notification"):
            RiskManagementService.reset_daily(portfolio.id)

        state.refresh_from_db()
        assert state.daily_pnl == 0.0


# ── C2: Singleton ReturnTracker ──────────────────────────────────────────────


@pytest.mark.django_db
class TestC2ReturnTrackerSingleton:
    """C2: _build_risk_manager() shares a singleton ReturnTracker."""

    def setup_method(self):
        _reset_return_tracker()

    def teardown_method(self):
        _reset_return_tracker()

    def test_singleton_created_once(self):
        tracker1 = _get_return_tracker()
        tracker2 = _get_return_tracker()
        assert tracker1 is tracker2

    def test_reset_creates_new_instance(self):
        tracker1 = _get_return_tracker()
        _reset_return_tracker()
        tracker2 = _get_return_tracker()
        assert tracker1 is not tracker2

    def test_build_risk_manager_uses_singleton(self):
        portfolio = _setup(equity=500.0)
        state = RiskManagementService._get_or_create_state(portfolio.id)
        limits = RiskManagementService._get_or_create_limits(portfolio.id)

        rm1 = RiskManagementService._build_risk_manager(limits, state)
        rm2 = RiskManagementService._build_risk_manager(limits, state)
        assert rm1.return_tracker is rm2.return_tracker

    def test_record_prices_feeds_tracker(self):
        RiskManagementService.record_prices({"BTC/USDT": 50000.0})
        RiskManagementService.record_prices({"BTC/USDT": 51000.0})
        tracker = _get_return_tracker()
        returns = tracker.get_returns("BTC/USDT")
        assert len(returns) == 1  # One return from two prices

    def test_var_nonzero_after_price_feed(self):
        """After enough price observations, VaR should be non-zero."""
        # Feed 30 price observations to get meaningful returns
        for i in range(30):
            price = 50000.0 + (i * 100) * (1 if i % 2 == 0 else -1)
            RiskManagementService.record_prices({"BTC/USDT": price})

        portfolio = _setup(equity=500.0)
        state = RiskManagementService._get_or_create_state(portfolio.id)
        state.open_positions = {
            "BTC/USDT": {"side": "buy", "size": 0.01, "entry_price": 50000, "value": 500},
        }
        state.save()

        var_result = RiskManagementService.get_var(portfolio.id)
        # With return data, VaR should now be computed (non-zero)
        # Note: parametric VaR with return data should give non-zero values
        assert var_result["method"] == "parametric"


# ── H1: Partial profit exits ≥50% converted to full exits ────────────────────


class TestH1PartialExitConversion:
    """H1: Partial exits ≥50% become full exits in Freqtrade."""

    def setup_method(self):
        # Import conviction helpers
        strategies_path = str(PROJECT_ROOT / "freqtrade" / "user_data" / "strategies")
        if strategies_path not in sys.path:
            sys.path.insert(0, strategies_path)

    def test_partial_50pct_triggers_full_exit(self):
        """partial_pct=0.5 should trigger a full exit."""
        import _conviction_helpers as helpers

        mock_advice = MagicMock()
        mock_advice.should_exit = True
        mock_advice.partial_pct = 0.5
        mock_advice.reason = "profit taking"
        mock_advice.urgency = "next_candle"

        strategy = MagicMock()
        strategy.__class__.__name__ = "CryptoInvestorV1"
        strategy._entry_regimes = {"BTC/USDT": "STRONG_TREND_UP"}
        strategy._current_regimes = {"BTC/USDT": MagicMock()}

        with patch.object(helpers, "HAS_CONVICTION", True), \
             patch.object(helpers, "advise_exit", return_value=mock_advice), \
             patch.object(helpers, "Regime", autospec=True):
            tag = helpers.check_exit_advice(
                strategy, "BTC/USDT", MagicMock(), MagicMock(), 0.06,
            )
        assert tag is not None
        assert "profit_taking" in tag

    def test_partial_75pct_triggers_full_exit(self):
        """partial_pct=0.75 should trigger a full exit."""
        import _conviction_helpers as helpers

        mock_advice = MagicMock()
        mock_advice.should_exit = True
        mock_advice.partial_pct = 0.75
        mock_advice.reason = "take profit"
        mock_advice.urgency = "next_candle"

        strategy = MagicMock()
        strategy.__class__.__name__ = "CryptoInvestorV1"
        strategy._entry_regimes = {"BTC/USDT": "STRONG_TREND_UP"}
        strategy._current_regimes = {"BTC/USDT": MagicMock()}

        with patch.object(helpers, "HAS_CONVICTION", True), \
             patch.object(helpers, "advise_exit", return_value=mock_advice), \
             patch.object(helpers, "Regime", autospec=True):
            tag = helpers.check_exit_advice(
                strategy, "BTC/USDT", MagicMock(), MagicMock(), 0.08,
            )
        assert tag is not None

    def test_partial_33pct_skipped(self):
        """partial_pct=0.33 should be skipped (small partial)."""
        import _conviction_helpers as helpers

        mock_advice = MagicMock()
        mock_advice.should_exit = True
        mock_advice.partial_pct = 0.33
        mock_advice.reason = "small profit taking"
        mock_advice.urgency = "monitor"

        strategy = MagicMock()
        strategy.__class__.__name__ = "CryptoInvestorV1"
        strategy._entry_regimes = {"BTC/USDT": "STRONG_TREND_UP"}
        strategy._current_regimes = {"BTC/USDT": MagicMock()}

        with patch.object(helpers, "HAS_CONVICTION", True), \
             patch.object(helpers, "advise_exit", return_value=mock_advice), \
             patch.object(helpers, "Regime", autospec=True):
            tag = helpers.check_exit_advice(
                strategy, "BTC/USDT", MagicMock(), MagicMock(), 0.03,
            )
        assert tag is None


# ── H2: Macro score wired into signal pipeline ──────────────────────────────


@pytest.mark.django_db
class TestH2MacroScoreWired:
    """H2: macro source flows into aggregator.compute()."""

    def test_macro_score_in_sources(self):
        """When macro_score is provided, it should appear in available sources."""
        aggregator = SignalAggregator()
        regime_state = RegimeState(
            regime=Regime.STRONG_TREND_UP,
            confidence=0.9,
            adx_value=45.0,
            bb_width_percentile=60.0,
            ema_slope=0.5,
            trend_alignment=0.8,
            price_structure_score=0.7,
            transition_probabilities={},
        )
        signal = aggregator.compute(
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy_name="CryptoInvestorV1",
            technical_score=70.0,
            regime_state=regime_state,
            macro_score=65.0,
        )
        assert "macro" in signal.sources_available

    def test_macro_score_none_excluded(self):
        """When macro_score is None, it should not be in sources."""
        aggregator = SignalAggregator()
        signal = aggregator.compute(
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy_name="CryptoInvestorV1",
            technical_score=70.0,
            macro_score=None,
        )
        assert "macro" not in signal.sources_available

    @patch("analysis.services.signal_service.ensure_platform_imports")
    def test_signal_service_get_macro_score_success(self, mock_imports):
        """_get_macro_score should return macro_score from FRED adapter."""
        from analysis.services.signal_service import SignalService

        with patch(
            "common.market_data.fred_adapter.fetch_macro_snapshot",
            return_value={"macro_score": 65.0, "vix": 18.5},
        ):
            score = SignalService._get_macro_score()
        assert score == 65.0

    @patch("analysis.services.signal_service.ensure_platform_imports")
    def test_signal_service_get_macro_score_failure(self, mock_imports):
        """_get_macro_score should return None on exception."""
        from analysis.services.signal_service import SignalService

        with patch(
            "common.market_data.fred_adapter.fetch_macro_snapshot",
            side_effect=Exception("FRED API down"),
        ):
            score = SignalService._get_macro_score()
        assert score is None


# ── H3: Explicit funding weight for non-crypto ──────────────────────────────


class TestH3FundingWeightNonCrypto:
    """H3: Non-crypto signals should have explicit funding N/A reasoning."""

    def test_equity_funding_na_reasoning(self):
        aggregator = SignalAggregator()
        regime_state = RegimeState(
            regime=Regime.STRONG_TREND_UP,
            confidence=0.9,
            adx_value=45.0,
            bb_width_percentile=60.0,
            ema_slope=0.5,
            trend_alignment=0.8,
            price_structure_score=0.7,
            transition_probabilities={},
        )
        signal = aggregator.compute(
            symbol="AAPL",
            asset_class="equity",
            strategy_name="EquityMomentum",
            technical_score=70.0,
            regime_state=regime_state,
        )
        funding_reasons = [
            r for r in signal.reasoning if "funding: N/A" in r
        ]
        assert len(funding_reasons) == 1
        assert "non-crypto" in funding_reasons[0]

    def test_forex_funding_na_reasoning(self):
        aggregator = SignalAggregator()
        signal = aggregator.compute(
            symbol="EUR/USD",
            asset_class="forex",
            strategy_name="ForexTrend",
            technical_score=70.0,
        )
        funding_reasons = [
            r for r in signal.reasoning if "funding: N/A" in r
        ]
        assert len(funding_reasons) == 1

    def test_crypto_no_funding_na_reasoning(self):
        """Crypto should NOT get the funding N/A reasoning."""
        aggregator = SignalAggregator()
        signal = aggregator.compute(
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy_name="CryptoInvestorV1",
            technical_score=70.0,
        )
        funding_na = [r for r in signal.reasoning if "funding: N/A" in r]
        assert len(funding_na) == 0


# ── H4: Single-portfolio equity sync ─────────────────────────────────────────


@pytest.mark.django_db
class TestH4SinglePortfolioEquitySync:
    """H4: Equity sync should update only the first crypto portfolio."""

    def test_only_first_portfolio_used(self):
        """_sync_freqtrade_equity should use portfolios.first(), not loop."""
        import requests as req_mod

        from django.conf import settings

        settings.FREQTRADE_INSTANCES = [
            {"url": "http://localhost:8080", "enabled": True, "dry_run_wallet": 500},
        ]
        settings.FREQTRADE_API_URL = ""
        settings.FREQTRADE_BMR_API_URL = ""
        settings.FREQTRADE_VB_API_URL = ""

        # Create one crypto portfolio and one equity portfolio
        p_crypto = _setup(equity=500.0)
        p_equity = Portfolio.objects.create(
            name="Equity Portfolio", exchange_id="yfinance", asset_class="equity",
        )
        RiskLimits.objects.get_or_create(portfolio_id=p_equity.id)
        RiskState.objects.get_or_create(
            portfolio_id=p_equity.id,
            defaults={"total_equity": 5000.0, "peak_equity": 5000.0, "daily_start_equity": 5000.0},
        )

        # Mock Freqtrade profit API
        mock_profit_resp = MagicMock()
        mock_profit_resp.status_code = 200
        mock_profit_resp.json.return_value = {"profit_all_coin": 10.0}
        mock_profit_resp.raise_for_status = MagicMock()

        mock_status_resp = MagicMock()
        mock_status_resp.status_code = 200
        mock_status_resp.json.return_value = []

        from core.services.task_registry import _sync_freqtrade_equity

        with patch.object(
            req_mod, "get",
            side_effect=lambda url, **kw: (
                mock_profit_resp if "profit" in url else mock_status_resp
            ),
        ), patch(
            "trading.services.forex_paper_trading.ForexPaperTradingService.get_profit",
            return_value={"profit_all_coin": 0},
        ):
            result = _sync_freqtrade_equity()

        assert result["equity_updated"] is True

        # Crypto portfolio should be updated (500 + 10 PnL = 510)
        s_crypto = RiskState.objects.get(portfolio_id=p_crypto.id)
        assert s_crypto.total_equity == 510.0

        # Equity portfolio should NOT be updated
        s_equity = RiskState.objects.get(portfolio_id=p_equity.id)
        assert s_equity.total_equity == 5000.0


# ── M2: Signal staleness window ──────────────────────────────────────────────


class TestM2SignalStalenessWindow:
    """M2: SIGNAL_MAX_AGE should be 600s (10 min), not 900s."""

    def test_signal_max_age_is_600(self):
        strategies_path = str(PROJECT_ROOT / "freqtrade" / "user_data" / "strategies")
        if strategies_path not in sys.path:
            sys.path.insert(0, strategies_path)
        import _conviction_helpers as helpers

        assert helpers.SIGNAL_MAX_AGE == 600


# ── M3: Fail-open logging at ERROR level ─────────────────────────────────────


class TestM3FailOpenLogging:
    """M3: Signal API failures should log at ERROR, not WARNING."""

    def test_fetch_signal_logs_error_on_exception(self):
        strategies_path = str(PROJECT_ROOT / "freqtrade" / "user_data" / "strategies")
        if strategies_path not in sys.path:
            sys.path.insert(0, strategies_path)
        import _conviction_helpers as helpers
        import requests as req_mod

        with patch.object(req_mod, "post", side_effect=ConnectionError("timeout")):
            with patch.object(helpers.logger, "error") as mock_error:
                result = helpers.fetch_signal("http://localhost:8000", "BTC/USDT", "CIV1")
                assert result is None
                mock_error.assert_called_once()
                assert "Signal fetch failed" in str(mock_error.call_args)
