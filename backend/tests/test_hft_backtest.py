"""
Comprehensive tests for the HFT backtest module (Tier 4)
==========================================================
Covers: strategy imports, interfaces, synthetic data execution,
result persistence (JSON files), error handling, configuration
edge cases, and task registry integration.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Helpers ──────────────────────────────────────────────


def _make_ticks(
    n: int = 100,
    start_price: float = 100.0,
    seed: int = 42,
) -> np.ndarray:
    """Generate synthetic tick data: [timestamp_ns, price, volume, side]."""
    np.random.seed(seed)
    timestamps = np.arange(n, dtype=np.float64) * 1_000_000_000
    prices = start_price + np.cumsum(np.random.normal(0, 0.1, n))
    volumes = np.random.uniform(0.01, 0.1, n)
    sides = np.random.choice([1.0, -1.0], n)
    return np.column_stack([timestamps, prices, volumes, sides])


def _make_trending_ticks(n: int = 200, start_price: float = 100.0, trend: float = 0.05) -> np.ndarray:
    """Generate ticks with a clear trend direction for strategy testing."""
    timestamps = np.arange(n, dtype=np.float64) * 1_000_000_000
    prices = start_price + np.arange(n) * trend + np.random.normal(0, 0.01, n)
    volumes = np.random.uniform(0.01, 0.1, n)
    sides = np.where(np.random.random(n) > 0.5, 1.0, -1.0)
    return np.column_stack([timestamps, prices, volumes, sides])


def _make_mean_reverting_ticks(n: int = 200, center: float = 100.0, amplitude: float = 2.0) -> np.ndarray:
    """Generate ticks that oscillate around a center price."""
    timestamps = np.arange(n, dtype=np.float64) * 1_000_000_000
    prices = center + amplitude * np.sin(np.linspace(0, 8 * np.pi, n))
    volumes = np.random.uniform(0.05, 0.2, n)
    sides = np.where(np.random.random(n) > 0.5, 1.0, -1.0)
    return np.column_stack([timestamps, prices, volumes, sides])


# ── 1. Strategy Import Tests ────────────────────────────


class TestStrategyImports:
    """Test that all 4 strategies are importable from the hftbacktest module."""

    def test_import_market_maker(self):
        from hftbacktest.strategies.market_maker import HFTMarketMaker

        assert HFTMarketMaker is not None

    def test_import_momentum_scalper(self):
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        assert HFTMomentumScalper is not None

    def test_import_grid_trader(self):
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        assert HFTGridTrader is not None

    def test_import_mean_reversion_scalper(self):
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        assert HFTMeanReversionScalper is not None

    def test_import_base_strategy(self):
        from hftbacktest.strategies.base import HFTBaseStrategy

        assert HFTBaseStrategy is not None

    def test_import_strategy_registry(self):
        from hftbacktest.strategies import STRATEGY_REGISTRY

        assert isinstance(STRATEGY_REGISTRY, dict)
        assert len(STRATEGY_REGISTRY) == 4

    def test_import_hft_runner(self):
        from hftbacktest.hft_runner import list_hft_strategies, run_hft_backtest

        assert callable(list_hft_strategies)
        assert callable(run_hft_backtest)


# ── 2. Strategy Interface Tests ─────────────────────────


class TestStrategyInterface:
    """Test that each strategy has the required methods and attributes."""

    STRATEGY_CLASSES = [
        ("MarketMaker", "hftbacktest.strategies.market_maker", "HFTMarketMaker"),
        ("MomentumScalper", "hftbacktest.strategies.momentum_scalper", "HFTMomentumScalper"),
        ("GridTrader", "hftbacktest.strategies.grid_trader", "HFTGridTrader"),
        ("MeanReversionScalper", "hftbacktest.strategies.mean_reversion", "HFTMeanReversionScalper"),
    ]

    @pytest.mark.parametrize("name,module,cls_name", STRATEGY_CLASSES)
    def test_has_on_tick_method(self, name, module, cls_name):
        import importlib

        mod = importlib.import_module(module)
        cls = getattr(mod, cls_name)
        instance = cls()
        assert hasattr(instance, "on_tick")
        assert callable(instance.on_tick)

    @pytest.mark.parametrize("name,module,cls_name", STRATEGY_CLASSES)
    def test_has_run_method(self, name, module, cls_name):
        import importlib

        mod = importlib.import_module(module)
        cls = getattr(mod, cls_name)
        instance = cls()
        assert hasattr(instance, "run")
        assert callable(instance.run)

    @pytest.mark.parametrize("name,module,cls_name", STRATEGY_CLASSES)
    def test_has_submit_order_method(self, name, module, cls_name):
        import importlib

        mod = importlib.import_module(module)
        cls = getattr(mod, cls_name)
        instance = cls()
        assert hasattr(instance, "submit_order")
        assert callable(instance.submit_order)

    @pytest.mark.parametrize("name,module,cls_name", STRATEGY_CLASSES)
    def test_has_get_trades_df_method(self, name, module, cls_name):
        import importlib

        mod = importlib.import_module(module)
        cls = getattr(mod, cls_name)
        instance = cls()
        assert hasattr(instance, "get_trades_df")
        assert callable(instance.get_trades_df)

    @pytest.mark.parametrize("name,module,cls_name", STRATEGY_CLASSES)
    def test_has_check_drawdown_halt_method(self, name, module, cls_name):
        import importlib

        mod = importlib.import_module(module)
        cls = getattr(mod, cls_name)
        instance = cls()
        assert hasattr(instance, "check_drawdown_halt")
        assert callable(instance.check_drawdown_halt)

    @pytest.mark.parametrize("name,module,cls_name", STRATEGY_CLASSES)
    def test_has_name_attribute(self, name, module, cls_name):
        import importlib

        mod = importlib.import_module(module)
        cls = getattr(mod, cls_name)
        instance = cls()
        assert instance.name == name

    @pytest.mark.parametrize("name,module,cls_name", STRATEGY_CLASSES)
    def test_has_required_state_attributes(self, name, module, cls_name):
        import importlib

        mod = importlib.import_module(module)
        cls = getattr(mod, cls_name)
        instance = cls()
        assert hasattr(instance, "position")
        assert hasattr(instance, "gross_pnl")
        assert hasattr(instance, "total_fees")
        assert hasattr(instance, "balance")
        assert hasattr(instance, "fills")
        assert hasattr(instance, "halted")
        assert instance.position == 0.0
        assert instance.gross_pnl == 0.0
        assert instance.halted is False


# ── 3. Strategy with Synthetic Data ─────────────────────


class TestStrategyWithSyntheticData:
    """Test strategy logic with various synthetic tick patterns."""

    def test_market_maker_processes_ticks_and_tracks_state(self):
        """MarketMaker should process ticks and maintain consistent state."""
        from hftbacktest.strategies.market_maker import HFTMarketMaker

        s = HFTMarketMaker(config={
            "half_spread": 0.001,
            "skew_factor": 0.0005,
            "order_size": 0.01,
            "max_position": 10.0,
            "quote_interval": 1,
        })
        ticks = _make_ticks(500)
        s.run(ticks)
        # Strategy should complete and maintain valid state
        assert isinstance(s.fills, list)
        assert isinstance(s.position, float)
        assert abs(s.position) <= s.max_position
        assert s.balance <= s.initial_balance or s.gross_pnl > 0

    def test_market_maker_fills_with_inventory_skew(self):
        """MarketMaker should fill when inventory skew shifts quotes favorably.

        With negative position and positive skew_factor, the inventory_skew term
        becomes negative, shifting bid/ask upward, allowing ask fills.
        """
        from hftbacktest.strategies.market_maker import HFTMarketMaker

        s = HFTMarketMaker(config={
            "half_spread": 0.001,
            "skew_factor": 10.0,  # Extreme skew to force fills
            "order_size": 0.01,
            "max_position": 10.0,
            "quote_interval": 1,
        })
        # Manually set a short position so skew shifts ask down below mid
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.1, "side": "sell"}
        s.submit_order("sell", 100.0, 1.0, tick)
        assert s.position == -1.0

        # Now on_tick: inventory_skew = -1.0 * 10.0 = -10.0
        # ask_price = 100 * 1.001 - (-10) = 100.1 + 10 = 110.1
        # bid_price = 100 * 0.999 - (-10) = 99.9 + 10 = 109.9
        # tick price 100 <= bid 109.9 AND side == "sell" -> buy fill
        buy_tick = {"timestamp": 1e9, "price": 100.0, "volume": 0.1, "side": "sell"}
        s.on_tick(buy_tick)
        assert s.position > -1.0, "Skewed bid should have triggered a buy fill"

    def test_momentum_scalper_trades_on_trending_data(self):
        """MomentumScalper should enter positions on trending data."""
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        s = HFTMomentumScalper(config={
            "lookback": 5,
            "entry_threshold": 0.0001,
            "order_size": 0.01,
            "max_position": 10.0,
        })
        ticks = _make_trending_ticks(200, trend=0.1)
        s.run(ticks)
        assert len(s.fills) > 0, "MomentumScalper should trade on trending data"

    def test_grid_trader_fills_levels_on_oscillating_data(self):
        """GridTrader should fill grid levels when price oscillates."""
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        s = HFTGridTrader(config={
            "grid_spacing": 0.01,
            "num_levels": 3,
            "order_size": 0.01,
            "max_position": 10.0,
        })
        ticks = _make_mean_reverting_ticks(500, center=100.0, amplitude=3.0)
        s.run(ticks)
        assert len(s.fills) > 0, "GridTrader should fill levels on oscillating data"

    def test_mean_reversion_trades_on_oscillating_data(self):
        """MeanReversionScalper should trade when price deviates from VWAP."""
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        s = HFTMeanReversionScalper(config={
            "lookback": 10,
            "deviation_threshold": 0.005,
            "order_size": 0.01,
            "max_position": 10.0,
        })
        ticks = _make_mean_reverting_ticks(300, center=100.0, amplitude=2.0)
        s.run(ticks)
        assert len(s.fills) > 0, "MeanReversionScalper should trade on oscillating data"

    def test_all_strategies_produce_valid_trades_df(self):
        """All strategies should produce a valid trades DataFrame after processing."""
        from hftbacktest.strategies import STRATEGY_REGISTRY

        ticks = _make_mean_reverting_ticks(500, center=100.0, amplitude=5.0)
        for name, cls in STRATEGY_REGISTRY.items():
            s = cls(config={
                "max_position": 10.0,
                "order_size": 0.01,
                # Strategy-specific: wide parameters to encourage fills
                "half_spread": 0.05,
                "quote_interval": 1,
                "lookback": 5,
                "entry_threshold": 0.0001,
                "deviation_threshold": 0.005,
                "grid_spacing": 0.01,
                "num_levels": 3,
            })
            s.run(ticks)
            df = s.get_trades_df()
            # trades_df is either empty or has the expected columns
            if not df.empty:
                assert "entry_price" in df.columns
                assert "exit_price" in df.columns
                assert "pnl" in df.columns
                assert "size" in df.columns
                assert "side" in df.columns

    def test_strategy_run_returns_fills_list(self):
        """run() should return the fills list."""
        from hftbacktest.strategies.market_maker import HFTMarketMaker

        s = HFTMarketMaker(config={"max_position": 10.0})
        ticks = _make_ticks(100)
        result = s.run(ticks)
        assert isinstance(result, list)
        assert result is s.fills


# ── 4. Result Persistence Tests ─────────────────────────


class TestResultPersistence:
    """Test saving and loading backtest results as JSON files."""

    def test_save_result_json(self, tmp_path):
        """Results dict should be serializable to JSON."""
        result = {
            "framework": "hftbacktest",
            "strategy": "MarketMaker",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "exchange": "kraken",
            "initial_balance": 10000.0,
            "latency_ns": 1_000_000,
            "ticks_processed": 400,
            "total_fills": 10,
            "final_position": 0.0,
            "gross_pnl": 5.23,
            "total_fees": 0.42,
            "metrics": {"total_trades": 5, "win_rate": 0.6},
            "trades": [{"entry_price": 100.0, "exit_price": 101.0, "pnl": 0.8}],
        }
        result_path = tmp_path / "test_result.json"
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

        with open(result_path) as f:
            loaded = json.load(f)

        assert loaded["strategy"] == "MarketMaker"
        assert loaded["gross_pnl"] == 5.23
        assert loaded["metrics"]["win_rate"] == 0.6

    def test_load_nonexistent_result(self, tmp_path):
        """Loading a non-existent result should raise FileNotFoundError."""
        path = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError):
            with open(path) as f:
                json.load(f)

    def test_results_dir_exists(self):
        """The hftbacktest results directory should exist."""
        results_dir = PROJECT_ROOT / "hftbacktest" / "results"
        assert results_dir.exists()
        assert results_dir.is_dir()

    def test_serialize_trades_df_round_trip(self):
        """serialize_trades_df should produce JSON-compatible output."""
        from common.metrics.performance import serialize_trades_df

        trades_df = pd.DataFrame({
            "entry_time": pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True),
            "exit_time": pd.to_datetime(["2024-01-01 01:00", "2024-01-02 01:00"], utc=True),
            "side": ["buy", "sell"],
            "entry_price": [100.0, 110.0],
            "exit_price": [105.0, 108.0],
            "size": [0.01, 0.01],
            "pnl": [0.05, -0.02],
            "pnl_pct": [0.05, -0.018],
            "fee": [0.002, 0.002],
        })
        serialized = serialize_trades_df(trades_df)
        assert isinstance(serialized, list)
        assert len(serialized) == 2
        # Should be JSON-serializable
        json_str = json.dumps(serialized)
        reloaded = json.loads(json_str)
        assert reloaded[0]["entry_price"] == 100.0

    def test_serialize_empty_trades_df(self):
        """serialize_trades_df should return empty list for empty DataFrame."""
        from common.metrics.performance import serialize_trades_df

        result = serialize_trades_df(pd.DataFrame())
        assert result == []


# ── 5. Error Handling Tests ─────────────────────────────


class TestErrorHandling:
    """Test behavior with invalid, empty, and corrupt data."""

    def test_empty_ticks_array(self):
        """Strategy should handle empty tick array without crashing."""
        from hftbacktest.strategies.market_maker import HFTMarketMaker

        s = HFTMarketMaker()
        empty_ticks = np.empty((0, 4), dtype=np.float64)
        s.run(empty_ticks)
        assert len(s.fills) == 0
        assert s.position == 0.0

    def test_single_tick(self):
        """Strategy should handle a single tick without crashing."""
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        s = HFTMomentumScalper()
        single_tick = np.array([[1e9, 100.0, 0.1, 1.0]])
        s.run(single_tick)
        assert s.position == 0.0  # Not enough data to enter

    def test_nan_prices_in_ticks(self):
        """Strategy should not crash on NaN prices (may not trade)."""
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        s = HFTGridTrader(config={"max_position": 10.0})
        ticks = _make_ticks(50)
        ticks[10, 1] = np.nan  # Insert NaN price
        # Should not raise, even if behavior is undefined on NaN
        try:
            s.run(ticks)
        except (ValueError, FloatingPointError):
            pass  # Acceptable to raise on NaN, but should not crash with unhandled exception

    def test_zero_volume_ticks(self):
        """Strategy should handle zero-volume ticks."""
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        s = HFTMeanReversionScalper(config={"max_position": 10.0})
        ticks = _make_ticks(100)
        ticks[:, 2] = 0.0  # Zero all volumes
        s.run(ticks)
        # Should complete without division-by-zero crash

    def test_negative_prices(self):
        """Strategy should handle negative prices without crashing."""
        from hftbacktest.strategies.market_maker import HFTMarketMaker

        s = HFTMarketMaker(config={"max_position": 10.0})
        ticks = _make_ticks(50, start_price=-10.0)
        s.run(ticks)
        # Not expected to trade sensibly but should not raise

    def test_run_hft_backtest_unknown_strategy(self):
        """run_hft_backtest should return error for unknown strategy."""
        from hftbacktest.hft_runner import run_hft_backtest

        # Patch tick file existence to avoid actual data loading
        with patch("hftbacktest.hft_runner.TICKS_DIR", Path(tempfile.mkdtemp())):
            result = run_hft_backtest("NonexistentStrategy")
            assert "error" in result
            assert "Unknown strategy" in result["error"]

    def test_halted_strategy_stops_processing(self):
        """Strategy halted mid-run should stop processing further ticks."""
        from hftbacktest.strategies.base import HFTBaseStrategy

        class TestStrategy(HFTBaseStrategy):
            name = "test"
            tick_count = 0

            def on_tick(self, tick):
                self.tick_count += 1
                if self.tick_count == 5:
                    self.halted = True

        s = TestStrategy()
        ticks = _make_ticks(100)
        s.run(ticks)
        assert s.tick_count == 5  # Should stop at 5


# ── 6. Configuration Tests ─────────────────────────────


class TestConfiguration:
    """Test strategy parameter validation and configuration handling."""

    def test_default_config(self):
        """Strategy with None config should use defaults."""
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config=None)
        assert s.initial_balance == 10000.0
        assert s.max_position == 1.0
        assert s.fee_rate == 0.0002

    def test_empty_config(self):
        """Strategy with empty config should use defaults."""
        from hftbacktest.strategies.market_maker import HFTMarketMaker

        s = HFTMarketMaker(config={})
        assert s.half_spread == 0.001
        assert s.skew_factor == 0.0005
        assert s.order_size == 0.01

    def test_custom_config_overrides(self):
        """Custom config values should override defaults."""
        from hftbacktest.strategies.market_maker import HFTMarketMaker

        cfg = {
            "half_spread": 0.005,
            "skew_factor": 0.001,
            "order_size": 0.05,
            "max_position": 5.0,
            "initial_balance": 50000.0,
            "fee_rate": 0.001,
            "drawdown_halt_pct": 0.10,
        }
        s = HFTMarketMaker(config=cfg)
        assert s.half_spread == 0.005
        assert s.skew_factor == 0.001
        assert s.order_size == 0.05
        assert s.max_position == 5.0
        assert s.initial_balance == 50000.0
        assert s.fee_rate == 0.001
        assert s.drawdown_halt_pct == 0.10

    def test_grid_trader_custom_levels(self):
        """GridTrader should respect num_levels and grid_spacing config."""
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        s = HFTGridTrader(config={"num_levels": 5, "grid_spacing": 0.005})
        assert s.num_levels == 5
        assert s.grid_spacing == 0.005

    def test_momentum_scalper_custom_lookback(self):
        """MomentumScalper alpha should change with lookback."""
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        s10 = HFTMomentumScalper(config={"lookback": 10})
        s50 = HFTMomentumScalper(config={"lookback": 50})
        assert s10._alpha > s50._alpha  # Shorter lookback = higher alpha

    def test_mean_reversion_custom_lookback(self):
        """MeanReversionScalper should respect lookback for VWAP window."""
        from hftbacktest.strategies.mean_reversion import HFTMeanReversionScalper

        s = HFTMeanReversionScalper(config={"lookback": 25})
        assert s.lookback == 25
        assert s._price_volume_window.maxlen == 25

    def test_latency_config(self):
        """Latency config should be respected."""
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config={"latency_ns": 5_000_000})
        assert s.latency_ns == 5_000_000

    def test_zero_fee_rate(self):
        """Zero fee rate should result in no fees being charged."""
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config={"fee_rate": 0.0})
        tick = {"timestamp": 1000, "price": 100.0, "volume": 0.1, "side": "sell"}
        s.submit_order("buy", 100.0, 0.5, tick)
        assert s.total_fees == 0.0
        assert s.fills[0]["fee"] == 0.0


# ── 7. Task Registry Integration Tests ─────────────────


class TestTaskRegistryIntegration:
    """Test that the hft_backtest executor exists and works."""

    def test_hft_backtest_in_task_registry(self):
        from core.services.task_registry import TASK_REGISTRY

        assert "hft_backtest" in TASK_REGISTRY

    def test_hft_backtest_executor_is_callable(self):
        from core.services.task_registry import TASK_REGISTRY

        assert callable(TASK_REGISTRY["hft_backtest"])

    @patch("core.platform_bridge.get_platform_config")
    @patch("core.platform_bridge.ensure_platform_imports")
    def test_hft_backtest_executor_no_watchlist(self, mock_imports, mock_config):
        """Executor should return skipped when no watchlist is configured."""
        from core.services.task_registry import TASK_REGISTRY

        mock_config.return_value = {"data": {"watchlist": []}}
        progress = MagicMock()
        result = TASK_REGISTRY["hft_backtest"]({}, progress)
        assert result["status"] == "skipped"
        assert "watchlist" in result["reason"].lower()

    def test_list_hft_strategies_returns_all_four(self):
        """list_hft_strategies should return all 4 registered strategy names."""
        from hftbacktest.hft_runner import list_hft_strategies

        names = list_hft_strategies()
        assert len(names) == 4
        assert set(names) == {"MarketMaker", "MomentumScalper", "GridTrader", "MeanReversionScalper"}


# ── 8. Performance Metrics Integration ──────────────────


class TestPerformanceMetrics:
    """Test that strategy output integrates correctly with compute_performance_metrics."""

    def test_metrics_from_strategy_fills(self):
        """Full pipeline: strategy -> trades_df -> metrics."""
        from common.metrics.performance import compute_performance_metrics
        from hftbacktest.strategies.momentum_scalper import HFTMomentumScalper

        s = HFTMomentumScalper(config={
            "lookback": 5,
            "entry_threshold": 0.0001,
            "max_position": 10.0,
            "order_size": 0.01,
        })
        ticks = _make_trending_ticks(200, trend=0.1)
        s.run(ticks)
        df = s.get_trades_df()
        if not df.empty:
            metrics = compute_performance_metrics(df)
            assert "total_trades" in metrics
            assert "total_pnl" in metrics
            assert "win_rate" in metrics
            assert "sharpe_ratio" in metrics
            assert "max_drawdown" in metrics
            assert isinstance(metrics["total_trades"], int)
            assert 0.0 <= metrics["win_rate"] <= 1.0

    def test_metrics_from_empty_trades(self):
        """compute_performance_metrics on empty DataFrame returns error message."""
        from common.metrics.performance import compute_performance_metrics

        metrics = compute_performance_metrics(pd.DataFrame())
        assert "error" in metrics


# ── 9. Additional Edge Cases ────────────────────────────


class TestEdgeCases:
    """Additional edge case tests."""

    def test_very_large_tick_count(self):
        """Strategy should handle a large number of ticks."""
        from hftbacktest.strategies.market_maker import HFTMarketMaker

        s = HFTMarketMaker(config={"max_position": 100.0, "quote_interval": 1})
        ticks = _make_ticks(10_000, seed=99)
        s.run(ticks)
        # Should complete without error or memory issues

    def test_position_tracks_correctly_after_many_trades(self):
        """Position should remain consistent after many buy/sell cycles."""
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config={"max_position": 100.0, "fee_rate": 0.0})
        tick = {"timestamp": 0, "price": 100.0, "volume": 0.1, "side": "sell"}
        # Do 100 buy/sell round trips
        for i in range(100):
            s.submit_order("buy", 100.0, 0.01, tick)
            s.submit_order("sell", 100.0, 0.01, tick)
        assert s.position == pytest.approx(0.0, abs=1e-10)

    def test_drawdown_threshold_boundary(self):
        """Drawdown exactly at threshold should trigger halt."""
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config={"initial_balance": 100.0})
        s.balance = 95.0  # Exactly 5% drawdown
        assert s.check_drawdown_halt(0.05) is True
        assert s.halted is True

    def test_drawdown_below_threshold_no_halt(self):
        """Drawdown below threshold should not halt."""
        from hftbacktest.strategies.base import HFTBaseStrategy

        s = HFTBaseStrategy(config={"initial_balance": 100.0})
        s.balance = 96.0  # 4% drawdown, below 5% threshold
        assert s.check_drawdown_halt(0.05) is False
        assert s.halted is False

    def test_grid_level_price_calculation(self):
        """Grid level price computation should be mathematically correct."""
        from hftbacktest.strategies.grid_trader import HFTGridTrader

        s = HFTGridTrader(config={"grid_spacing": 0.01, "num_levels": 3})
        s._reference_price = 100.0
        buy_1 = s._grid_level_price(1, "buy")
        sell_1 = s._grid_level_price(1, "sell")
        assert buy_1 == pytest.approx(99.0)   # 100 * (1 - 0.01)
        assert sell_1 == pytest.approx(101.0)  # 100 * (1 + 0.01)

    def test_load_platform_config_missing_file(self):
        """_load_platform_config should return empty dict when file is missing."""
        from hftbacktest.hft_runner import _load_platform_config

        with patch("hftbacktest.hft_runner.CONFIG_PATH", Path("/nonexistent/config.yaml")):
            config = _load_platform_config()
            assert config == {}
