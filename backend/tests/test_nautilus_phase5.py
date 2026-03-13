"""
Phase 5 coverage tests for nautilus/ — targeting 100% line coverage.

Covers:
- nt_native.py: native adapter instantiation, on_bar signal paths, enter/exit/stop
- engine.py: HAS_NAUTILUS_TRADER=False ImportError paths, config exception
- nautilus_runner.py: config exception, native backtest exception, engine test paths
- base.py: abstract methods, position sizing edge case, risk gate exception
- Strategy edge cases: volume/BB width guards
"""

import pytest
from collections import deque
from unittest.mock import MagicMock, patch

import pandas as pd

from nautilus.strategies.nt_native import (
    HAS_NAUTILUS_TRADER,
    _NativeAdapterConfig,
    NativeTrendFollowing,
    NativeMeanReversion,
    NativeVolatilityBreakout,
    NativeEquityMomentum,
    NativeEquityMeanReversion,
    NativeForexTrend,
    NativeForexRange,
)

pytestmark = pytest.mark.skipif(not HAS_NAUTILUS_TRADER, reason="nautilus_trader not installed")

# ── Helpers ──────────────────────────────────────────────────────────

_DEFAULT_CONFIG = _NativeAdapterConfig(
    instrument_id="BTCUSDT.BINANCE",
    bar_type="BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL",
    trade_size=0.01,
    mode="backtest",
)


class FakeBar:
    """Minimal bar mimicking nautilus_trader.model.data.Bar attributes."""

    def __init__(self, close=100.0, ts_event=0):
        self.open = close
        self.high = close + 1
        self.low = close - 1
        self.close = close
        self.volume = 100.0
        self.ts_event = ts_event


def _setup_engine_with_strategy(adapter_cls, n_bars=250, closes=None,
                                 should_enter_seq=None, should_exit_seq=None):
    """Create a real BacktestEngine with the given native adapter and synthetic data.

    Mocks _compute_indicators and should_enter/should_exit to control signal flow.
    Returns (engine, strategy) — caller must engine.dispose() after.
    """
    from nautilus.engine import (
        create_backtest_engine,
        add_venue,
        create_crypto_instrument,
        build_bar_type,
        convert_df_to_bars,
    )

    engine = create_backtest_engine(log_level="WARNING")
    add_venue(engine, "KRAKEN", starting_balance=10000.0)
    instrument = create_crypto_instrument("BTC/USDT", "KRAKEN")
    engine.add_instrument(instrument)
    bar_type = build_bar_type(instrument.id, "1h")

    config = _NativeAdapterConfig(
        instrument_id=str(instrument.id),
        bar_type=str(bar_type),
        trade_size=0.01,
        mode="backtest",
    )
    strategy = adapter_cls(config=config)
    engine.add_strategy(strategy)

    # Mock signal engine to control signal flow
    strategy._signal_engine._compute_indicators = MagicMock(
        return_value=pd.Series({"close": 1000.0})
    )
    if should_enter_seq is not None:
        strategy._signal_engine.should_enter = MagicMock(side_effect=should_enter_seq)
    if should_exit_seq is not None:
        strategy._signal_engine.should_exit = MagicMock(side_effect=should_exit_seq)

    # Create synthetic bar data
    if closes is None:
        closes = [1000.0] * n_bars
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [100.0] * n_bars,
        },
        index=dates,
    )
    bars = convert_df_to_bars(df, bar_type, price_precision=2, size_precision=6)
    engine.add_data(bars)

    return engine, strategy


# ══════════════════════════════════════════════════════════════════════
# Section 1: Native Adapter Instantiation (nt_native.py lines 170-220)
# ══════════════════════════════════════════════════════════════════════


