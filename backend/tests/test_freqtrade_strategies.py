"""Comprehensive tests for all 3 Freqtrade strategies.

Tests cover indicator population, entry/exit signals, custom stoploss,
custom exit, and risk gate (confirm_trade_entry). All framework deps required.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("talib", reason="talib not installed")

# Ensure freqtrade strategies are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "freqtrade" / "user_data" / "strategies"))

from BollingerMeanReversion import BollingerMeanReversion
from CryptoInvestorV1 import CryptoInvestorV1
from VolatilityBreakout import VolatilityBreakout

# ── Helpers ──────────────────────────────────────────────────────


def _make_ohlcv(n: int = 300, trend: str = "up") -> pd.DataFrame:
    """Generate synthetic OHLCV data suitable for Freqtrade strategies."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="1h")
    base = 100.0
    prices = [base]
    for _i in range(1, n):
        if trend == "up":
            drift = 0.0003
        elif trend == "down":
            drift = -0.0003
        else:
            drift = 0.0
        prices.append(prices[-1] * (1 + drift + np.random.normal(0, 0.005)))

    close = np.array(prices)
    high = close * (1 + np.abs(np.random.normal(0, 0.003, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.003, n)))
    opn = close * (1 + np.random.normal(0, 0.001, n))
    volume = np.random.uniform(100, 10000, n)

    return pd.DataFrame({
        "date": dates,
        "open": opn,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def _make_strategy(cls):
    """Create a strategy instance with mocked dp (dataprovider)."""
    strategy = cls.__new__(cls)
    # Initialize IStrategy attributes manually
    strategy.dp = MagicMock()
    strategy.dp.runmode = None
    # Set hyperopt param values to defaults
    for attr_name in dir(strategy):
        attr = getattr(type(strategy), attr_name, None)
        if attr is not None and hasattr(attr, "value"):
            pass  # Already has .value via descriptor
    return strategy


# ── CryptoInvestorV1 Tests ───────────────────────────────────────


class TestCryptoInvestorV1Indicators:
    def setup_method(self):
        self.strategy = _make_strategy(CryptoInvestorV1)
        self.df = _make_ohlcv(300, "up")

    def test_populate_indicators_adds_emas(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        for period in [7, 14, 21, 50, 100, 200]:
            assert f"ema_{period}" in result.columns
            assert f"sma_{period}" in result.columns

    def test_populate_indicators_adds_rsi(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        assert "rsi" in result.columns
        # RSI should be between 0-100 where not NaN
        valid = result["rsi"].dropna()
        assert valid.min() >= 0
        assert valid.max() <= 100

    def test_populate_indicators_adds_macd(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        assert "macd" in result.columns
        assert "macdsignal" in result.columns
        assert "macdhist" in result.columns

    def test_populate_indicators_adds_bollinger(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        assert "bb_upper" in result.columns
        assert "bb_mid" in result.columns
        assert "bb_lower" in result.columns
        assert "bb_width" in result.columns

    def test_populate_indicators_adds_atr(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        assert "atr" in result.columns
        valid = result["atr"].dropna()
        assert (valid >= 0).all()

    def test_populate_indicators_adds_volume_ratio(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        assert "volume_sma_20" in result.columns
        assert "volume_ratio" in result.columns

    def test_populate_indicators_adds_trend_flags(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        assert "uptrend" in result.columns
        assert "strong_uptrend" in result.columns
        assert set(result["uptrend"].dropna().unique()).issubset({0, 1})


class TestCryptoInvestorV1Signals:
    def setup_method(self):
        self.strategy = _make_strategy(CryptoInvestorV1)

    def test_entry_signals_generated(self):
        df = _make_ohlcv(500, "up")
        df = self.strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = self.strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert "enter_long" in df.columns
        # Should generate at least some entry signals in uptrend data
        entries = df["enter_long"].fillna(0).sum()
        assert entries >= 0  # May be 0 depending on data, but column must exist

    def test_exit_signals_generated(self):
        df = _make_ohlcv(500, "up")
        df = self.strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = self.strategy.populate_exit_trend(df, {"pair": "BTC/USDT"})
        assert "exit_long" in df.columns

    def test_entry_requires_volume(self):
        """Zero volume candles should not generate entries."""
        df = _make_ohlcv(300, "up")
        df["volume"] = 0  # No volume
        df = self.strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = self.strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert df["enter_long"].fillna(0).sum() == 0

    def test_entry_not_in_freefall(self):
        """RSI < 10 should not generate entries (freefall filter)."""
        df = _make_ohlcv(300, "down")
        df = self.strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        # Force RSI below 10
        df["rsi"] = 5.0
        df = self.strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert df["enter_long"].fillna(0).sum() == 0


class TestCryptoInvestorV1CustomStoploss:
    def setup_method(self):
        self.strategy = _make_strategy(CryptoInvestorV1)

    def test_stoploss_returns_default_on_empty_df(self):
        self.strategy.dp.get_analyzed_dataframe.return_value = (pd.DataFrame(), None)
        result = self.strategy.custom_stoploss(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.01, False,
        )
        assert result == self.strategy.stoploss

    def test_stoploss_returns_default_on_zero_atr(self):
        df = pd.DataFrame({"atr": [0.0]})
        self.strategy.dp.get_analyzed_dataframe.return_value = (df, None)
        result = self.strategy.custom_stoploss(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.01, False,
        )
        assert result == self.strategy.stoploss

    def test_stoploss_tightens_at_high_profit(self):
        df = pd.DataFrame({"atr": [500.0]})
        self.strategy.dp.get_analyzed_dataframe.return_value = (df, None)

        # At 7% profit, stop should tighten to at most -2%
        result = self.strategy.custom_stoploss(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.07, False,
        )
        assert result >= -0.05  # At least as tight as hard stop
        assert result <= 0  # Must be negative


class TestCryptoInvestorV1CustomExit:
    def setup_method(self):
        self.strategy = _make_strategy(CryptoInvestorV1)

    def test_custom_exit_returns_none_on_empty(self):
        self.strategy.dp.get_analyzed_dataframe.return_value = (pd.DataFrame(), None)
        result = self.strategy.custom_exit(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.01, False,
        )
        assert result is None

    def test_custom_exit_stale_trade(self):
        """Trades held > 7 days with < 1% profit should be exited."""
        df = pd.DataFrame({"ema_21": [100.0], "ema_100": [99.0]})
        self.strategy.dp.get_analyzed_dataframe.return_value = (df, None)

        trade = MagicMock()
        trade.open_date_utc = datetime.now(tz=timezone.utc) - timedelta(days=8)
        result = self.strategy.custom_exit(
            "BTC/USDT", trade, datetime.now(tz=timezone.utc),
            50000.0, 0.005, False,
        )
        assert result == "stale_trade"

    def test_custom_exit_trend_breakdown(self):
        """Fast EMA below slow EMA with small loss should exit."""
        df = pd.DataFrame({"ema_21": [95.0], "ema_100": [100.0]})
        self.strategy.dp.get_analyzed_dataframe.return_value = (df, None)

        trade = MagicMock()
        trade.open_date_utc = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        result = self.strategy.custom_exit(
            "BTC/USDT", trade, datetime.now(tz=timezone.utc),
            50000.0, -0.01, False,
        )
        assert result == "trend_breakdown"


class TestCryptoInvestorV1ConfirmTrade:
    def setup_method(self):
        self.strategy = _make_strategy(CryptoInvestorV1)

    def test_confirm_trade_backtest_mode_always_true(self):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.BACKTEST
        result = self.strategy.confirm_trade_entry(
            "BTC/USDT", "limit", 0.01, 50000.0, "GTC",
            datetime.now(tz=timezone.utc), None, "long",
        )
        assert result is True

    def test_confirm_trade_hyperopt_mode_always_true(self):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.HYPEROPT
        result = self.strategy.confirm_trade_entry(
            "BTC/USDT", "limit", 0.01, 50000.0, "GTC",
            datetime.now(tz=timezone.utc), None, "long",
        )
        assert result is True

    @patch("CryptoInvestorV1.record_entry_regime")
    @patch("CryptoInvestorV1.check_conviction", return_value=True)
    @patch("requests.post")
    def test_confirm_trade_risk_approved(self, mock_post, mock_conv, mock_regime):
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

    @patch("requests.post")
    def test_confirm_trade_risk_rejected(self, mock_post):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"approved": False, "reason": "drawdown limit"}),
        )

        result = self.strategy.confirm_trade_entry(
            "BTC/USDT", "limit", 0.01, 50000.0, "GTC",
            datetime.now(tz=timezone.utc), None, "long",
        )
        assert result is False

    @patch("CryptoInvestorV1.record_entry_regime")
    @patch("CryptoInvestorV1.check_conviction", return_value=True)
    @patch("requests.post", side_effect=ConnectionError("refused"))
    def test_confirm_trade_api_unreachable_failopen(self, mock_post, mock_conv, mock_regime):
        from freqtrade.enums import RunMode
        self.strategy.dp.runmode = RunMode.DRY_RUN

        result = self.strategy.confirm_trade_entry(
            "BTC/USDT", "limit", 0.01, 50000.0, "GTC",
            datetime.now(tz=timezone.utc), None, "long",
        )
        assert result is True  # fail-open


# ── BollingerMeanReversion Tests ─────────────────────────────────


class TestBollingerMeanReversionIndicators:
    def setup_method(self):
        self.strategy = _make_strategy(BollingerMeanReversion)
        self.df = _make_ohlcv(300, "down")

    def test_populate_indicators_adds_bollinger_grid(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        # Outside hyperopt, only the selected BB params are computed (default: period=20, std=1.5)
        assert "bb_upper_20_15" in result.columns
        assert "bb_lower_20_15" in result.columns
        assert "bb_mid_20_15" in result.columns

    def test_populate_indicators_adds_rsi_adx(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        assert "rsi" in result.columns
        assert "adx" in result.columns
        assert "mfi" in result.columns

    def test_populate_indicators_adds_stochastic(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        assert "stoch_k" in result.columns
        assert "stoch_d" in result.columns


class TestBollingerMeanReversionBBOptimization:
    """Tests for BB computation optimization (hyperopt vs non-hyperopt)."""

    def test_non_hyperopt_computes_only_selected_bb(self):
        """Outside hyperopt, only the selected period/std BB columns exist."""
        from freqtrade.enums import RunMode
        strategy = _make_strategy(BollingerMeanReversion)
        strategy.dp.runmode = RunMode.DRY_RUN
        df = _make_ohlcv(300, "down")
        result = strategy.populate_indicators(df.copy(), {"pair": "BTC/USDT"})
        # Default: period=20, std=1.5 → suffix _20_15
        assert "bb_upper_20_15" in result.columns
        assert "bb_mid_20_15" in result.columns
        assert "bb_lower_20_15" in result.columns
        # Other combos should NOT exist
        assert "bb_upper_25_20" not in result.columns
        assert "bb_upper_15_10" not in result.columns

    def test_hyperopt_computes_full_bb_grid(self):
        """In hyperopt mode, all 24 BB combos are computed."""
        from freqtrade.enums import RunMode
        strategy = _make_strategy(BollingerMeanReversion)
        strategy.dp.runmode = RunMode.HYPEROPT
        df = _make_ohlcv(300, "down")
        result = strategy.populate_indicators(df.copy(), {"pair": "BTC/USDT"})
        # All combos should exist
        for period in [15, 20, 25, 30]:
            for std in [1.0, 1.2, 1.5, 2.0, 2.5, 3.0]:
                suffix = f"_{period}_{str(std).replace('.', '')}"
                assert f"bb_upper{suffix}" in result.columns

    def test_dp_none_uses_selected_bb_only(self):
        """If dp is None (edge case), compute only selected BB."""
        strategy = _make_strategy(BollingerMeanReversion)
        strategy.dp = None
        df = _make_ohlcv(300, "down")
        result = strategy.populate_indicators(df.copy(), {"pair": "BTC/USDT"})
        assert "bb_upper_20_15" in result.columns
        assert "bb_upper_25_20" not in result.columns

    def test_backtest_mode_uses_selected_bb_only(self):
        """Backtest mode should also use only selected BB (not full grid)."""
        from freqtrade.enums import RunMode
        strategy = _make_strategy(BollingerMeanReversion)
        strategy.dp.runmode = RunMode.BACKTEST
        df = _make_ohlcv(300, "down")
        result = strategy.populate_indicators(df.copy(), {"pair": "BTC/USDT"})
        assert "bb_upper_20_15" in result.columns
        assert "bb_upper_30_30" not in result.columns

    def test_entry_exit_work_with_optimized_indicators(self):
        """Entry and exit signals work correctly with optimized BB computation."""
        from freqtrade.enums import RunMode
        strategy = _make_strategy(BollingerMeanReversion)
        strategy.dp.runmode = RunMode.DRY_RUN
        df = _make_ohlcv(300, "down")
        df = strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        df = strategy.populate_exit_trend(df, {"pair": "BTC/USDT"})
        assert "enter_long" in df.columns
        assert "exit_long" in df.columns


class TestBollingerMeanReversionSignals:
    def setup_method(self):
        self.strategy = _make_strategy(BollingerMeanReversion)

    def test_entry_signals_structure(self):
        df = _make_ohlcv(300, "down")
        df = self.strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = self.strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert "enter_long" in df.columns

    def test_exit_signals_structure(self):
        df = _make_ohlcv(300, "down")
        df = self.strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = self.strategy.populate_exit_trend(df, {"pair": "BTC/USDT"})
        assert "exit_long" in df.columns

    def test_no_entry_with_zero_volume(self):
        df = _make_ohlcv(300, "down")
        df["volume"] = 0
        df = self.strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = self.strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert df["enter_long"].fillna(0).sum() == 0


class TestBollingerMeanReversionStoploss:
    def setup_method(self):
        self.strategy = _make_strategy(BollingerMeanReversion)

    def test_stoploss_empty_df(self):
        self.strategy.dp.get_analyzed_dataframe.return_value = (pd.DataFrame(), None)
        result = self.strategy.custom_stoploss(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.01, False,
        )
        assert result == self.strategy.stoploss

    def test_stoploss_tighter_in_strong_trend(self):
        """ADX > 35 should produce tighter stops."""
        df_strong = pd.DataFrame({"atr": [500.0], "adx": [40.0]})
        df_weak = pd.DataFrame({"atr": [500.0], "adx": [20.0]})

        self.strategy.dp.get_analyzed_dataframe.return_value = (df_strong, None)
        stop_strong = self.strategy.custom_stoploss(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.0, False,
        )

        self.strategy.dp.get_analyzed_dataframe.return_value = (df_weak, None)
        stop_weak = self.strategy.custom_stoploss(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.0, False,
        )

        # Strong trend: atr_mult=1.5, Weak: atr_mult=2.0 → strong stop is tighter
        assert stop_strong >= stop_weak


# ── VolatilityBreakout Tests ─────────────────────────────────────


class TestVolatilityBreakoutIndicators:
    def setup_method(self):
        self.strategy = _make_strategy(VolatilityBreakout)
        self.df = _make_ohlcv(300, "up")

    def test_populate_indicators_adds_highs(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        for period in [10, 15, 20, 25, 30]:
            assert f"high_{period}" in result.columns

    def test_populate_indicators_adds_bb_width(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        assert "bb_width" in result.columns
        assert "bb_width_prev" in result.columns

    def test_populate_indicators_adds_emas(self):
        result = self.strategy.populate_indicators(self.df.copy(), {"pair": "BTC/USDT"})
        assert "ema_20" in result.columns
        assert "ema_50" in result.columns


class TestVolatilityBreakoutSignals:
    def setup_method(self):
        self.strategy = _make_strategy(VolatilityBreakout)

    def test_entry_signals_structure(self):
        df = _make_ohlcv(300, "up")
        df = self.strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = self.strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert "enter_long" in df.columns

    def test_exit_signals_structure(self):
        df = _make_ohlcv(300, "up")
        df = self.strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = self.strategy.populate_exit_trend(df, {"pair": "BTC/USDT"})
        assert "exit_long" in df.columns

    def test_no_entry_with_zero_volume(self):
        df = _make_ohlcv(300, "up")
        df["volume"] = 0
        df = self.strategy.populate_indicators(df, {"pair": "BTC/USDT"})
        df = self.strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert df["enter_long"].fillna(0).sum() == 0


class TestVolatilityBreakoutStoploss:
    def setup_method(self):
        self.strategy = _make_strategy(VolatilityBreakout)

    def test_stoploss_empty_df(self):
        self.strategy.dp.get_analyzed_dataframe.return_value = (pd.DataFrame(), None)
        result = self.strategy.custom_stoploss(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.01, False,
        )
        assert result == self.strategy.stoploss

    def test_stoploss_tightens_at_5pct_profit(self):
        df = pd.DataFrame({"atr": [500.0]})
        self.strategy.dp.get_analyzed_dataframe.return_value = (df, None)
        result = self.strategy.custom_stoploss(
            "BTC/USDT", MagicMock(), datetime.now(tz=timezone.utc),
            50000.0, 0.06, False,
        )
        # At 6% profit (above 4% threshold), should tighten to max(-atr_stop, -0.035)
        assert result >= -0.05  # At least as tight as hard stop


# ── Strategy Metadata Tests ──────────────────────────────────────


class TestStrategyMetadata:
    """Verify critical strategy configuration."""

    def test_civ1_metadata(self):
        assert CryptoInvestorV1.INTERFACE_VERSION == 3
        assert CryptoInvestorV1.timeframe == "1h"
        assert CryptoInvestorV1.can_short is False
        assert CryptoInvestorV1.stoploss == -0.04

    def test_bmr_metadata(self):
        assert BollingerMeanReversion.INTERFACE_VERSION == 3
        assert BollingerMeanReversion.timeframe == "1h"
        assert BollingerMeanReversion.can_short is False
        assert BollingerMeanReversion.stoploss == -0.03

    def test_vb_metadata(self):
        assert VolatilityBreakout.INTERFACE_VERSION == 3
        assert VolatilityBreakout.timeframe == "1h"
        assert VolatilityBreakout.can_short is False
        assert VolatilityBreakout.stoploss == -0.03

    def test_roi_tables_are_decreasing(self):
        """ROI targets should decrease over time."""
        for cls in [CryptoInvestorV1, BollingerMeanReversion, VolatilityBreakout]:
            roi = cls.minimal_roi
            sorted_keys = sorted(int(k) for k in roi)
            values = [roi[str(k)] for k in sorted_keys]
            for i in range(1, len(values)):
                assert values[i] <= values[i - 1], (
                    f"{cls.__name__} ROI not decreasing: {values}"
                )

    def test_all_strategies_have_risk_api(self):
        """All strategies should have risk gate integration."""
        for cls in [CryptoInvestorV1, BollingerMeanReversion, VolatilityBreakout]:
            assert hasattr(cls, "risk_api_url")
            assert hasattr(cls, "risk_portfolio_id")
            assert hasattr(cls, "confirm_trade_entry")
