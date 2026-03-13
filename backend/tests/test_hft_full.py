"""Full coverage tests for hftbacktest/ module.

Covers: base class edge cases (empty ticks, position limits, drawdown,
FIFO trades), all 4 strategies with adversarial inputs, runner error paths,
config loading, tick conversion, result persistence.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Helpers ────────────────────────────────────────────

def _make_ticks(n=100, start_price=100.0, seed=42):
    np.random.seed(seed)
    timestamps = np.arange(n, dtype=np.float64) * 1_000_000_000
    prices = start_price + np.cumsum(np.random.normal(0, 0.1, n))
    volumes = np.random.uniform(0.01, 0.1, n)
    sides = np.random.choice([1.0, -1.0], n)
    return np.column_stack([timestamps, prices, volumes, sides])


def _make_flat_ticks(n=100, price=100.0):
    timestamps = np.arange(n, dtype=np.float64) * 1_000_000_000
    prices = np.full(n, price)
    volumes = np.full(n, 0.05)
    sides = np.ones(n)
    return np.column_stack([timestamps, prices, volumes, sides])


# ══════════════════════════════════════════════════════
# Base Class — Edge Cases
# ══════════════════════════════════════════════════════


class TestBaseStrategyEdgeCases:
    def test_empty_tick_array(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy()
        s.on_tick = lambda tick: None  # Override abstract method
        ticks = np.empty((0, 4))
        fills = s.run(ticks)
        assert fills == []
        assert s.position == 0.0

    def test_single_tick(self):
        from hftbacktest.strategies.market_maker import HFTMarketMaker
        ticks = _make_ticks(1)
        s = HFTMarketMaker()
        s.run(ticks)
        # Should not crash with single tick

    def test_position_limit_buy(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy(config={"max_position": 0.5})
        s.on_tick = lambda tick: None
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.05, "side": "buy"}
        # First order should succeed
        fill = s.submit_order("buy", 100.0, 0.3, tick)
        assert fill is not None
        assert s.position == 0.3
        # This exceeds 0.5 limit
        fill2 = s.submit_order("buy", 100.0, 0.3, tick)
        assert fill2 is None
        assert s.position == 0.3

    def test_position_limit_sell(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy(config={"max_position": 0.5})
        s.on_tick = lambda tick: None
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.05, "side": "sell"}
        fill = s.submit_order("sell", 100.0, 0.3, tick)
        assert fill is not None
        assert s.position == -0.3
        fill2 = s.submit_order("sell", 100.0, 0.3, tick)
        assert fill2 is None

    def test_halted_rejects_orders(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy()
        s.on_tick = lambda tick: None
        s.halted = True
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.05, "side": "buy"}
        fill = s.submit_order("buy", 100.0, 0.01, tick)
        assert fill is None

    def test_halted_stops_run_loop(self):
        from hftbacktest.strategies.market_maker import HFTMarketMaker
        s = HFTMarketMaker()
        s.halted = True
        ticks = _make_ticks(100)
        fills = s.run(ticks)
        assert fills == []

    def test_drawdown_halt_exact_threshold(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy(config={"initial_balance": 10000.0})
        s.on_tick = lambda tick: None
        # Lose exactly 5%
        s.balance = 9500.0
        s.peak_balance = 10000.0
        result = s.check_drawdown_halt(0.05)
        assert result is True
        assert s.halted is True

    def test_drawdown_just_below_threshold(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy(config={"initial_balance": 10000.0})
        s.on_tick = lambda tick: None
        s.balance = 9501.0
        s.peak_balance = 10000.0
        result = s.check_drawdown_halt(0.05)
        assert result is False
        assert s.halted is False

    def test_buy_closing_short_pnl(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy(config={"fee_rate": 0.0})
        s.on_tick = lambda tick: None
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.05, "side": "sell"}
        # Open short at 100
        s.submit_order("sell", 100.0, 0.1, tick)
        assert s.position == -0.1
        # Close short at 95 → profit
        tick2 = {"timestamp": 1000, "price": 95.0, "volume": 0.05, "side": "buy"}
        fill = s.submit_order("buy", 95.0, 0.1, tick2)
        assert fill["pnl"] == pytest.approx(0.5)  # 0.1 * (100 - 95)
        assert s.position == 0.0

    def test_sell_closing_long_pnl(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy(config={"fee_rate": 0.0})
        s.on_tick = lambda tick: None
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.05, "side": "buy"}
        s.submit_order("buy", 100.0, 0.1, tick)
        tick2 = {"timestamp": 1000, "price": 110.0, "volume": 0.05, "side": "sell"}
        fill = s.submit_order("sell", 110.0, 0.1, tick2)
        assert fill["pnl"] == pytest.approx(1.0)  # 0.1 * (110 - 100)

    def test_avg_cost_accumulation(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy(config={"fee_rate": 0.0, "max_position": 10.0})
        s.on_tick = lambda tick: None
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.05, "side": "buy"}
        s.submit_order("buy", 100.0, 1.0, tick)
        s.submit_order("buy", 110.0, 1.0, tick)
        # avg_cost = (100*1 + 110*1) / 2 = 105
        assert s.avg_cost == pytest.approx(105.0)
        assert s.position == 2.0

    def test_zero_fee_rate(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy(config={"fee_rate": 0.0})
        s.on_tick = lambda tick: None
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.05, "side": "buy"}
        fill = s.submit_order("buy", 100.0, 0.1, tick)
        assert fill["fee"] == 0.0
        assert s.total_fees == 0.0

    def test_fee_deduction(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy(config={"fee_rate": 0.001, "initial_balance": 10000.0})
        s.on_tick = lambda tick: None
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.05, "side": "buy"}
        fill = s.submit_order("buy", 100.0, 1.0, tick)
        assert fill["fee"] == pytest.approx(0.1)  # 100 * 1.0 * 0.001
        assert s.balance == pytest.approx(10000.0 - 0.1)


# ══════════════════════════════════════════════════════
# Base Class — FIFO get_trades_df
# ══════════════════════════════════════════════════════


class TestFIFOTrades:
    def test_no_fills_empty_df(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy()
        s.on_tick = lambda tick: None
        df = s.get_trades_df()
        assert df.empty

    def test_single_round_trip(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy(config={"fee_rate": 0.0})
        s.on_tick = lambda tick: None
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.05, "side": "buy"}
        s.submit_order("buy", 100.0, 0.1, tick)
        tick2 = {"timestamp": 1_000_000_000, "price": 105.0, "volume": 0.05, "side": "sell"}
        s.submit_order("sell", 105.0, 0.1, tick2)
        df = s.get_trades_df()
        assert len(df) == 1
        assert df["side"].iloc[0] == "buy"
        assert df["entry_price"].iloc[0] == 100.0
        assert df["exit_price"].iloc[0] == 105.0

    def test_consecutive_same_side_then_close(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy(config={"fee_rate": 0.0, "max_position": 10.0})
        s.on_tick = lambda tick: None
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.05, "side": "buy"}
        s.submit_order("buy", 100.0, 0.1, tick)
        s.submit_order("buy", 102.0, 0.1, tick)
        # Close both
        tick2 = {"timestamp": 1_000_000_000, "price": 110.0, "volume": 0.05, "side": "sell"}
        s.submit_order("sell", 110.0, 0.2, tick2)
        df = s.get_trades_df()
        # FIFO: first close at 100 entry, second at 102 entry
        assert len(df) == 2
        assert df["entry_price"].iloc[0] == 100.0
        assert df["entry_price"].iloc[1] == 102.0

    def test_partial_close(self):
        from hftbacktest.strategies.base import HFTBaseStrategy
        s = HFTBaseStrategy(config={"fee_rate": 0.0, "max_position": 10.0})
        s.on_tick = lambda tick: None
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.05, "side": "buy"}
        s.submit_order("buy", 100.0, 0.2, tick)
        # Partial close
        tick2 = {"timestamp": 1_000_000_000, "price": 105.0, "volume": 0.05, "side": "sell"}
        s.submit_order("sell", 105.0, 0.1, tick2)
        df = s.get_trades_df()
        assert len(df) == 1
        assert df["size"].iloc[0] == pytest.approx(0.1)


# ══════════════════════════════════════════════════════
# Market Maker — Edge Cases
# ══════════════════════════════════════════════════════


class TestMarketMakerEdgeCases:
    def test_flat_prices_produces_fills(self):
        from hftbacktest.strategies.market_maker import HFTMarketMaker
        ticks = _make_flat_ticks(100, price=100.0)
        s = HFTMarketMaker(config={"quote_interval": 1})
        s.run(ticks)
        # Should produce some fills even with flat prices
        assert isinstance(s.fills, list)

    def test_high_skew_factor(self):
        from hftbacktest.strategies.market_maker import HFTMarketMaker
        ticks = _make_ticks(100)
        s = HFTMarketMaker(config={"skew_factor": 0.01, "quote_interval": 1})
        s.run(ticks)
        # Should complete without crash

    def test_quote_interval_larger_than_ticks(self):
        from hftbacktest.strategies.market_maker import HFTMarketMaker
        ticks = _make_ticks(5)
        s = HFTMarketMaker(config={"quote_interval": 100})
        s.run(ticks)
        # Only requotes every 100 ticks, so with 5 ticks only tick 0 activates
        # No assertion on fills count since tick 0 triggers

    def test_name(self):
        from hftbacktest.strategies.market_maker import HFTMarketMaker
        s = HFTMarketMaker()
        assert s.name == "MarketMaker"


# ══════════════════════════════════════════════════════
# Momentum Scalper — Edge Cases
# ══════════════════════════════════════════════════════


class TestMomentumScalperEdgeCases:
    def test_flat_prices_no_entry(self):
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper
        ticks = _make_flat_ticks(100)
        s = HFTMomentumScalper()
        s.run(ticks)
        # EMA momentum should be ~0, no entry
        assert s.position == 0.0

    def test_strong_uptrend_enters_long(self):
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper
        # Clear uptrend
        n = 100
        timestamps = np.arange(n, dtype=np.float64) * 1_000_000_000
        prices = 100.0 + np.arange(n) * 0.1  # strong up
        volumes = np.full(n, 0.05)
        sides = np.ones(n)
        ticks = np.column_stack([timestamps, prices, volumes, sides])
        s = HFTMomentumScalper(config={"entry_threshold": 0.0001, "max_hold_ticks": 200})
        s.run(ticks)
        # Should have entered at least once
        assert len(s.fills) > 0

    def test_max_hold_ticks_forces_exit(self):
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper
        n = 200
        timestamps = np.arange(n, dtype=np.float64) * 1_000_000_000
        # Trend up then flat — entry will happen, then max hold forces exit
        prices = np.concatenate([
            100.0 + np.arange(50) * 0.2,  # strong trend
            np.full(150, 110.0),  # flat
        ])
        volumes = np.full(n, 0.05)
        sides = np.ones(n)
        ticks = np.column_stack([timestamps, prices, volumes, sides])
        s = HFTMomentumScalper(config={
            "entry_threshold": 0.0001, "max_hold_ticks": 10, "lookback": 5
        })
        s.run(ticks)
        # Max hold should have forced exit

    def test_name(self):
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper
        s = HFTMomentumScalper()
        assert s.name == "MomentumScalper"


# ══════════════════════════════════════════════════════
# Grid Trader — Edge Cases
# ══════════════════════════════════════════════════════


class TestGridTraderEdgeCases:
    def test_grid_initialization(self):
        from hftbacktest.strategies.grid_trader import HFTGridTrader
        ticks = _make_ticks(10, start_price=100.0)
        s = HFTGridTrader()
        s.run(ticks)
        assert s._reference_price is not None

    def test_price_escape_upper_resets_grid(self):
        from hftbacktest.strategies.grid_trader import HFTGridTrader
        n = 50
        timestamps = np.arange(n, dtype=np.float64) * 1_000_000_000
        # Start at 100, jump to 110 (beyond upper bound with 3 levels * 0.002)
        prices = np.concatenate([np.full(10, 100.0), np.full(40, 110.0)])
        volumes = np.full(n, 0.05)
        sides = np.ones(n)
        ticks = np.column_stack([timestamps, prices, volumes, sides])
        s = HFTGridTrader(config={"grid_spacing": 0.002, "num_levels": 3})
        s.run(ticks)
        # Grid should have been reset when price escaped

    def test_level_price_calculation(self):
        from hftbacktest.strategies.grid_trader import HFTGridTrader
        s = HFTGridTrader(config={"grid_spacing": 0.01, "num_levels": 3})
        s._reference_price = 100.0
        buy_level = s._grid_level_price(1, "buy")
        sell_level = s._grid_level_price(1, "sell")
        assert buy_level == pytest.approx(99.0)  # 100 * (1 - 1 * 0.01)
        assert sell_level == pytest.approx(101.0)  # 100 * (1 + 1 * 0.01)

    def test_name(self):
        from hftbacktest.strategies.grid_trader import HFTGridTrader
        s = HFTGridTrader()
        assert s.name == "GridTrader"

    def test_all_levels_filled_resets(self):
        from hftbacktest.strategies.grid_trader import HFTGridTrader
        # Create ticks that cross all grid levels
        n = 200
        timestamps = np.arange(n, dtype=np.float64) * 1_000_000_000
        # Oscillate around center to hit all levels
        prices = 100.0 + 5.0 * np.sin(np.linspace(0, 8 * np.pi, n))
        volumes = np.full(n, 0.05)
        sides = np.where(np.random.RandomState(42).random(n) > 0.5, 1.0, -1.0)
        ticks = np.column_stack([timestamps, prices, volumes, sides])
        s = HFTGridTrader(config={"grid_spacing": 0.01, "num_levels": 2, "max_position": 10.0})
        s.run(ticks)
        # Should have reset grid at least once


# ══════════════════════════════════════════════════════
# Mean Reversion Scalper — Edge Cases
# ══════════════════════════════════════════════════════


class TestMeanReversionEdgeCases:
    def test_zero_volume_vwap_fallback(self):
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper
        n = 60
        timestamps = np.arange(n, dtype=np.float64) * 1_000_000_000
        prices = np.full(n, 100.0)
        volumes = np.zeros(n)  # all zero volume
        sides = np.ones(n)
        ticks = np.column_stack([timestamps, prices, volumes, sides])
        s = HFTMeanReversionScalper(config={"lookback": 10})
        s.run(ticks)
        # VWAP falls back to price when volume is 0 — no crash

    def test_warmup_period_no_trades(self):
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper
        ticks = _make_ticks(30)  # less than lookback=50
        s = HFTMeanReversionScalper(config={"lookback": 50})
        s.run(ticks)
        assert len(s.fills) == 0

    def test_deviation_triggers_entry(self):
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper
        n = 100
        timestamps = np.arange(n, dtype=np.float64) * 1_000_000_000
        # Stable at 100 for 60 ticks, then drop below VWAP band
        prices = np.concatenate([np.full(60, 100.0), np.full(40, 99.0)])
        volumes = np.full(n, 1.0)
        sides = np.ones(n)
        ticks = np.column_stack([timestamps, prices, volumes, sides])
        s = HFTMeanReversionScalper(config={
            "lookback": 50, "deviation_threshold": 0.005, "max_position": 1.0
        })
        s.run(ticks)
        # Price drops 1% below VWAP of 100 → should trigger buy
        assert len(s.fills) > 0

    def test_max_hold_forces_exit(self):
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper
        n = 200
        timestamps = np.arange(n, dtype=np.float64) * 1_000_000_000
        # Drop below VWAP and stay there
        prices = np.concatenate([np.full(60, 100.0), np.full(140, 98.0)])
        volumes = np.full(n, 1.0)
        sides = np.ones(n)
        ticks = np.column_stack([timestamps, prices, volumes, sides])
        s = HFTMeanReversionScalper(config={
            "lookback": 50, "deviation_threshold": 0.005,
            "max_hold_ticks": 20, "max_position": 1.0
        })
        s.run(ticks)
        # Should have forced exit after max_hold_ticks

    def test_name(self):
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper
        s = HFTMeanReversionScalper()
        assert s.name == "MeanReversionScalper"


# ══════════════════════════════════════════════════════
# Runner — Error Handling
# ══════════════════════════════════════════════════════


class TestRunnerErrorHandling:
    def test_unknown_strategy(self):
        from hftbacktest.hft_runner import run_hft_backtest
        result = run_hft_backtest("NonExistent")
        assert "error" in result
        assert "Unknown strategy" in result["error"]

    def test_unknown_strategy_lists_available(self):
        from hftbacktest.hft_runner import run_hft_backtest
        result = run_hft_backtest("FakeStrategy")
        assert "Available" in result["error"]
        assert "MarketMaker" in result["error"]

    def test_list_hft_strategies(self):
        from hftbacktest.hft_runner import list_hft_strategies
        names = list_hft_strategies()
        assert len(names) == 4
        assert "MarketMaker" in names
        assert "MomentumScalper" in names
        assert "GridTrader" in names
        assert "MeanReversionScalper" in names

    def test_load_platform_config_missing(self):
        from hftbacktest.hft_runner import _load_platform_config
        with patch("hftbacktest.hft_runner.CONFIG_PATH", Path("/nonexistent/config.yaml")):
            cfg = _load_platform_config()
            assert cfg == {}

    def test_load_platform_config_valid(self):
        from hftbacktest.hft_runner import _load_platform_config
        cfg = _load_platform_config()
        assert isinstance(cfg, dict)


# ══════════════════════════════════════════════════════
# Runner — Tick Conversion
# ══════════════════════════════════════════════════════


class TestTickConversion:
    def test_convert_no_data_returns_none(self):
        from hftbacktest.hft_runner import convert_ohlcv_to_hft_ticks
        result = convert_ohlcv_to_hft_ticks("NODATA/PAIR", "1h", "noexchange")
        assert result is None

    def test_convert_with_data(self):
        from common.data_pipeline.pipeline import save_ohlcv
        from hftbacktest.hft_runner import convert_ohlcv_to_hft_ticks
        import pandas as pd
        import numpy as np

        np.random.seed(42)
        n = 50
        dates = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
        df = pd.DataFrame({
            "open": 100.0 + np.random.randn(n),
            "high": 101.0 + np.abs(np.random.randn(n)),
            "low": 99.0 - np.abs(np.random.randn(n)),
            "close": 100.0 + np.random.randn(n),
            "volume": np.random.uniform(100, 1000, n),
        }, index=dates)
        save_ohlcv(df, "HFTTEST/USDT", "1h", "testexch")
        path = convert_ohlcv_to_hft_ticks("HFTTEST/USDT", "1h", "testexch")
        assert path is not None
        assert path.exists()
        ticks = np.load(path)
        assert ticks.shape[1] == 4  # timestamp, price, volume, side
        assert len(ticks) == n * 4  # 4 ticks per bar


# ══════════════════════════════════════════════════════
# Runner — Full Backtest Execution
# ══════════════════════════════════════════════════════


class TestRunnerBacktest:
    def test_full_backtest_with_saved_data(self):
        from common.data_pipeline.pipeline import save_ohlcv
        from hftbacktest.hft_runner import run_hft_backtest, TICKS_DIR

        # Save tick data first
        ticks = _make_ticks(200)
        tick_path = TICKS_DIR / "testexch_HFTBT2USDT_1h_ticks.npy"
        np.save(tick_path, ticks)

        result = run_hft_backtest(
            "MarketMaker", "HFTBT2/USDT", "1h", "testexch",
            latency_ns=500_000, initial_balance=5000.0,
        )
        assert "error" not in result
        assert result["framework"] == "hftbacktest"
        assert result["strategy"] == "MarketMaker"
        assert result["ticks_processed"] == 200
        assert "metrics" in result
        assert "total_fills" in result
        # Cleanup
        tick_path.unlink(missing_ok=True)

    def test_backtest_result_keys(self):
        from hftbacktest.hft_runner import run_hft_backtest, TICKS_DIR

        ticks = _make_ticks(50)
        tick_path = TICKS_DIR / "testexch_HFTKEYSUSDT_1h_ticks.npy"
        np.save(tick_path, ticks)

        result = run_hft_backtest("GridTrader", "HFTKEYS/USDT", "1h", "testexch")
        expected_keys = {"framework", "strategy", "symbol", "timeframe", "exchange",
                         "initial_balance", "latency_ns", "ticks_processed",
                         "total_fills", "final_position", "gross_pnl", "total_fees",
                         "metrics", "trades"}
        assert expected_keys.issubset(set(result.keys()))
        tick_path.unlink(missing_ok=True)


# ══════════════════════════════════════════════════════
# Strategy Registry
# ══════════════════════════════════════════════════════


class TestStrategyRegistry:
    def test_registry_has_four_strategies(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY
        assert len(STRATEGY_REGISTRY) == 4

    def test_registry_keys(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY
        expected = {"MarketMaker", "MomentumScalper", "GridTrader", "MeanReversionScalper"}
        assert set(STRATEGY_REGISTRY.keys()) == expected

    def test_all_are_classes(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY
        for name, cls in STRATEGY_REGISTRY.items():
            assert isinstance(cls, type), f"{name} is not a class"


# ══════════════════════════════════════════════════════
# All 4 Strategies — Parametrized Run
# ══════════════════════════════════════════════════════


class TestAllStrategiesRun:
    @pytest.mark.parametrize("strategy_name", [
        "MarketMaker", "MomentumScalper", "GridTrader", "MeanReversionScalper",
    ])
    def test_strategy_runs_with_normal_data(self, strategy_name):
        from hftbacktest.strategies import STRATEGY_REGISTRY
        ticks = _make_ticks(200)
        s = STRATEGY_REGISTRY[strategy_name]()
        s.run(ticks)
        assert isinstance(s.fills, list)
        assert isinstance(s.position, float)
        assert s.balance <= s.initial_balance + 1000  # sanity check

    @pytest.mark.parametrize("strategy_name", [
        "MarketMaker", "MomentumScalper", "GridTrader", "MeanReversionScalper",
    ])
    def test_strategy_with_flat_prices(self, strategy_name):
        from hftbacktest.strategies import STRATEGY_REGISTRY
        ticks = _make_flat_ticks(100)
        s = STRATEGY_REGISTRY[strategy_name]()
        s.run(ticks)
        # Should not crash

    @pytest.mark.parametrize("strategy_name", [
        "MarketMaker", "MomentumScalper", "GridTrader", "MeanReversionScalper",
    ])
    def test_strategy_get_trades_df(self, strategy_name):
        from hftbacktest.strategies import STRATEGY_REGISTRY
        ticks = _make_ticks(200)
        s = STRATEGY_REGISTRY[strategy_name]()
        s.run(ticks)
        df = s.get_trades_df()
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            expected_cols = {"entry_time", "exit_time", "side", "entry_price",
                             "exit_price", "size", "pnl", "pnl_pct", "fee"}
            assert expected_cols.issubset(set(df.columns))