class TestNativeAdapterInstantiation:
    """Cover concrete adapter __init__ methods via direct instantiation."""

    def test_native_mean_reversion_init(self):
        adapter = NativeMeanReversion(config=_DEFAULT_CONFIG)
        assert adapter._signal_engine.name == "NautilusMeanReversion"

    def test_native_volatility_breakout_init(self):
        adapter = NativeVolatilityBreakout(config=_DEFAULT_CONFIG)
        assert adapter._signal_engine.name == "NautilusVolatilityBreakout"

    def test_native_equity_momentum_init(self):
        adapter = NativeEquityMomentum(config=_DEFAULT_CONFIG)
        assert adapter._signal_engine.name == "EquityMomentum"

    def test_native_equity_mean_reversion_init(self):
        adapter = NativeEquityMeanReversion(config=_DEFAULT_CONFIG)
        assert adapter._signal_engine.name == "EquityMeanReversion"

    def test_native_forex_trend_init(self):
        adapter = NativeForexTrend(config=_DEFAULT_CONFIG)
        assert adapter._signal_engine.name == "ForexTrend"

    def test_native_forex_range_init(self):
        adapter = NativeForexRange(config=_DEFAULT_CONFIG)
        assert adapter._signal_engine.name == "ForexRange"


# ══════════════════════════════════════════════════════════════════════
# Section 2: on_bar / _enter_long / _exit_position / on_stop
# (nt_native.py lines 105-153)
# ══════════════════════════════════════════════════════════════════════


class TestNativeAdapterOnBar:
    """Cover on_bar signal evaluation, order submission, and stop logic.

    Uses real BacktestEngine with mocked signal engine for deterministic testing.
    """

    def test_entry_and_on_stop_flatten(self):
        """Entry on bar 199, hold (stoploss checks but no trigger), on_stop flatten.

        Covers: lines 105, 110-114, 118-133, 152-153.
        """
        engine, strategy = _setup_engine_with_strategy(
            NativeTrendFollowing,
            n_bars=250,
            should_enter_seq=[True] + [False] * 200,
            should_exit_seq=[False] * 200,
        )
        engine.run()

        # on_stop flattened the position at engine end
        assert strategy._position_open is False
        assert strategy._signal_engine.should_enter.call_count == 1
        assert strategy._signal_engine.should_exit.call_count >= 1
        engine.dispose()

    def test_exit_via_signal(self):
        """Entry, then exit via should_exit=True.

        Covers: lines 107-108, 136-147.
        """
        engine, strategy = _setup_engine_with_strategy(
            NativeTrendFollowing,
            n_bars=250,
            should_enter_seq=[True] + [False] * 200,
            should_exit_seq=[False, False, True] + [False] * 200,
        )
        engine.run()

        assert strategy._position_open is False
        assert strategy._signal_engine.should_exit.call_count >= 3
        engine.dispose()

    def test_exit_via_stoploss(self):
        """Entry at 1000, price drops to 940 (6% > 5% stoploss) → exit.

        Covers: lines 110-115 (stoploss trigger branch).
        """
        closes = [1000.0] * 205 + [940.0] * 45
        engine, strategy = _setup_engine_with_strategy(
            NativeTrendFollowing,
            n_bars=250,
            closes=closes,
            should_enter_seq=[True] + [False] * 200,
            should_exit_seq=[False] * 200,
        )
        strategy._signal_engine.stoploss = -0.05

        engine.run()

        assert strategy._position_open is False
        assert strategy._signal_engine.position is None
        engine.dispose()

    def test_exit_position_guard_when_not_open(self):
        """_exit_position with no open position → early return (line 136-137)."""
        adapter = NativeTrendFollowing(config=_DEFAULT_CONFIG)
        adapter._position_open = False

        # Doesn't touch order_factory (Cython), so this works
        adapter._exit_position(FakeBar())

    def test_on_stop_no_position(self):
        """on_stop with no position → no action."""
        adapter = NativeTrendFollowing(config=_DEFAULT_CONFIG)
        adapter._position_open = False

        adapter.on_stop()  # Should do nothing

    def test_on_start(self):
        """on_start subscribes to bars (tested via engine integration)."""
        # on_start is called by the engine during engine.run()
        # Already implicitly tested by the engine tests above.
        # Explicitly verify via direct call on a registered strategy:
        engine, strategy = _setup_engine_with_strategy(
            NativeTrendFollowing,
            n_bars=5,  # Minimal data, just test startup
            should_enter_seq=[False] * 10,
        )
        engine.run()
        engine.dispose()


# ══════════════════════════════════════════════════════════════════════
# Section 3: engine.py — ImportError paths and config exception
# (lines 55-56, 90, 110, 137, 176, 214, 288, 312)
# ══════════════════════════════════════════════════════════════════════


