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

    def test_registry_count(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY

        assert len(STRATEGY_REGISTRY) >= 1

    def test_list_hft_strategies(self):
        from hftbacktest.hft_runner import list_hft_strategies

        names = list_hft_strategies()
        assert "MarketMaker" in names


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
        s.submit_order("buy", 100.0, 1.0, t2)   # Buy to close
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
        s.submit_order("buy", 100.0, 3.0, t1)   # Long 3.0
        s.submit_order("sell", 110.0, 1.0, t2)   # Sell 1.0: partial close
        assert s.position == pytest.approx(2.0)   # 2.0 still open
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
        s.submit_order("buy", 100.0, 1.0, t1)   # Long 1.0
        s.submit_order("sell", 110.0, 3.0, t2)   # Sell 3.0: close 1.0 long + open 2.0 short
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
        assert len(hft_strategies) >= 1
        assert any(s["name"] == "MarketMaker" for s in hft_strategies)
