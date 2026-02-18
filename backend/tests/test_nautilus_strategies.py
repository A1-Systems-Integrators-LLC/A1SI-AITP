"""
Tests for NautilusTrader strategies (Tier 3)
=============================================
Covers: strategy registry, base class, indicator computation,
data conversion, backtesting, and backend integration.

Engine-level tests are skipped when nautilus_trader is not installed.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Helpers ──────────────────────────────────────────


def _make_ohlcv(n: int = 300, start_price: float = 100.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    timestamps = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    returns = np.random.normal(0.0001, 0.01, n)
    prices = start_price * np.exp(np.cumsum(returns))
    noise = np.random.uniform(0.998, 1.002, n)
    return pd.DataFrame(
        {
            "open": prices * noise,
            "high": prices * np.random.uniform(1.001, 1.02, n),
            "low": prices * np.random.uniform(0.98, 0.999, n),
            "close": prices,
            "volume": np.random.lognormal(10, 1, n),
        },
        index=timestamps,
    )


def _bars_from_df(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to list of bar dicts."""
    bars = []
    for ts, row in df.iterrows():
        bars.append(
            {
                "timestamp": ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )
    return bars


# ── Registry Tests ───────────────────────────────────


class TestNautilusRegistry:
    def test_registry_has_three_strategies(self):
        from nautilus.strategies import STRATEGY_REGISTRY

        assert len(STRATEGY_REGISTRY) == 3

    def test_registry_keys(self):
        from nautilus.strategies import STRATEGY_REGISTRY

        expected = {
            "NautilusTrendFollowing",
            "NautilusMeanReversion",
            "NautilusVolatilityBreakout",
        }
        assert set(STRATEGY_REGISTRY.keys()) == expected

    def test_all_strategies_are_classes(self):
        from nautilus.strategies import STRATEGY_REGISTRY

        for name, cls in STRATEGY_REGISTRY.items():
            assert isinstance(cls, type), f"{name} is not a class"

    def test_list_nautilus_strategies(self):
        from nautilus.nautilus_runner import list_nautilus_strategies

        names = list_nautilus_strategies()
        assert len(names) == 3
        assert "NautilusTrendFollowing" in names


# ── Base Class Tests ─────────────────────────────────


class TestNautilusBase:
    def test_base_init_defaults(self):
        from nautilus.strategies.base import NautilusStrategyBase

        s = NautilusStrategyBase()
        assert s.position is None
        assert len(s.trades) == 0
        assert len(s.bars) == 0

    def test_base_bars_bounded(self):
        from nautilus.strategies.base import NautilusStrategyBase

        s = NautilusStrategyBase(config={"max_bars": 10})
        assert s.bars.maxlen == 10

    def test_bars_to_df(self):
        from nautilus.strategies.base import NautilusStrategyBase

        s = NautilusStrategyBase()
        df = _make_ohlcv(5)
        for bar in _bars_from_df(df):
            s.bars.append(bar)
        result = s._bars_to_df()
        assert len(result) == 5
        assert "close" in result.columns

    def test_indicator_computation(self):
        from nautilus.strategies.base import NautilusStrategyBase

        s = NautilusStrategyBase()
        df = _make_ohlcv(250)
        for bar in _bars_from_df(df):
            s.bars.append(bar)
        indicators = s._compute_indicators(s._bars_to_df())
        assert "rsi_14" in indicators.index
        assert "ema_50" in indicators.index
        assert "atr_14" in indicators.index
        assert "bb_upper" in indicators.index

    def test_sprint_a_indicators_present(self):
        """Verify Sprint A indicators: ema_20, macd_hist_prev, high_20_prev."""
        from nautilus.strategies.base import NautilusStrategyBase

        s = NautilusStrategyBase()
        df = _make_ohlcv(250)
        for bar in _bars_from_df(df):
            s.bars.append(bar)
        indicators = s._compute_indicators(s._bars_to_df())
        # ema_20 added for volatility breakout exit
        assert "ema_20" in indicators.index
        assert not pd.isna(indicators["ema_20"])
        # macd_hist_prev for MACD turning-positive logic
        assert "macd_hist_prev" in indicators.index
        assert not pd.isna(indicators["macd_hist_prev"])
        # high_20_prev for proper breakout detection (excludes current bar)
        assert "high_20_prev" in indicators.index
        assert not pd.isna(indicators["high_20_prev"])

    def test_on_stop_flattens_position(self):
        from nautilus.strategies.base import NautilusStrategyBase

        s = NautilusStrategyBase()
        df = _make_ohlcv(5)
        for bar in _bars_from_df(df):
            s.bars.append(bar)
        s.position = {
            "side": "long",
            "entry_price": 100.0,
            "size": 1.0,
            "entry_time": df.index[0],
        }
        trade = s.on_stop()
        assert trade is not None
        assert s.position is None
        assert len(s.trades) == 1

    def test_on_stop_includes_fee(self):
        """Verify on_stop() produces fee-adjusted PnL."""
        from nautilus.strategies.base import NautilusStrategyBase

        s = NautilusStrategyBase(config={"fee_rate": 0.001})
        df = _make_ohlcv(5)
        for bar in _bars_from_df(df):
            s.bars.append(bar)
        entry_price = 100.0
        size = 1.0
        s.position = {
            "side": "long",
            "entry_price": entry_price,
            "size": size,
            "entry_time": df.index[0],
        }
        trade = s.on_stop()
        exit_price = trade["exit_price"]
        expected_fee = (entry_price + exit_price) * size * 0.001
        assert "fee" in trade
        assert trade["fee"] == pytest.approx(expected_fee, rel=1e-6)
        raw_pnl = (exit_price - entry_price) * size
        assert trade["pnl"] == pytest.approx(raw_pnl - expected_fee, rel=1e-6)

    def test_make_trade_fee_math(self):
        """Test _make_trade() fee calculation with known values."""
        from nautilus.strategies.base import NautilusStrategyBase

        s = NautilusStrategyBase(config={"fee_rate": 0.001})
        entry_price = 100.0
        exit_price = 110.0
        size = 2.0
        s.bars.append({
            "timestamp": pd.Timestamp("2024-01-01", tz="UTC"),
            "open": 110.0, "high": 111.0, "low": 109.0,
            "close": exit_price, "volume": 1000.0,
        })
        s.position = {
            "side": "long",
            "entry_price": entry_price,
            "size": size,
            "entry_time": pd.Timestamp("2024-01-01", tz="UTC"),
        }
        bar = s.bars[-1]
        trade = s._make_trade(exit_price, bar)

        # Fee = (100 + 110) * 2 * 0.001 = 0.42
        expected_fee = (100.0 + 110.0) * 2.0 * 0.001
        assert trade["fee"] == pytest.approx(expected_fee, rel=1e-6)
        # Raw PnL = (110 - 100) * 2 = 20, net = 20 - 0.42 = 19.58
        assert trade["pnl"] == pytest.approx(20.0 - expected_fee, rel=1e-6)
        # pnl_pct = (110/100) - 1 - 2*0.001 = 0.098
        expected_pct = (110.0 / 100.0) - 1 - (2 * 0.001)
        assert trade["pnl_pct"] == pytest.approx(expected_pct, rel=1e-6)
        assert s.position is None
        assert len(s.trades) == 1


# ── Strategy Signal Tests ────────────────────────────


class TestTrendFollowing:
    def test_instantiation(self):
        from nautilus.strategies.trend_following import NautilusTrendFollowing

        s = NautilusTrendFollowing()
        assert s.name == "NautilusTrendFollowing"
        assert s.stoploss == -0.05

    def test_processes_bars_without_error(self):
        from nautilus.strategies.trend_following import NautilusTrendFollowing

        s = NautilusTrendFollowing(config={"mode": "backtest"})
        df = _make_ohlcv(250)
        for bar in _bars_from_df(df):
            s.on_bar(bar)
        # Should not crash; may or may not produce trades depending on data

    def test_macd_turning_positive_triggers_entry(self):
        """MACD hist negative but rising should allow entry (Freqtrade parity)."""
        from nautilus.strategies.trend_following import NautilusTrendFollowing

        s = NautilusTrendFollowing()
        # Craft indicators: uptrend (ema_50 > ema_200, close > ema_50),
        # RSI pulled back, volume ok, MACD hist negative but rising, not near BB
        ind = pd.Series({
            "close": 105.0,
            "ema_50": 102.0,
            "ema_200": 100.0,
            "rsi_14": 35.0,          # below buy_rsi_threshold (40)
            "volume_ratio": 1.0,
            "macd_hist": -0.1,        # negative
            "macd_hist_prev": -0.5,   # but rising (prev was more negative)
            "bb_upper": 120.0,
        })
        assert s.should_enter(ind) is True

    def test_macd_negative_and_falling_rejects_entry(self):
        """MACD hist negative and falling should reject entry."""
        from nautilus.strategies.trend_following import NautilusTrendFollowing

        s = NautilusTrendFollowing()
        ind = pd.Series({
            "close": 105.0,
            "ema_50": 102.0,
            "ema_200": 100.0,
            "rsi_14": 35.0,
            "volume_ratio": 1.0,
            "macd_hist": -0.5,        # negative
            "macd_hist_prev": -0.1,   # and falling (prev was less negative)
            "bb_upper": 120.0,
        })
        assert s.should_enter(ind) is False


class TestMeanReversion:
    def test_instantiation(self):
        from nautilus.strategies.mean_reversion import NautilusMeanReversion

        s = NautilusMeanReversion()
        assert s.name == "NautilusMeanReversion"
        assert s.stoploss == -0.04

    def test_processes_bars_without_error(self):
        from nautilus.strategies.mean_reversion import NautilusMeanReversion

        s = NautilusMeanReversion(config={"mode": "backtest"})
        df = _make_ohlcv(250)
        for bar in _bars_from_df(df):
            s.on_bar(bar)

    def test_bb_lower_rsi_oversold_triggers_entry(self):
        """Close below BB lower + RSI oversold + volume spike + low ADX -> entry."""
        from nautilus.strategies.mean_reversion import NautilusMeanReversion

        s = NautilusMeanReversion()
        ind = pd.Series({
            "close": 95.0,
            "bb_lower": 96.0,       # close below BB lower
            "rsi_14": 25.0,          # oversold (< 35)
            "volume_ratio": 2.0,     # above volume_factor (1.5)
            "adx_14": 20.0,          # ranging market (< 30)
        })
        assert s.should_enter(ind) is True

    def test_rsi_above_threshold_rejects_entry(self):
        """RSI above buy threshold should reject entry even if below BB lower."""
        from nautilus.strategies.mean_reversion import NautilusMeanReversion

        s = NautilusMeanReversion()
        ind = pd.Series({
            "close": 95.0,
            "bb_lower": 96.0,
            "rsi_14": 40.0,          # above buy_rsi_threshold (35)
            "volume_ratio": 2.0,
            "adx_14": 20.0,
        })
        assert s.should_enter(ind) is False

    def test_high_adx_rejects_entry(self):
        """High ADX (trending market) should reject mean reversion entry."""
        from nautilus.strategies.mean_reversion import NautilusMeanReversion

        s = NautilusMeanReversion()
        ind = pd.Series({
            "close": 95.0,
            "bb_lower": 96.0,
            "rsi_14": 25.0,
            "volume_ratio": 2.0,
            "adx_14": 35.0,          # above adx_ceiling (30) -> trending
        })
        assert s.should_enter(ind) is False

    def test_exit_above_bb_mid(self):
        """Close above BB mid should trigger exit (mean reversion target)."""
        from nautilus.strategies.mean_reversion import NautilusMeanReversion

        s = NautilusMeanReversion()
        ind = pd.Series({
            "close": 102.0,
            "bb_mid": 100.0,         # close above bb_mid -> exit
            "rsi_14": 50.0,
        })
        assert s.should_exit(ind) is True

    def test_exit_rsi_strong(self):
        """RSI above sell threshold should trigger exit."""
        from nautilus.strategies.mean_reversion import NautilusMeanReversion

        s = NautilusMeanReversion()
        ind = pd.Series({
            "close": 98.0,
            "bb_mid": 100.0,         # still below mid
            "rsi_14": 70.0,          # above sell_rsi_threshold (65)
        })
        assert s.should_exit(ind) is True


class TestVolatilityBreakout:
    def test_instantiation(self):
        from nautilus.strategies.volatility_breakout import NautilusVolatilityBreakout

        s = NautilusVolatilityBreakout()
        assert s.name == "NautilusVolatilityBreakout"
        assert s.stoploss == -0.03

    def test_processes_bars_without_error(self):
        from nautilus.strategies.volatility_breakout import NautilusVolatilityBreakout

        s = NautilusVolatilityBreakout(config={"mode": "backtest"})
        df = _make_ohlcv(250)
        for bar in _bars_from_df(df):
            s.on_bar(bar)

    def test_breakout_above_high_20_prev_triggers_entry(self):
        """Close above previous 20-period high should trigger entry."""
        from nautilus.strategies.volatility_breakout import NautilusVolatilityBreakout

        s = NautilusVolatilityBreakout()
        ind = pd.Series({
            "close": 110.0,
            "high_20_prev": 108.0,  # close breaks above previous high
            "volume_ratio": 2.0,    # above volume_factor (1.8)
            "bb_width": 0.05,       # positive BB width
            "adx_14": 20.0,         # in emerging-trend range (15-25)
            "rsi_14": 55.0,         # neutral zone (40-70)
        })
        assert s.should_enter(ind) is True

    def test_no_breakout_rejects_entry(self):
        """Close at or below high_20_prev should reject entry."""
        from nautilus.strategies.volatility_breakout import NautilusVolatilityBreakout

        s = NautilusVolatilityBreakout()
        ind = pd.Series({
            "close": 107.0,
            "high_20_prev": 108.0,  # close below previous high
            "volume_ratio": 2.0,
            "bb_width": 0.05,
            "adx_14": 20.0,
            "rsi_14": 55.0,
        })
        assert s.should_enter(ind) is False

    def test_exit_below_ema_20(self):
        """Close below EMA20 should trigger exit."""
        from nautilus.strategies.volatility_breakout import NautilusVolatilityBreakout

        s = NautilusVolatilityBreakout()
        ind = pd.Series({
            "rsi_14": 60.0,     # not exhausted
            "close": 98.0,
            "ema_20": 100.0,    # close below ema_20 -> exit
        })
        assert s.should_exit(ind) is True


# ── Data Conversion Tests ────────────────────────────


class TestNautilusDataConversion:
    def test_csv_conversion(self, tmp_path):
        """Test Nautilus CSV conversion with mock data."""
        from common.data_pipeline.pipeline import save_ohlcv
        from nautilus.nautilus_runner import convert_ohlcv_to_nautilus_csv

        df = _make_ohlcv(50)
        save_ohlcv(df, "TEST/USDT", "1h", "testexch")

        path = convert_ohlcv_to_nautilus_csv("TEST/USDT", "1h", "testexch")
        assert path is not None
        assert path.exists()

        csv_df = pd.read_csv(path)
        assert len(csv_df) == 50
        assert "bar_type" in csv_df.columns


# ── Backend Integration Tests ────────────────────────


class TestBacktestServiceNautilus:
    def test_list_strategies_includes_nautilus(self):
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        from analysis.services.backtest import BacktestService

        strategies = BacktestService.list_strategies()
        nautilus_strategies = [s for s in strategies if s["framework"] == "nautilus"]
        assert len(nautilus_strategies) == 3