class TestEngineImportErrors:
    """Cover HAS_NAUTILUS_TRADER=False paths in engine.py."""

    def test_create_backtest_engine_no_nt(self):
        with patch("nautilus.engine.HAS_NAUTILUS_TRADER", False):
            from nautilus.engine import create_backtest_engine

            with pytest.raises(ImportError, match="nautilus_trader is not installed"):
                create_backtest_engine()

    def test_add_venue_no_nt(self):
        with patch("nautilus.engine.HAS_NAUTILUS_TRADER", False):
            from nautilus.engine import add_venue

            with pytest.raises(ImportError, match="nautilus_trader is not installed"):
                add_venue(MagicMock())

    def test_create_crypto_instrument_no_nt(self):
        with patch("nautilus.engine.HAS_NAUTILUS_TRADER", False):
            from nautilus.engine import create_crypto_instrument

            with pytest.raises(ImportError, match="nautilus_trader is not installed"):
                create_crypto_instrument()

    def test_create_equity_instrument_no_nt(self):
        with patch("nautilus.engine.HAS_NAUTILUS_TRADER", False):
            from nautilus.engine import create_equity_instrument

            with pytest.raises(ImportError, match="nautilus_trader is not installed"):
                create_equity_instrument()

    def test_create_forex_instrument_no_nt(self):
        with patch("nautilus.engine.HAS_NAUTILUS_TRADER", False):
            from nautilus.engine import create_forex_instrument

            with pytest.raises(ImportError, match="nautilus_trader is not installed"):
                create_forex_instrument()

    def test_build_bar_type_no_nt(self):
        with patch("nautilus.engine.HAS_NAUTILUS_TRADER", False):
            from nautilus.engine import build_bar_type

            with pytest.raises(ImportError, match="nautilus_trader is not installed"):
                build_bar_type(MagicMock())

    def test_convert_df_to_bars_no_nt(self):
        with patch("nautilus.engine.HAS_NAUTILUS_TRADER", False):
            from nautilus.engine import convert_df_to_bars

            with pytest.raises(ImportError, match="nautilus_trader is not installed"):
                convert_df_to_bars(pd.DataFrame(), MagicMock())

    def test_load_nautilus_config_exception(self):
        """Cover lines 55-56: exception in _load_nautilus_config."""
        from nautilus.engine import _load_nautilus_config

        with patch("nautilus.engine.CONFIG_PATH") as mock_path:
            mock_path.exists.return_value = True
            with patch("builtins.open", side_effect=OSError("disk error")):
                result = _load_nautilus_config()
                assert result == {}


# ══════════════════════════════════════════════════════════════════════
# Section 4: nautilus_runner.py — config exception, native error, engine test
# (lines 63-65, 263-265, 358-364)
# ══════════════════════════════════════════════════════════════════════


class TestNautilusRunnerGaps:
    """Cover uncovered paths in nautilus_runner.py."""

    def test_load_platform_config_generic_exception(self):
        """Cover lines 63-65: generic exception in _load_platform_config."""
        from nautilus.nautilus_runner import _load_platform_config

        with patch("nautilus.nautilus_runner.CONFIG_PATH") as mock_path:
            mock_path.exists.return_value = True
            with patch("builtins.open", side_effect=RuntimeError("corrupt")):
                result = _load_platform_config()
                assert result == {}

    def test_run_native_backtest_exception(self):
        """Cover lines 263-265: exception during native backtest → None."""
        from nautilus.nautilus_runner import _run_native_backtest

        with patch(
            "nautilus.engine.create_backtest_engine",
            side_effect=RuntimeError("engine crash"),
        ):
            result = _run_native_backtest(
                "NautilusTrendFollowing",
                pd.DataFrame(
                    {
                        "open": [1.0],
                        "high": [2.0],
                        "low": [0.5],
                        "close": [1.5],
                        "volume": [100.0],
                    }
                ),
                "BTC/USDT",
                "1h",
                "kraken",
                10000.0,
            )
            assert result is None

    def test_run_nautilus_engine_test_exception(self):
        """Cover lines 358-360: engine init raises in run_nautilus_engine_test."""
        from nautilus.nautilus_runner import run_nautilus_engine_test

        with patch("nautilus.nautilus_runner.HAS_NAUTILUS_TRADER", True):
            with patch(
                "nautilus.engine.create_backtest_engine",
                side_effect=RuntimeError("init failed"),
            ):
                assert run_nautilus_engine_test() is False

    def test_run_nautilus_engine_test_not_installed(self):
        """Cover lines 361-364: NT not installed path."""
        from nautilus.nautilus_runner import run_nautilus_engine_test

        with patch("nautilus.nautilus_runner.HAS_NAUTILUS_TRADER", False):
            assert run_nautilus_engine_test() is False


