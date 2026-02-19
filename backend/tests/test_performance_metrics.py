"""
Tests for common.metrics.performance module.
Covers serialize_trades_df() and compute_performance_metrics().
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.metrics.performance import compute_performance_metrics, serialize_trades_df  # noqa: E402, I001


# ── serialize_trades_df ────────────────────────────────────────────


class TestSerializeTradesDf:
    def test_empty_dataframe_returns_empty_list(self):
        df = pd.DataFrame()
        assert serialize_trades_df(df) == []

    def test_normal_trades_with_timestamps(self):
        df = pd.DataFrame(
            {
                "entry_time": pd.to_datetime(["2025-01-01", "2025-01-02"]),
                "exit_time": pd.to_datetime(["2025-01-01 12:00", "2025-01-02 12:00"]),
                "pnl": [100.0, -50.0],
                "pnl_pct": [0.01, -0.005],
                "side": ["long", "short"],
            }
        )
        result = serialize_trades_df(df)
        assert len(result) == 2
        # Timestamps should be strings, not Timestamp objects
        assert isinstance(result[0]["entry_time"], str)
        assert isinstance(result[0]["exit_time"], str)
        assert result[0]["pnl"] == 100.0
        assert result[1]["side"] == "short"

    def test_missing_time_columns(self):
        """DataFrame without entry_time/exit_time should still serialize."""
        df = pd.DataFrame({"pnl": [10, 20], "side": ["long", "long"]})
        result = serialize_trades_df(df)
        assert len(result) == 2
        assert result[0]["pnl"] == 10

    def test_preserves_numeric_types(self):
        df = pd.DataFrame(
            {
                "entry_time": pd.to_datetime(["2025-01-01"]),
                "exit_time": pd.to_datetime(["2025-01-02"]),
                "pnl": [123.456],
                "pnl_pct": [0.0123],
            }
        )
        result = serialize_trades_df(df)
        assert result[0]["pnl"] == 123.456
        assert result[0]["pnl_pct"] == 0.0123

    def test_does_not_mutate_original(self):
        df = pd.DataFrame(
            {
                "entry_time": pd.to_datetime(["2025-01-01"]),
                "exit_time": pd.to_datetime(["2025-01-02"]),
                "pnl": [100.0],
            }
        )
        original_dtype = df["entry_time"].dtype
        serialize_trades_df(df)
        assert df["entry_time"].dtype == original_dtype

    def test_only_entry_time_column(self):
        """DataFrame with only entry_time (no exit_time) should convert that column."""
        df = pd.DataFrame(
            {
                "entry_time": pd.to_datetime(["2025-03-01"]),
                "pnl": [50.0],
            }
        )
        result = serialize_trades_df(df)
        assert isinstance(result[0]["entry_time"], str)


# ── compute_performance_metrics ────────────────────────────────────


class TestComputePerformanceMetrics:
    def test_empty_dataframe_returns_error(self):
        df = pd.DataFrame()
        result = compute_performance_metrics(df)
        assert result == {"error": "No trades to analyze"}

    def test_all_winners(self):
        df = pd.DataFrame(
            {
                "entry_time": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
                "exit_time": pd.to_datetime(
                    ["2025-01-01 12:00", "2025-01-02 12:00", "2025-01-03 12:00"]
                ),
                "pnl": [100.0, 200.0, 50.0],
                "pnl_pct": [0.01, 0.02, 0.005],
                "side": ["long", "long", "long"],
            }
        )
        result = compute_performance_metrics(df)
        assert result["total_trades"] == 3
        assert result["total_pnl"] == 350.0
        assert result["win_rate"] == 1.0
        assert result["profit_factor"] == float("inf")
        assert result["best_trade"] == 200.0
        assert result["worst_trade"] == 50.0

    def test_mixed_winners_and_losers(self):
        df = pd.DataFrame(
            {
                "entry_time": pd.to_datetime(["2025-01-01", "2025-01-02"]),
                "exit_time": pd.to_datetime(["2025-01-01 12:00", "2025-01-02 12:00"]),
                "pnl": [100.0, -50.0],
                "pnl_pct": [0.01, -0.005],
                "side": ["long", "short"],
            }
        )
        result = compute_performance_metrics(df)
        assert result["total_trades"] == 2
        assert result["total_pnl"] == 50.0
        assert result["win_rate"] == 0.5
        assert result["profit_factor"] == 2.0
        assert result["avg_win"] == 100.0
        assert result["avg_loss"] == -50.0

    def test_max_drawdown_computation(self):
        df = pd.DataFrame(
            {
                "entry_time": pd.to_datetime(
                    ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"]
                ),
                "exit_time": pd.to_datetime(
                    ["2025-01-01 12:00", "2025-01-02 12:00", "2025-01-03 12:00", "2025-01-04 12:00"]
                ),
                "pnl": [100.0, -200.0, -50.0, 300.0],
                "pnl_pct": [0.01, -0.02, -0.005, 0.03],
                "side": ["long", "long", "long", "long"],
            }
        )
        result = compute_performance_metrics(df)
        # cumulative: 100, -100, -150, 150
        # running_max: 100, 100, 100, 150
        # drawdown: 0, -200, -250, 0
        assert result["max_drawdown"] == -250.0

    def test_sharpe_ratio_computed(self):
        np.random.seed(42)
        n = 50
        df = pd.DataFrame(
            {
                "entry_time": pd.date_range("2025-01-01", periods=n, freq="D"),
                "exit_time": pd.date_range("2025-01-01 12:00", periods=n, freq="D"),
                "pnl": np.random.normal(10, 5, n),
                "pnl_pct": np.random.normal(0.01, 0.005, n),
                "side": ["long"] * n,
            }
        )
        result = compute_performance_metrics(df)
        # Sharpe should be a finite number for this distribution
        assert isinstance(result["sharpe_ratio"], float)
        assert not np.isnan(result["sharpe_ratio"])

    def test_without_pnl_pct_column(self):
        df = pd.DataFrame(
            {
                "entry_time": pd.to_datetime(["2025-01-01"]),
                "exit_time": pd.to_datetime(["2025-01-02"]),
                "pnl": [100.0],
                "side": ["long"],
            }
        )
        result = compute_performance_metrics(df)
        assert result["sharpe_ratio"] == 0
        assert result["total_pnl"] == 100.0

    def test_avg_trade_duration(self):
        df = pd.DataFrame(
            {
                "entry_time": pd.to_datetime(["2025-01-01 00:00", "2025-01-02 00:00"]),
                "exit_time": pd.to_datetime(["2025-01-01 06:00", "2025-01-02 12:00"]),
                "pnl": [10.0, 20.0],
                "pnl_pct": [0.001, 0.002],
                "side": ["long", "long"],
            }
        )
        result = compute_performance_metrics(df)
        assert result["avg_trade_duration"] != "N/A"
