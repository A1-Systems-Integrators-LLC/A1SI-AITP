"""
Tests for hftbacktest strategies (Tier 4)
==========================================
Covers: strategy registry, base class, tick data conversion,
market maker logic, backtesting, and backend integration.
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


def _make_ticks(n: int = 100, start_price: float = 100.0) -> np.ndarray:
    """Generate synthetic tick data: [timestamp_ns, price, volume, side]."""
    np.random.seed(42)
    timestamps = np.arange(n) * 1_000_000_000  # 1s intervals in ns
    prices = start_price + np.cumsum(np.random.normal(0, 0.1, n))
    volumes = np.random.uniform(0.01, 0.1, n)
    sides = np.random.choice([1.0, -1.0], n)
    return np.column_stack([timestamps, prices, volumes, sides])


def _make_ohlcv(n: int = 50, start_price: float = 100.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    np.random.seed(42)
    timestamps = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    returns = np.random.normal(0.0001, 0.01, n)
    prices = start_price * np.exp(np.cumsum(returns))
    return pd.DataFrame(
        {
            "open": prices * np.random.uniform(0.998, 1.002, n),
            "high": prices * np.random.uniform(1.001, 1.02, n),
            "low": prices * np.random.uniform(0.98, 0.999, n),
            "close": prices,
            "volume": np.random.lognormal(10, 1, n),
        },
        index=timestamps,
    )


# ── Registry Tests ───────────────────────────────────


class TestHFTRegistry:
    def test_registry_has_market_maker(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY

        assert "MarketMaker" in STRATEGY_REGISTRY

    def test_registry_has_momentum_scalper(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY

        assert "MomentumScalper" in STRATEGY_REGISTRY

    def test_registry_has_grid_trader(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY

        assert "GridTrader" in STRATEGY_REGISTRY

    def test_registry_has_mean_reversion_scalper(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY

        assert "MeanReversionScalper" in STRATEGY_REGISTRY

    def test_registry_count(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY

        assert len(STRATEGY_REGISTRY) >= 4

    def test_list_hft_strategies(self):
        from hftbacktest.hft_runner import list_hft_strategies

        names = list_hft_strategies()
        assert "MarketMaker" in names
        assert "MomentumScalper" in names
        assert "GridTrader" in names
        assert "MeanReversionScalper" in names


# ── Base Class Tests ─────────────────────────────────


class TestHFTBase:
    def test_init_defaults(self):
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy()
        assert s.position == 0.0
        assert s.gross_pnl == 0.0
        assert s.balance == 10000.0
        assert not s.halted

    def test_submit_buy_order(self):
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy()
        tick = {"timestamp": 1000, "price": 100.0, "volume": 0.1, "side": "sell"}
        fill = s.submit_order("buy", 100.0, 0.5, tick)
        assert fill is not None
        assert s.position == 0.5
        assert fill["side"] == "buy"

    def test_submit_sell_order(self):
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy()
        tick = {"timestamp": 1000, "price": 100.0, "volume": 0.1, "side": "buy"}
        fill = s.submit_order("sell", 100.0, 0.5, tick)
        assert fill is not None
        assert s.position == -0.5

    def test_position_limit_rejects_order(self):
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config={"max_position": 0.5})
        tick = {"timestamp": 1000, "price": 100.0, "volume": 0.1, "side": "sell"}
        s.submit_order("buy", 100.0, 0.5, tick)
        # Second order would exceed limit
        fill = s.submit_order("buy", 100.0, 0.5, tick)
        assert fill is None
        assert s.position == 0.5

    def test_round_trip_pnl(self):
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config={"fee_rate": 0.0})  # zero fees for legacy test
        tick1 = {"timestamp": 1000, "price": 100.0, "volume": 0.1, "side": "sell"}
        tick2 = {"timestamp": 2000, "price": 110.0, "volume": 0.1, "side": "buy"}
        s.submit_order("buy", 100.0, 1.0, tick1)
        s.submit_order("sell", 110.0, 1.0, tick2)
        assert s.position == 0.0
        assert s.gross_pnl == pytest.approx(10.0)

    def test_round_trip_pnl_with_fees(self):
        from hftbacktest.strategies.base import HFTBaseStrategy

        fee_rate = 0.0002
        s = HFTBaseStrategy(config={"fee_rate": fee_rate})
        tick1 = {"timestamp": 1000, "price": 100.0, "volume": 0.1, "side": "sell"}
        tick2 = {"timestamp": 2000, "price": 110.0, "volume": 0.1, "side": "buy"}
        s.submit_order("buy", 100.0, 1.0, tick1)
        s.submit_order("sell", 110.0, 1.0, tick2)
        assert s.position == 0.0
        # Gross PnL = 10.0, fees = 100*1*0.0002 + 110*1*0.0002 = 0.042
        expected_fees = 100.0 * 1.0 * fee_rate + 110.0 * 1.0 * fee_rate
        assert s.gross_pnl == pytest.approx(10.0)  # gross_pnl tracks gross PnL before fees
        # Balance = initial - fees + gross pnl
        assert s.balance == pytest.approx(10000.0 + 10.0 - expected_fees)
        # Fills have fee field
        assert "fee" in s.fills[0]
        assert s.fills[0]["fee"] == pytest.approx(100.0 * 1.0 * fee_rate)
        assert s.fills[1]["fee"] == pytest.approx(110.0 * 1.0 * fee_rate)

    def test_drawdown_halt(self):
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config={"initial_balance": 100.0})
        s.balance = 90.0  # 10% loss
        assert s.check_drawdown_halt(0.05) is True
        assert s.halted is True

    def test_halted_rejects_orders(self):
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy()
        s.halted = True
        tick = {"timestamp": 1000, "price": 100.0, "volume": 0.1, "side": "sell"}
        fill = s.submit_order("buy", 100.0, 0.5, tick)
        assert fill is None

    def test_fifo_trades_df_consecutive_buys(self):
        """Multiple buys then one sell should produce correct FIFO trades."""
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config={"fee_rate": 0.0, "max_position": 5.0})
        t1 = {"timestamp": 1000, "price": 100.0, "volume": 1.0, "side": "sell"}
        t2 = {"timestamp": 2000, "price": 102.0, "volume": 1.0, "side": "sell"}
        t3 = {"timestamp": 3000, "price": 110.0, "volume": 1.0, "side": "buy"}
        s.submit_order("buy", 100.0, 1.0, t1)
        s.submit_order("buy", 102.0, 1.0, t2)
        s.submit_order("sell", 110.0, 2.0, t3)
        df = s.get_trades_df()
        assert len(df) == 2  # Two FIFO round-trips
        # First trade: bought at 100, sold at 110 -> pnl = 10
        assert df.iloc[0]["entry_price"] == pytest.approx(100.0)
        assert df.iloc[0]["pnl"] == pytest.approx(10.0)
        # Second trade: bought at 102, sold at 110 -> pnl = 8
        assert df.iloc[1]["entry_price"] == pytest.approx(102.0)
        assert df.iloc[1]["pnl"] == pytest.approx(8.0)

    def test_fifo_trades_df_includes_fee(self):
        """FIFO trades should include fee deduction."""
        from hftbacktest.strategies.base import HFTBaseStrategy

        fee_rate = 0.001
        s = HFTBaseStrategy(config={"fee_rate": fee_rate})
        t1 = {"timestamp": 1000, "price": 100.0, "volume": 1.0, "side": "sell"}
        t2 = {"timestamp": 2000, "price": 110.0, "volume": 1.0, "side": "buy"}
        s.submit_order("buy", 100.0, 1.0, t1)
        s.submit_order("sell", 110.0, 1.0, t2)
        df = s.get_trades_df()
        assert len(df) == 1
        expected_fee = 100.0 * 1.0 * fee_rate + 110.0 * 1.0 * fee_rate
        assert df.iloc[0]["fee"] == pytest.approx(expected_fee)
        assert df.iloc[0]["pnl"] == pytest.approx(10.0 - expected_fee)

    def test_fifo_short_round_trip(self):
        """Short entry (sell) then buy exit should produce correct FIFO trade."""
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config={"fee_rate": 0.0, "max_position": 5.0})
        t1 = {"timestamp": 1000, "price": 110.0, "volume": 1.0, "side": "buy"}
        t2 = {"timestamp": 2000, "price": 100.0, "volume": 1.0, "side": "sell"}
        s.submit_order("sell", 110.0, 1.0, t1)  # Short entry
        s.submit_order("buy", 100.0, 1.0, t2)  # Buy to close
        assert s.position == 0.0
        df = s.get_trades_df()
        assert len(df) == 1
        assert df.iloc[0]["side"] == "sell"
        assert df.iloc[0]["entry_price"] == pytest.approx(110.0)
        assert df.iloc[0]["exit_price"] == pytest.approx(100.0)
        # Short PnL: (entry - exit) * size = (110 - 100) * 1 = 10
        assert df.iloc[0]["pnl"] == pytest.approx(10.0)

    def test_fifo_partial_close(self):
        """Sell that partially closes a larger long should leave residual open."""
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config={"fee_rate": 0.0, "max_position": 5.0})
        t1 = {"timestamp": 1000, "price": 100.0, "volume": 1.0, "side": "sell"}
        t2 = {"timestamp": 2000, "price": 110.0, "volume": 1.0, "side": "buy"}
        s.submit_order("buy", 100.0, 3.0, t1)  # Long 3.0
        s.submit_order("sell", 110.0, 1.0, t2)  # Sell 1.0: partial close
        assert s.position == pytest.approx(2.0)  # 2.0 still open
        df = s.get_trades_df()
        assert len(df) == 1  # One closed round-trip
        assert df.iloc[0]["size"] == pytest.approx(1.0)
        assert df.iloc[0]["pnl"] == pytest.approx(10.0)

    def test_fifo_position_flip(self):
        """Single fill that flips from long to short should produce trade + new open."""
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config={"fee_rate": 0.0, "max_position": 5.0})
        t1 = {"timestamp": 1000, "price": 100.0, "volume": 1.0, "side": "sell"}
        t2 = {"timestamp": 2000, "price": 110.0, "volume": 1.0, "side": "buy"}
        s.submit_order("buy", 100.0, 1.0, t1)  # Long 1.0
        s.submit_order("sell", 110.0, 3.0, t2)  # Sell 3.0: close 1.0 long + open 2.0 short
        assert s.position == pytest.approx(-2.0)
        df = s.get_trades_df()
        # Only 1 closed trade (the long close), short 2.0 is still open
        assert len(df) == 1
        assert df.iloc[0]["entry_price"] == pytest.approx(100.0)
        assert df.iloc[0]["exit_price"] == pytest.approx(110.0)
        assert df.iloc[0]["size"] == pytest.approx(1.0)
        assert df.iloc[0]["pnl"] == pytest.approx(10.0)


# ── Market Maker Tests ───────────────────────────────


class TestMarketMaker:
    def test_instantiation(self):
        from hftbacktest.strategies.market_maker import HFTMarketMaker

        s = HFTMarketMaker()
        assert s.name == "MarketMaker"
        assert s.half_spread > 0

    def test_processes_ticks_without_error(self):
        from hftbacktest.strategies.market_maker import HFTMarketMaker

        s = HFTMarketMaker(config={"max_position": 10.0})
        ticks = _make_ticks(200)
        s.run(ticks)
        # Should complete without error


# ── MomentumScalper Tests ────────────────────────────


class TestMomentumScalper:
    def test_instantiation(self):
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        s = HFTMomentumScalper()
        assert s.name == "MomentumScalper"
        assert s.lookback == 20
        assert s.entry_threshold == 0.0005

    def test_processes_ticks_without_error(self):
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        s = HFTMomentumScalper(config={"max_position": 10.0})
        ticks = _make_ticks(200)
        s.run(ticks)

    def test_enters_long_on_positive_momentum(self):
        """Strong upward ticks should trigger a buy."""
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        s = HFTMomentumScalper(config={
            "lookback": 5,
            "entry_threshold": 0.0001,
            "max_position": 1.0,
        })
        # Feed rising prices to build positive momentum
        for i in range(20):
            tick = {"timestamp": i * 1e9, "price": 100.0 + i * 0.1, "volume": 0.1, "side": "sell"}
            s.on_tick(tick)
        # Should have entered long
        assert s.position > 0 or len(s.fills) > 0

    def test_enters_short_on_negative_momentum(self):
        """Strong downward ticks should trigger a sell."""
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        s = HFTMomentumScalper(config={
            "lookback": 5,
            "entry_threshold": 0.0001,
            "max_position": 1.0,
        })
        for i in range(20):
            tick = {"timestamp": i * 1e9, "price": 100.0 - i * 0.1, "volume": 0.1, "side": "buy"}
            s.on_tick(tick)
        assert s.position < 0 or len(s.fills) > 0

    def test_exit_on_max_hold_ticks(self):
        """Position should be closed after max_hold_ticks."""
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        s = HFTMomentumScalper(config={
            "lookback": 3,
            "entry_threshold": 0.0001,
            "max_hold_ticks": 5,
            "max_position": 1.0,
        })
        # Build momentum to enter
        for i in range(10):
            tick = {"timestamp": i * 1e9, "price": 100.0 + i * 0.1, "volume": 0.1, "side": "sell"}
            s.on_tick(tick)
        # Now feed flat prices — should exit after max_hold_ticks
        pos_after_entry = s.position
        if pos_after_entry != 0:
            for i in range(10, 30):
                tick = {"timestamp": i * 1e9, "price": 101.0, "volume": 0.1, "side": "sell"}
                s.on_tick(tick)
            # Position should have been force-closed
            assert s.position == 0 or s._hold_counter < s.max_hold_ticks

    def test_drawdown_halt(self):
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        s = HFTMomentumScalper(config={"drawdown_halt_pct": 0.01, "initial_balance": 100.0})
        s.balance = 98.0  # 2% drawdown > 1% threshold
        tick = {"timestamp": 1e9, "price": 100.0, "volume": 0.1, "side": "sell"}
        s.on_tick(tick)
        assert s.halted is True

    def test_config_override(self):
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        cfg = {"lookback": 10, "entry_threshold": 0.001, "order_size": 0.05}
        s = HFTMomentumScalper(config=cfg)
        assert s.lookback == 10
        assert s.entry_threshold == 0.001
        assert s.order_size == 0.05

    def test_registry_presence(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        assert STRATEGY_REGISTRY["MomentumScalper"] is HFTMomentumScalper


# ── GridTrader Tests ─────────────────────────────────


class TestGridTrader:
    def test_instantiation(self):
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        s = HFTGridTrader()
        assert s.name == "GridTrader"
        assert s.grid_spacing == 0.002
        assert s.num_levels == 3

    def test_processes_ticks_without_error(self):
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        s = HFTGridTrader(config={"max_position": 10.0})
        ticks = _make_ticks(200)
        s.run(ticks)

    def test_buys_at_lower_grid_level(self):
        """Price dropping below a grid level should trigger a buy."""
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        s = HFTGridTrader(config={"grid_spacing": 0.01, "num_levels": 2, "max_position": 1.0})
        # First tick sets reference price
        s.on_tick({"timestamp": 0, "price": 100.0, "volume": 0.1, "side": "sell"})
        # Price drops below level 1 (100 * (1 - 0.01) = 99.0)
        s.on_tick({"timestamp": 1e9, "price": 98.5, "volume": 0.1, "side": "sell"})
        assert s.position > 0

    def test_sells_at_upper_grid_level(self):
        """Price rising above a grid level should trigger a sell."""
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        s = HFTGridTrader(config={"grid_spacing": 0.01, "num_levels": 2, "max_position": 1.0})
        s.on_tick({"timestamp": 0, "price": 100.0, "volume": 0.1, "side": "buy"})
        # Price rises above level 1 (100 * (1 + 0.01) = 101.0)
        s.on_tick({"timestamp": 1e9, "price": 101.5, "volume": 0.1, "side": "buy"})
        assert s.position < 0

    def test_grid_reset_on_price_escape(self):
        """Grid should reset when price moves outside the grid range."""
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        s = HFTGridTrader(config={"grid_spacing": 0.01, "num_levels": 2, "max_position": 10.0})
        s.on_tick({"timestamp": 0, "price": 100.0, "volume": 0.1, "side": "sell"})
        ref_before = s._reference_price
        # Price escapes above upper bound (100 * (1 + 3 * 0.01) = 103.0)
        s.on_tick({"timestamp": 1e9, "price": 104.0, "volume": 0.1, "side": "buy"})
        assert s._reference_price != ref_before  # Grid was reset

    def test_grid_reset_on_all_levels_filled(self):
        """Grid resets when all buy and sell levels have been filled."""
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        s = HFTGridTrader(config={
            "grid_spacing": 0.01,
            "num_levels": 1,
            "max_position": 10.0,
        })
        s.on_tick({"timestamp": 0, "price": 100.0, "volume": 0.1, "side": "sell"})
        # Fill buy level 1
        s.on_tick({"timestamp": 1e9, "price": 98.0, "volume": 0.1, "side": "sell"})
        # Fill sell level 1
        s.on_tick({"timestamp": 2e9, "price": 102.0, "volume": 0.1, "side": "buy"})
        # Next tick should see reset (all filled)
        ref_before = s._reference_price
        s.on_tick({"timestamp": 3e9, "price": 100.0, "volume": 0.1, "side": "sell"})
        assert s._reference_price != ref_before or len(s._buy_levels_filled) == 0

    def test_drawdown_halt(self):
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        s = HFTGridTrader(config={"drawdown_halt_pct": 0.01, "initial_balance": 100.0})
        s.balance = 98.0
        tick = {"timestamp": 1e9, "price": 100.0, "volume": 0.1, "side": "sell"}
        s.on_tick(tick)
        assert s.halted is True

    def test_config_override(self):
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        s = HFTGridTrader(config={"grid_spacing": 0.005, "num_levels": 5, "order_size": 0.02})
        assert s.grid_spacing == 0.005
        assert s.num_levels == 5
        assert s.order_size == 0.02

    def test_registry_presence(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        assert STRATEGY_REGISTRY["GridTrader"] is HFTGridTrader


# ── MeanReversionScalper Tests ──────────────────────


class TestMeanReversionScalper:
    def test_instantiation(self):
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        s = HFTMeanReversionScalper()
        assert s.name == "MeanReversionScalper"
        assert s.lookback == 50
        assert s.deviation_threshold == 0.001

    def test_processes_ticks_without_error(self):
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        s = HFTMeanReversionScalper(config={"max_position": 10.0})
        ticks = _make_ticks(200)
        s.run(ticks)

    def test_buys_below_vwap(self):
        """Price well below VWAP should trigger a buy."""
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        s = HFTMeanReversionScalper(config={
            "lookback": 10,
            "deviation_threshold": 0.005,
            "max_position": 1.0,
        })
        # Build VWAP around 100
        for i in range(10):
            s.on_tick({"timestamp": i * 1e9, "price": 100.0, "volume": 1.0, "side": "sell"})
        # Price drops well below VWAP
        s.on_tick({"timestamp": 11e9, "price": 99.0, "volume": 1.0, "side": "sell"})
        assert s.position > 0

    def test_sells_above_vwap(self):
        """Price well above VWAP should trigger a sell."""
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        s = HFTMeanReversionScalper(config={
            "lookback": 10,
            "deviation_threshold": 0.005,
            "max_position": 1.0,
        })
        for i in range(10):
            s.on_tick({"timestamp": i * 1e9, "price": 100.0, "volume": 1.0, "side": "buy"})
        s.on_tick({"timestamp": 11e9, "price": 101.0, "volume": 1.0, "side": "buy"})
        assert s.position < 0

    def test_exit_on_vwap_crossover(self):
        """Long position should exit when price reverts back to VWAP."""
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        s = HFTMeanReversionScalper(config={
            "lookback": 5,
            "deviation_threshold": 0.01,
            "max_position": 1.0,
        })
        # Build VWAP at 100
        for i in range(5):
            s.on_tick({"timestamp": i * 1e9, "price": 100.0, "volume": 1.0, "side": "sell"})
        # Enter long below VWAP
        s.on_tick({"timestamp": 6e9, "price": 98.0, "volume": 1.0, "side": "sell"})
        assert s.position > 0
        # Price reverts to VWAP — should exit
        s.on_tick({"timestamp": 7e9, "price": 100.0, "volume": 1.0, "side": "sell"})
        assert s.position == pytest.approx(0.0)

    def test_exit_on_max_hold_ticks(self):
        """Position should be closed after max_hold_ticks."""
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        s = HFTMeanReversionScalper(config={
            "lookback": 5,
            "deviation_threshold": 0.01,
            "max_hold_ticks": 3,
            "max_position": 1.0,
        })
        # Build VWAP at 100
        for i in range(5):
            s.on_tick({"timestamp": i * 1e9, "price": 100.0, "volume": 1.0, "side": "sell"})
        # Enter long
        s.on_tick({"timestamp": 6e9, "price": 98.0, "volume": 1.0, "side": "sell"})
        assert s.position > 0
        # Feed ticks that stay below VWAP (no crossover exit)
        for i in range(7, 12):
            s.on_tick({"timestamp": i * 1e9, "price": 98.0, "volume": 1.0, "side": "sell"})
        # Should have force-exited after max_hold_ticks
        assert s.position == pytest.approx(0.0)

    def test_drawdown_halt(self):
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        s = HFTMeanReversionScalper(config={"drawdown_halt_pct": 0.01, "initial_balance": 100.0})
        s.balance = 98.0
        tick = {"timestamp": 1e9, "price": 100.0, "volume": 0.1, "side": "sell"}
        s.on_tick(tick)
        assert s.halted is True

    def test_config_override(self):
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        cfg = {"lookback": 30, "deviation_threshold": 0.002, "order_size": 0.05}
        s = HFTMeanReversionScalper(config=cfg)
        assert s.lookback == 30
        assert s.deviation_threshold == 0.002
        assert s.order_size == 0.05

    def test_registry_presence(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        assert STRATEGY_REGISTRY["MeanReversionScalper"] is HFTMeanReversionScalper


# ── Data Conversion Tests ────────────────────────────


class TestHFTDataConversion:
    def test_ohlcv_to_ticks(self):
        from common.data_pipeline.pipeline import to_hftbacktest_ticks

        df = _make_ohlcv(10)
        ticks = to_hftbacktest_ticks(df)
        assert ticks.shape == (40, 4)  # 4 ticks per bar
        assert ticks.dtype == np.float64


# ── Backend Integration Tests ────────────────────────


class TestBacktestServiceHFT:
    def test_list_strategies_includes_hft(self):
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        from analysis.services.backtest import BacktestService

        strategies = BacktestService.list_strategies()
        hft_strategies = [s for s in strategies if s["framework"] == "hftbacktest"]
        assert len(hft_strategies) >= 4
        hft_names = {s["name"] for s in hft_strategies}
        assert "MarketMaker" in hft_names
        assert "MomentumScalper" in hft_names
        assert "GridTrader" in hft_names
        assert "MeanReversionScalper" in hft_names