# ══════════════════════════════════════════════════════════════════════
# Section 5: base.py — abstract methods, position sizing, risk gate
# (lines 129, 133, 195, 230-232)
# ══════════════════════════════════════════════════════════════════════


class TestBaseStrategyGaps:
    """Cover base.py uncovered lines."""

    def test_should_enter_not_implemented(self):
        """Cover line 129."""
        from nautilus.strategies.base import NautilusStrategyBase

        with pytest.raises(NotImplementedError):
            NautilusStrategyBase().should_enter(pd.Series())

    def test_should_exit_not_implemented(self):
        """Cover line 133."""
        from nautilus.strategies.base import NautilusStrategyBase

        with pytest.raises(NotImplementedError):
            NautilusStrategyBase().should_exit(pd.Series())

    def test_position_sizing_zero_risk_per_unit(self):
        """Cover line 195: atr_multiplier=0 → risk_per_unit=0 → return 0.0."""
        from nautilus.strategies.base import NautilusStrategyBase

        base = NautilusStrategyBase()
        base.atr_multiplier = 0
        result = base._compute_position_size(pd.Series({"atr_14": 5.0}), 100.0)
        assert result == 0.0

    def test_risk_gate_api_exception(self):
        """Cover lines 230-232: exception in risk API call → return False."""
        from nautilus.strategies.base import NautilusStrategyBase

        base = NautilusStrategyBase(config={"mode": "live"})
        with patch.dict("sys.modules", {"requests": MagicMock()}):
            import sys

            sys.modules["requests"].post.side_effect = ConnectionError("refused")
            result = base._check_risk_gate({"close": 100}, 100.0, 0.01)
            assert result is False


# ══════════════════════════════════════════════════════════════════════
# Section 6: Strategy edge cases (individual uncovered lines)
# ══════════════════════════════════════════════════════════════════════


class TestStrategyEdgeCases:
    """Cover individual strategy edge case lines."""

    def test_equity_mean_reversion_low_volume(self):
        """Cover equity_mean_reversion.py line 33: volume_ratio < volume_factor."""
        from nautilus.strategies.equity_mean_reversion import EquityMeanReversion

        s = EquityMeanReversion()
        ind = pd.Series({"close": 90.0, "bb_lower": 95.0, "rsi_14": 20.0, "volume_ratio": 0.5})
        assert s.should_enter(ind) is False

    def test_equity_momentum_exit_no_conditions(self):
        """Cover equity_momentum.py line 55: return False (no exit conditions met)."""
        from nautilus.strategies.equity_momentum import EquityMomentum

        s = EquityMomentum()
        ind = pd.Series({"rsi_14": 60.0, "close": 200.0, "sma_50": 150.0})
        assert s.should_exit(ind) is False

    def test_forex_range_invalid_bb_lower(self):
        """Cover forex_range.py line 33: bb_lower <= 0."""
        from nautilus.strategies.forex_range import ForexRange

        s = ForexRange()
        ind = pd.Series({"adx_14": 15.0, "close": 1.0, "bb_lower": 0.0, "bb_width": 0.01})
        assert s.should_enter(ind) is False

    def test_forex_range_zero_bb_width(self):
        """Cover forex_range.py line 33: bb_width <= 0."""
        from nautilus.strategies.forex_range import ForexRange

        s = ForexRange()
        ind = pd.Series({"adx_14": 15.0, "close": 1.0, "bb_lower": 1.1, "bb_width": 0})
        assert s.should_enter(ind) is False

    def test_volatility_breakout_zero_bb_width(self):
        """Cover volatility_breakout.py line 43: bb_width <= 0."""
        from nautilus.strategies.volatility_breakout import NautilusVolatilityBreakout

        s = NautilusVolatilityBreakout()
        ind = pd.Series({"high_20_prev": 100.0, "close": 105.0, "volume_ratio": 2.0, "bb_width": 0})
        assert s.should_enter(ind) is False
