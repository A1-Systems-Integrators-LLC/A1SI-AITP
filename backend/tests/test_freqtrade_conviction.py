"""Tests for Freqtrade strategy conviction system integration (IEB Phase 5).

Covers:
- _conviction_helpers module (fetch_signal, check_conviction, etc.)
- bot_loop_start signal caching
- confirm_trade_entry conviction gate
- custom_stake_amount position scaling
- custom_exit exit advisor
- custom_stoploss regime-aware tightening
- Backtest/hyperopt mode skipping
- Fail-open behavior
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure freqtrade strategies are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "freqtrade" / "user_data" / "strategies"))

import _conviction_helpers as helpers  # noqa: I001
from BollingerMeanReversion import BollingerMeanReversion
from CryptoInvestorV1 import CryptoInvestorV1
from VolatilityBreakout import VolatilityBreakout


# ── Fixtures ──────────────────────────────────────────────────────


def _make_strategy(cls):
    """Create a strategy instance with mocked dp."""
    strategy = cls.__new__(cls)
    strategy.dp = MagicMock()
    strategy.dp.runmode = None
    strategy.dp.current_whitelist.return_value = ["BTC/USDT", "ETH/USDT"]
    strategy.dp.get_analyzed_dataframe.return_value = (pd.DataFrame(), None)
    return strategy


def _signal_response(approved=True, score=75.0, modifier=1.0, label="strong_buy"):
    """Build a mock entry-check API response."""
    return {
        "approved": approved,
        "score": score,
        "position_modifier": modifier,
        "reasoning": ["test reason"],
        "signal_label": label,
        "hard_disabled": False,
    }


# ── _conviction_helpers.fetch_signal ──────────────────────────────


class TestFetchSignal:
    @patch("requests.post")
    def test_fetch_signal_success(self, mock_post):
        resp = _signal_response()
        mock_post.return_value = MagicMock(status_code=200, json=MagicMock(return_value=resp))
        result = helpers.fetch_signal("http://localhost:8000", "BTC/USDT", "CryptoInvestorV1")
        assert result == resp
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "BTC-USDT" in call_args[0][0]
        assert call_args[1]["json"]["strategy"] == "CryptoInvestorV1"

    @patch("requests.post")
    def test_fetch_signal_non_200(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        result = helpers.fetch_signal("http://localhost:8000", "BTC/USDT", "Test")
        assert result is None

    @patch("requests.post", side_effect=ConnectionError("refused"))
    def test_fetch_signal_exception(self, mock_post):
        result = helpers.fetch_signal("http://localhost:8000", "BTC/USDT", "Test")
        assert result is None

    @patch("requests.post", side_effect=TimeoutError("timeout"))
    def test_fetch_signal_timeout(self, mock_post):
        result = helpers.fetch_signal("http://localhost:8000", "BTC/USDT", "Test")
        assert result is None


# ── _conviction_helpers.check_conviction ──────────────────────────


class TestCheckConviction:
    @pytest.fixture(autouse=True)
    def _skip_pause_check(self):
        with patch.object(helpers, "check_strategy_paused", return_value=False):
            yield

    def test_approved_from_cache(self):
        strategy = MagicMock()
        strategy._signals = {"BTC/USDT": _signal_response(approved=True, score=80)}
        assert helpers.check_conviction(strategy, "BTC/USDT") is True

    def test_rejected_from_cache(self):
        strategy = MagicMock()
        strategy._signals = {"BTC/USDT": _signal_response(approved=False, score=30)}
        assert helpers.check_conviction(strategy, "BTC/USDT") is False

    @patch("_conviction_helpers.fetch_signal", return_value=None)
    def test_failopen_no_signal(self, mock_fetch):
        strategy = MagicMock()
        strategy._signals = {}
        strategy.risk_api_url = "http://localhost:8000"
        strategy.__class__.__name__ = "CryptoInvestorV1"
        assert helpers.check_conviction(strategy, "BTC/USDT") is True

    @patch("_conviction_helpers.fetch_signal")
    def test_fetches_when_not_cached(self, mock_fetch):
        mock_fetch.return_value = _signal_response(approved=True, score=70)
        strategy = MagicMock()
        strategy._signals = {}
        strategy.risk_api_url = "http://localhost:8000"
        strategy.__class__.__name__ = "CryptoInvestorV1"
        assert helpers.check_conviction(strategy, "BTC/USDT") is True
        mock_fetch.assert_called_once()


# ── _conviction_helpers.get_position_modifier ─────────────────────


class TestGetPositionModifier:
    def test_returns_modifier_from_signal(self):
        strategy = MagicMock()
        strategy._signals = {"BTC/USDT": _signal_response(modifier=0.7)}
        assert helpers.get_position_modifier(strategy, "BTC/USDT") == 0.7

    def test_returns_1_when_no_signal(self):
        strategy = MagicMock()
        strategy._signals = {}
        assert helpers.get_position_modifier(strategy, "BTC/USDT") == 1.0

    def test_returns_1_when_no_cache(self):
        strategy = MagicMock(spec=[])
        assert helpers.get_position_modifier(strategy, "BTC/USDT") == 1.0


# ── _conviction_helpers.refresh_signals ───────────────────────────


class TestRefreshSignals:
    @patch("_conviction_helpers.fetch_signal")
    def test_refreshes_all_pairs(self, mock_fetch):
        mock_fetch.return_value = _signal_response()
        strategy = _make_strategy(CryptoInvestorV1)
        from freqtrade.enums import RunMode
        strategy.dp.runmode = RunMode.DRY_RUN

        helpers.refresh_signals(strategy)

        assert mock_fetch.call_count == 2  # BTC + ETH
        assert "BTC/USDT" in strategy._signals
        assert "ETH/USDT" in strategy._signals

    def test_skips_in_backtest_mode(self):
        strategy = _make_strategy(CryptoInvestorV1)
        from freqtrade.enums import RunMode
        strategy.dp.runmode = RunMode.BACKTEST

        helpers.refresh_signals(strategy)
        assert not hasattr(strategy, "_signals")

    def test_skips_in_hyperopt_mode(self):
        strategy = _make_strategy(CryptoInvestorV1)
        from freqtrade.enums import RunMode
        strategy.dp.runmode = RunMode.HYPEROPT

        helpers.refresh_signals(strategy)
        assert not hasattr(strategy, "_signals")

    @patch("_conviction_helpers.fetch_signal")
    def test_throttles_refresh(self, mock_fetch):
        mock_fetch.return_value = _signal_response()
        strategy = _make_strategy(CryptoInvestorV1)
        from freqtrade.enums import RunMode
        strategy.dp.runmode = RunMode.DRY_RUN

        # First call — fetches
        helpers.refresh_signals(strategy)
        first_count = mock_fetch.call_count

        # Second call within 5 min — skipped
        helpers.refresh_signals(strategy)
        assert mock_fetch.call_count == first_count

    @patch("_conviction_helpers.fetch_signal", return_value=None)
    def test_handles_fetch_failure(self, mock_fetch):
        strategy = _make_strategy(CryptoInvestorV1)
        from freqtrade.enums import RunMode
        strategy.dp.runmode = RunMode.DRY_RUN

        helpers.refresh_signals(strategy)
        assert strategy._signals == {}


# ── _conviction_helpers.record_entry_regime ───────────────────────


class TestRecordEntryRegime:
    def test_records_from_cached_regime(self):
        if not helpers.HAS_CONVICTION:
            pytest.skip("Conviction modules not available")

        from common.regime.regime_detector import Regime, RegimeState

        strategy = _make_strategy(CryptoInvestorV1)
        state = RegimeState(
            regime=Regime.WEAK_TREND_UP,
            confidence=0.8,
            adx_value=30,
            bb_width_percentile=50,
            ema_slope=0.01,
            trend_alignment=0.5,
            price_structure_score=0.3,
        )
        strategy._current_regimes = {"BTC/USDT": state}

        helpers.record_entry_regime(strategy, "BTC/USDT")
        assert strategy._entry_regimes["BTC/USDT"] == "weak_trend_up"

    def test_noop_without_conviction(self):
        with patch.object(helpers, "HAS_CONVICTION", False):
            strategy = _make_strategy(CryptoInvestorV1)
            helpers.record_entry_regime(strategy, "BTC/USDT")
            assert not hasattr(strategy, "_entry_regimes")


# ── _conviction_helpers.check_exit_advice ─────────────────────────


class TestCheckExitAdvice:
    def test_returns_none_without_conviction(self):
        with patch.object(helpers, "HAS_CONVICTION", False):
            strategy = _make_strategy(CryptoInvestorV1)
            result = helpers.check_exit_advice(
                strategy, "BTC/USDT", MagicMock(),
                datetime.now(tz=timezone.utc), 0.05,
            )
            assert result is None

    def test_returns_none_without_entry_regime(self):
        strategy = _make_strategy(CryptoInvestorV1)
        strategy._entry_regimes = {}
        result = helpers.check_exit_advice(
            strategy, "BTC/USDT", MagicMock(),
            datetime.now(tz=timezone.utc), 0.05,
        )
        assert result is None

    def test_calls_advise_exit(self):
        if not helpers.HAS_CONVICTION:
            pytest.skip("Conviction modules not available")

        from common.regime.regime_detector import Regime, RegimeState
        from common.signals.exit_manager import ExitAdvice

        strategy = _make_strategy(CryptoInvestorV1)
        strategy._entry_regimes = {"BTC/USDT": "strong_trend_up"}

        state = RegimeState(
            regime=Regime.STRONG_TREND_DOWN,
            confidence=0.9,
            adx_value=45,
            bb_width_percentile=80,
            ema_slope=-0.02,
            trend_alignment=-0.8,
            price_structure_score=-0.5,
        )
        strategy._current_regimes = {"BTC/USDT": state}

        trade = MagicMock()
        trade.open_date_utc = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        with patch("_conviction_helpers.advise_exit") as mock_advise:
            mock_advise.return_value = ExitAdvice(
                should_exit=True,
                reason="regime deterioration",
                urgency="immediate",
                partial_pct=0.0,
            )
            result = helpers.check_exit_advice(
                strategy, "BTC/USDT", trade,
                datetime.now(tz=timezone.utc), 0.05,
            )
            assert result is not None
            assert "regime_deterioration" in result

    def test_returns_none_when_no_exit(self):
        if not helpers.HAS_CONVICTION:
            pytest.skip("Conviction modules not available")

        from common.regime.regime_detector import Regime, RegimeState
        from common.signals.exit_manager import ExitAdvice

        strategy = _make_strategy(CryptoInvestorV1)
        strategy._entry_regimes = {"BTC/USDT": "weak_trend_up"}

        state = RegimeState(
            regime=Regime.WEAK_TREND_UP,
            confidence=0.7,
            adx_value=28,
            bb_width_percentile=50,
            ema_slope=0.01,
            trend_alignment=0.5,
            price_structure_score=0.3,
        )
        strategy._current_regimes = {"BTC/USDT": state}

        trade = MagicMock()
        trade.open_date_utc = datetime.now(tz=timezone.utc) - timedelta(hours=1)

        with patch("_conviction_helpers.advise_exit") as mock_advise:
            mock_advise.return_value = ExitAdvice(
                should_exit=False,
                reason="monitoring",
                urgency="monitor",
                partial_pct=0.0,
            )
            result = helpers.check_exit_advice(
                strategy, "BTC/USDT", trade,
                datetime.now(tz=timezone.utc), 0.02,
            )
            assert result is None


# ── _conviction_helpers.get_regime_stop_multiplier ────────────────


class TestGetRegimeStopMultiplier:
    def test_returns_1_without_conviction(self):
        with patch.object(helpers, "HAS_CONVICTION", False):
            strategy = _make_strategy(CryptoInvestorV1)
            assert helpers.get_regime_stop_multiplier(strategy, "BTC/USDT") == 1.0

    def test_returns_multiplier_from_cached_regime(self):
        if not helpers.HAS_CONVICTION:
            pytest.skip("Conviction modules not available")

        from common.regime.regime_detector import Regime, RegimeState

        strategy = _make_strategy(CryptoInvestorV1)
        state = RegimeState(
            regime=Regime.STRONG_TREND_DOWN,
            confidence=0.9,
            adx_value=50,
            bb_width_percentile=80,
            ema_slope=-0.03,
            trend_alignment=-0.9,
            price_structure_score=-0.6,
        )
        strategy._current_regimes = {"BTC/USDT": state}

        mult = helpers.get_regime_stop_multiplier(strategy, "BTC/USDT")
        assert mult < 1.0  # Should tighten in downtrend
        assert mult == 0.55  # STRONG_TREND_DOWN → 0.55

    def test_returns_1_for_uptrend(self):
        if not helpers.HAS_CONVICTION:
            pytest.skip("Conviction modules not available")

        from common.regime.regime_detector import Regime, RegimeState

        strategy = _make_strategy(CryptoInvestorV1)
        state = RegimeState(
            regime=Regime.STRONG_TREND_UP,
            confidence=0.9,
            adx_value=50,
            bb_width_percentile=40,
            ema_slope=0.03,
            trend_alignment=0.9,
            price_structure_score=0.6,
        )
        strategy._current_regimes = {"BTC/USDT": state}

        mult = helpers.get_regime_stop_multiplier(strategy, "BTC/USDT")
        assert mult == 1.0


# ── CryptoInvestorV1 Integration ──────────────────────────────────


class TestCIV1BotLoopStart:
    @patch("CryptoInvestorV1.refresh_signals")
    def test_calls_refresh_signals(self, mock_refresh):
        strategy = _make_strategy(CryptoInvestorV1)
        strategy.bot_loop_start()
        mock_refresh.assert_called_once_with(strategy)


class TestCIV1ConfirmTradeConviction:
    def setup_method(self):
        self.strategy = _make_strategy(CryptoInvestorV1)

    @patch("CryptoInvestorV1.record_entry_regime")
    @patch("CryptoInvestorV1.check_conviction", return_value=True)
    @patch("requests.post")
    def test_both_gates_approve(self, mock_post, mock_conv, mock_regime):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        mock_post.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value={"approved": True}),
        )
        result = self.strategy.confirm_trade_entry(
            "BTC/USDT", "limit", 0.01, 50000.0, "GTC",
            datetime.now(tz=timezone.utc), None, "long",
        )
        assert result is True
        mock_conv.assert_called_once()
        mock_regime.assert_called_once()

    @patch("CryptoInvestorV1.check_conviction", return_value=False)
    @patch("requests.post")
    def test_conviction_rejects(self, mock_post, mock_conv):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        mock_post.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value={"approved": True}),
        )
        result = self.strategy.confirm_trade_entry(
            "BTC/USDT", "limit", 0.01, 50000.0, "GTC",
            datetime.now(tz=timezone.utc), None, "long",
        )
        assert result is False

    @patch("CryptoInvestorV1.record_entry_regime")
    @patch("CryptoInvestorV1.check_conviction", return_value=True)
    @patch("requests.post")
    def test_risk_rejects_before_conviction(self, mock_post, mock_conv, mock_regime):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"approved": False, "reason": "drawdown"}),
        )
        result = self.strategy.confirm_trade_entry(
            "BTC/USDT", "limit", 0.01, 50000.0, "GTC",
            datetime.now(tz=timezone.utc), None, "long",
        )
        assert result is False
        mock_conv.assert_not_called()

    @patch("CryptoInvestorV1.record_entry_regime")
    @patch("CryptoInvestorV1.check_conviction", return_value=True)
    @patch("requests.post", side_effect=ConnectionError("refused"))
    def test_risk_failopen_then_conviction(self, mock_post, mock_conv, mock_regime):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        result = self.strategy.confirm_trade_entry(
            "BTC/USDT", "limit", 0.01, 50000.0, "GTC",
            datetime.now(tz=timezone.utc), None, "long",
        )
        assert result is True
        mock_conv.assert_called_once()


class TestCIV1CustomStakeAmount:
    def setup_method(self):
        self.strategy = _make_strategy(CryptoInvestorV1)

    def test_backtest_mode_returns_proposed(self):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.BACKTEST
        result = self.strategy.custom_stake_amount(
            "BTC/USDT", datetime.now(tz=timezone.utc), 50000.0,
            100.0, 10.0, 500.0, 1.0, None, "long",
        )
        assert result == 100.0

    @patch("CryptoInvestorV1.get_position_modifier", return_value=0.7)
    def test_scales_by_modifier(self, mock_mod):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        result = self.strategy.custom_stake_amount(
            "BTC/USDT", datetime.now(tz=timezone.utc), 50000.0,
            100.0, 10.0, 500.0, 1.0, None, "long",
        )
        assert result == pytest.approx(70.0)

    @patch("CryptoInvestorV1.get_position_modifier", return_value=0.4)
    def test_clamps_to_min_stake(self, mock_mod):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        # 100 * 0.4 = 40, but min_stake = 50
        result = self.strategy.custom_stake_amount(
            "BTC/USDT", datetime.now(tz=timezone.utc), 50000.0,
            100.0, 50.0, 500.0, 1.0, None, "long",
        )
        assert result == 50.0

    @patch("CryptoInvestorV1.get_position_modifier", return_value=1.0)
    def test_full_size_at_modifier_1(self, mock_mod):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        result = self.strategy.custom_stake_amount(
            "BTC/USDT", datetime.now(tz=timezone.utc), 50000.0,
            100.0, 10.0, 500.0, 1.0, None, "long",
        )
        assert result == 100.0

    @patch("CryptoInvestorV1.get_position_modifier", return_value=0.5)
    def test_handles_none_min_stake(self, mock_mod):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        result = self.strategy.custom_stake_amount(
            "BTC/USDT", datetime.now(tz=timezone.utc), 50000.0,
            100.0, None, 500.0, 1.0, None, "long",
        )
        assert result == pytest.approx(50.0)


class TestCIV1CustomExitConviction:
    def setup_method(self):
        self.strategy = _make_strategy(CryptoInvestorV1)

    @patch("CryptoInvestorV1.check_exit_advice", return_value="conviction_regime_deterioration")
    def test_exit_advisor_triggers(self, mock_exit):
        trade = MagicMock()
        trade.open_date_utc = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        result = self.strategy.custom_exit(
            "BTC/USDT", trade, datetime.now(tz=timezone.utc),
            50000.0, 0.05, False,
        )
        assert result == "conviction_regime_deterioration"

    @patch("CryptoInvestorV1.check_exit_advice", return_value=None)
    def test_falls_through_to_technical(self, mock_exit):
        """When conviction returns None, existing technical exits still work."""
        df = pd.DataFrame({"ema_21": [95.0], "ema_100": [100.0]})
        self.strategy.dp.get_analyzed_dataframe.return_value = (df, None)

        trade = MagicMock()
        trade.open_date_utc = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        result = self.strategy.custom_exit(
            "BTC/USDT", trade, datetime.now(tz=timezone.utc),
            50000.0, -0.01, False,
        )
        assert result == "trend_breakdown"


class TestCIV1CustomStoplossRegime:
    def setup_method(self):
        self.strategy = _make_strategy(CryptoInvestorV1)

    @patch("CryptoInvestorV1.get_regime_stop_multiplier", return_value=0.5)
    def test_regime_tightens_stop(self, mock_mult):
        df = pd.DataFrame({"atr": [500.0]})
        self.strategy.dp.get_analyzed_dataframe.return_value = (df, None)
        result = self.strategy.custom_stoploss(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.0, False,
        )
        # ATR stop with 0.5x multiplier should be tighter
        assert result < 0

    @patch("CryptoInvestorV1.get_regime_stop_multiplier", return_value=1.0)
    def test_regime_neutral_stop(self, mock_mult):
        df = pd.DataFrame({"atr": [500.0]})
        self.strategy.dp.get_analyzed_dataframe.return_value = (df, None)
        result = self.strategy.custom_stoploss(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.0, False,
        )
        assert result < 0


# ── BollingerMeanReversion Integration ────────────────────────────


class TestBMRConviction:
    def setup_method(self):
        self.strategy = _make_strategy(BollingerMeanReversion)

    @patch("BollingerMeanReversion.refresh_signals")
    def test_bot_loop_start(self, mock_refresh):
        self.strategy.bot_loop_start()
        mock_refresh.assert_called_once_with(self.strategy)

    @patch("BollingerMeanReversion.record_entry_regime")
    @patch("BollingerMeanReversion.check_conviction", return_value=True)
    @patch("requests.post")
    def test_confirm_trade_conviction_approved(self, mock_post, mock_conv, mock_regime):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        mock_post.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value={"approved": True}),
        )
        result = self.strategy.confirm_trade_entry(
            "BTC/USDT", "limit", 0.01, 50000.0, "GTC",
            datetime.now(tz=timezone.utc), None, "long",
        )
        assert result is True

    @patch("BollingerMeanReversion.check_conviction", return_value=False)
    @patch("requests.post")
    def test_confirm_trade_conviction_rejected(self, mock_post, mock_conv):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        mock_post.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value={"approved": True}),
        )
        result = self.strategy.confirm_trade_entry(
            "BTC/USDT", "limit", 0.01, 50000.0, "GTC",
            datetime.now(tz=timezone.utc), None, "long",
        )
        assert result is False

    @patch("BollingerMeanReversion.get_position_modifier", return_value=0.7)
    def test_custom_stake_amount(self, mock_mod):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        result = self.strategy.custom_stake_amount(
            "BTC/USDT", datetime.now(tz=timezone.utc), 50000.0,
            100.0, 10.0, 500.0, 1.0, None, "long",
        )
        assert result == pytest.approx(70.0)

    @patch("BollingerMeanReversion.check_exit_advice", return_value="conviction_time_limit")
    def test_custom_exit(self, mock_exit):
        trade = MagicMock()
        trade.open_date_utc = datetime.now(tz=timezone.utc) - timedelta(hours=50)
        result = self.strategy.custom_exit(
            "BTC/USDT", trade, datetime.now(tz=timezone.utc),
            50000.0, 0.02, False,
        )
        assert result == "conviction_time_limit"

    @patch("BollingerMeanReversion.get_regime_stop_multiplier", return_value=0.65)
    def test_custom_stoploss_regime(self, mock_mult):
        df = pd.DataFrame({"atr": [500.0], "adx": [25.0]})
        self.strategy.dp.get_analyzed_dataframe.return_value = (df, None)
        result = self.strategy.custom_stoploss(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.0, False,
        )
        assert result < 0


# ── VolatilityBreakout Integration ────────────────────────────────


class TestVBConviction:
    def setup_method(self):
        self.strategy = _make_strategy(VolatilityBreakout)

    @patch("VolatilityBreakout.refresh_signals")
    def test_bot_loop_start(self, mock_refresh):
        self.strategy.bot_loop_start()
        mock_refresh.assert_called_once_with(self.strategy)

    @patch("VolatilityBreakout.record_entry_regime")
    @patch("VolatilityBreakout.check_conviction", return_value=True)
    @patch("requests.post")
    def test_confirm_trade_conviction_approved(self, mock_post, mock_conv, mock_regime):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        mock_post.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value={"approved": True}),
        )
        result = self.strategy.confirm_trade_entry(
            "BTC/USDT", "limit", 0.01, 50000.0, "GTC",
            datetime.now(tz=timezone.utc), None, "long",
        )
        assert result is True

    @patch("VolatilityBreakout.check_conviction", return_value=False)
    @patch("requests.post")
    def test_confirm_trade_conviction_rejected(self, mock_post, mock_conv):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        mock_post.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value={"approved": True}),
        )
        result = self.strategy.confirm_trade_entry(
            "BTC/USDT", "limit", 0.01, 50000.0, "GTC",
            datetime.now(tz=timezone.utc), None, "long",
        )
        assert result is False

    @patch("VolatilityBreakout.get_position_modifier", return_value=0.4)
    def test_custom_stake_amount(self, mock_mod):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        result = self.strategy.custom_stake_amount(
            "BTC/USDT", datetime.now(tz=timezone.utc), 50000.0,
            100.0, 10.0, 500.0, 1.0, None, "long",
        )
        assert result == pytest.approx(40.0)

    @patch("VolatilityBreakout.check_exit_advice", return_value="conviction_regime_deterioration")
    def test_custom_exit(self, mock_exit):
        trade = MagicMock()
        trade.open_date_utc = datetime.now(tz=timezone.utc) - timedelta(hours=80)
        result = self.strategy.custom_exit(
            "BTC/USDT", trade, datetime.now(tz=timezone.utc),
            50000.0, 0.03, False,
        )
        assert result == "conviction_regime_deterioration"

    @patch("VolatilityBreakout.get_regime_stop_multiplier", return_value=0.7)
    def test_custom_stoploss_regime(self, mock_mult):
        df = pd.DataFrame({"atr": [500.0]})
        self.strategy.dp.get_analyzed_dataframe.return_value = (df, None)
        result = self.strategy.custom_stoploss(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.0, False,
        )
        assert result < 0


# ── Cross-strategy metadata tests ────────────────────────────────


class TestAllStrategiesHaveConviction:
    """Verify all 3 strategies have the conviction hooks."""

    @pytest.mark.parametrize("cls", [CryptoInvestorV1, BollingerMeanReversion, VolatilityBreakout])
    def test_has_bot_loop_start(self, cls):
        assert hasattr(cls, "bot_loop_start")

    @pytest.mark.parametrize("cls", [CryptoInvestorV1, BollingerMeanReversion, VolatilityBreakout])
    def test_has_custom_stake_amount(self, cls):
        assert hasattr(cls, "custom_stake_amount")

    @pytest.mark.parametrize("cls", [CryptoInvestorV1, BollingerMeanReversion, VolatilityBreakout])
    def test_has_custom_exit(self, cls):
        assert hasattr(cls, "custom_exit")

    @pytest.mark.parametrize("cls", [CryptoInvestorV1, BollingerMeanReversion, VolatilityBreakout])
    def test_has_custom_stoploss(self, cls):
        assert hasattr(cls, "custom_stoploss")
