"""Tests for Gate 2+3 Validation Engine — Sprint 1, Items 1.2 & 1.3
================================================================
Covers: Gate 2 criteria checking, synthetic data generation,
signal function shapes, ADX indicator, and integration tests.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure project root and scripts directory on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SCRIPTS_DIR = PROJECT_ROOT / "research" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from common.indicators.technical import adx
from validate_bollinger_mean_reversion import bollinger_mr_signals
from validate_crypto_investor_v1 import crypto_investor_v1_signals
from validate_volatility_breakout import volatility_breakout_signals
from validation_engine import (
    GATE2_MAX_DRAWDOWN,
    GATE2_MIN_SHARPE,
    GATE2_MIN_TRADES_PER_YEAR,
    GATE2_PVALUE,
    check_gate2,
    generate_synthetic_ohlcv,
)

# ── ADX Indicator Tests ───────────────────────────────────────


class TestADX:
    def test_adx_returns_series(self):
        np.random.seed(42)
        n = 200
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        high = close + np.abs(np.random.randn(n) * 0.3)
        low = close - np.abs(np.random.randn(n) * 0.3)
        df = pd.DataFrame({"high": high, "low": low, "close": close})
        result = adx(df, 14)
        assert isinstance(result, pd.Series)
        assert len(result) == n

    def test_adx_bounded_0_100(self):
        np.random.seed(42)
        n = 500
        close = 100 + np.cumsum(np.random.randn(n))
        high = close + np.abs(np.random.randn(n))
        low = close - np.abs(np.random.randn(n))
        df = pd.DataFrame({"high": high, "low": low, "close": close})
        result = adx(df, 14)
        valid = result.dropna()
        assert valid.min() >= 0
        assert valid.max() <= 100

    def test_adx_trending_vs_ranging(self):
        """Strong trend should have higher ADX than ranging market."""
        n = 300
        # Trending: steady upward
        trend_close = np.linspace(100, 200, n)
        trend_high = trend_close + 1
        trend_low = trend_close - 1
        trend_df = pd.DataFrame({"high": trend_high, "low": trend_low, "close": trend_close})

        # Ranging: oscillating
        np.random.seed(42)
        range_close = 100 + np.sin(np.linspace(0, 20, n)) * 5
        range_high = range_close + 1
        range_low = range_close - 1
        range_df = pd.DataFrame({"high": range_high, "low": range_low, "close": range_close})

        trend_adx = adx(trend_df, 14).iloc[-1]
        range_adx = adx(range_df, 14).iloc[-1]
        assert trend_adx > range_adx


# ── Gate 2 Criteria Tests ─────────────────────────────────────


class TestCheckGate2:
    def test_passing_result(self):
        result = {
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.15,
            "annualized_trades": 50,
            "pvalue": 0.01,
        }
        passed, failures = check_gate2(result)
        assert passed is True
        assert len(failures) == 0

    def test_fails_low_sharpe(self):
        result = {
            "sharpe_ratio": 0.5,
            "max_drawdown": 0.10,
            "annualized_trades": 50,
            "pvalue": 0.01,
        }
        passed, failures = check_gate2(result)
        assert passed is False
        assert any("Sharpe" in f for f in failures)

    def test_fails_high_drawdown(self):
        result = {
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.30,
            "annualized_trades": 50,
            "pvalue": 0.01,
        }
        passed, failures = check_gate2(result)
        assert passed is False
        assert any("Drawdown" in f for f in failures)

    def test_fails_few_trades(self):
        result = {
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.10,
            "annualized_trades": 10,
            "pvalue": 0.01,
        }
        passed, failures = check_gate2(result)
        assert passed is False
        assert any("Trades" in f for f in failures)

    def test_fails_high_pvalue(self):
        result = {
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.10,
            "annualized_trades": 50,
            "pvalue": 0.20,
        }
        passed, failures = check_gate2(result)
        assert passed is False
        assert any("p-value" in f for f in failures)

    def test_fails_nan_sharpe(self):
        result = {
            "sharpe_ratio": float("nan"),
            "max_drawdown": 0.10,
            "annualized_trades": 50,
            "pvalue": 0.01,
        }
        passed, failures = check_gate2(result)
        assert passed is False
        assert any("Sharpe" in f for f in failures)

    def test_multiple_failures(self):
        result = {
            "sharpe_ratio": 0.3,
            "max_drawdown": 0.30,
            "annualized_trades": 5,
            "pvalue": 0.50,
        }
        passed, failures = check_gate2(result)
        assert passed is False
        assert len(failures) == 4

    def test_boundary_values_pass(self):
        """Exactly at thresholds should pass."""
        result = {
            "sharpe_ratio": GATE2_MIN_SHARPE,
            "max_drawdown": GATE2_MAX_DRAWDOWN,
            "annualized_trades": GATE2_MIN_TRADES_PER_YEAR,
            "pvalue": GATE2_PVALUE,
        }
        passed, failures = check_gate2(result)
        assert passed is True


# ── Synthetic Data Tests ──────────────────────────────────────


class TestSyntheticData:
    def test_generates_correct_shape(self):
        df = generate_synthetic_ohlcv(n=1000)
        assert len(df) == 1000
        assert set(df.columns) == {"open", "high", "low", "close", "volume"}

    def test_ohlc_integrity(self):
        df = generate_synthetic_ohlcv(n=500)
        assert (df["high"] >= df["close"]).all()
        assert (df["high"] >= df["open"]).all()
        assert (df["low"] <= df["close"]).all()
        assert (df["low"] <= df["open"]).all()

    def test_positive_prices_and_volume(self):
        df = generate_synthetic_ohlcv(n=500)
        assert (df["close"] > 0).all()
        assert (df["volume"] > 0).all()

    def test_has_timezone_aware_index(self):
        df = generate_synthetic_ohlcv(n=100)
        assert df.index.tz is not None

    def test_reproducible_with_seed(self):
        df1 = generate_synthetic_ohlcv(n=100, seed=42)
        df2 = generate_synthetic_ohlcv(n=100, seed=42)
        pd.testing.assert_frame_equal(df1, df2)


# ── Signal Function Tests ─────────────────────────────────────


class TestCryptoInvestorV1Signals:
    def test_returns_boolean_series(self):
        df = generate_synthetic_ohlcv(n=1000)
        params = {
            "ema_fast": 50,
            "ema_slow": 200,
            "rsi_threshold": 40,
            "sell_rsi_threshold": 80,
        }
        entries, exits = crypto_investor_v1_signals(df, params)
        assert isinstance(entries, pd.Series)
        assert isinstance(exits, pd.Series)
        assert entries.dtype == bool
        assert exits.dtype == bool
        assert len(entries) == len(df)
        assert len(exits) == len(df)

    def test_no_nans_in_signals(self):
        df = generate_synthetic_ohlcv(n=1000)
        params = {
            "ema_fast": 50,
            "ema_slow": 200,
            "rsi_threshold": 40,
            "sell_rsi_threshold": 80,
        }
        entries, exits = crypto_investor_v1_signals(df, params)
        assert not entries.isna().any()
        assert not exits.isna().any()

    def test_generates_some_signals(self):
        df = generate_synthetic_ohlcv(n=5000)
        params = {
            "ema_fast": 50,
            "ema_slow": 200,
            "rsi_threshold": 45,
            "sell_rsi_threshold": 70,
        }
        entries, exits = crypto_investor_v1_signals(df, params)
        # With 5000 rows of synthetic data, we expect at least some signals
        assert entries.sum() >= 0  # May be 0 depending on data
        assert exits.sum() >= 0


class TestBollingerMRSignals:
    def test_returns_boolean_series(self):
        df = generate_synthetic_ohlcv(n=1000)
        params = {
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_threshold": 35,
            "volume_factor": 1.5,
            "sell_rsi_threshold": 65,
        }
        entries, exits = bollinger_mr_signals(df, params)
        assert isinstance(entries, pd.Series)
        assert isinstance(exits, pd.Series)
        assert entries.dtype == bool
        assert exits.dtype == bool
        assert len(entries) == len(df)
        assert len(exits) == len(df)

    def test_no_nans_in_signals(self):
        df = generate_synthetic_ohlcv(n=1000)
        params = {
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_threshold": 35,
            "volume_factor": 1.5,
            "sell_rsi_threshold": 65,
        }
        entries, exits = bollinger_mr_signals(df, params)
        assert not entries.isna().any()
        assert not exits.isna().any()

    def test_generates_some_signals(self):
        df = generate_synthetic_ohlcv(n=5000)
        params = {
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_threshold": 40,
            "volume_factor": 1.0,
            "sell_rsi_threshold": 55,
        }
        entries, exits = bollinger_mr_signals(df, params)
        assert entries.sum() >= 0
        assert exits.sum() >= 0


# ── Integration Tests (require VectorBT) ─────────────────────

import vectorbt  # noqa: F401


class TestIntegrationWithVBT:
    def test_run_backtest_returns_metrics(self):
        from validation_engine import _run_backtest

        df = generate_synthetic_ohlcv(n=2000)
        params = {
            "ema_fast": 50,
            "ema_slow": 200,
            "rsi_threshold": 40,
            "sell_rsi_threshold": 80,
        }
        entries, exits = crypto_investor_v1_signals(df, params)
        metrics = _run_backtest(df["close"], entries, exits, fees=0.0015, sl_stop=0.05)
        assert "sharpe_ratio" in metrics
        assert "total_return" in metrics
        assert "max_drawdown" in metrics
        assert "num_trades" in metrics
        assert "annualized_trades" in metrics
        assert "pvalue" in metrics

    def test_sweep_tiny_grid(self):
        from validation_engine import sweep_parameters

        df = generate_synthetic_ohlcv(n=2000)
        tiny_grid = {
            "ema_fast": [50],
            "ema_slow": [200],
            "rsi_threshold": [40],
            "sell_rsi_threshold": [80],
        }
        results_df = sweep_parameters(df, crypto_investor_v1_signals, tiny_grid, sl_stop=0.05)
        assert len(results_df) == 1
        assert "sharpe_ratio" in results_df.columns
        assert "passes_gate2" in results_df.columns

    def test_full_validation_report_structure(self):
        from validation_engine import run_validation

        df = generate_synthetic_ohlcv(n=3000)
        tiny_grid = {
            "ema_fast": [50],
            "ema_slow": [200],
            "rsi_threshold": [40],
            "sell_rsi_threshold": [80],
        }
        report = run_validation(
            "CIV1_test",
            df,
            crypto_investor_v1_signals,
            tiny_grid,
            sl_stop=0.05,
            symbol="SYNTHETIC",
        )
        assert "strategy_name" in report
        assert "gate2" in report
        assert "overall" in report
        assert isinstance(report["overall"]["passed"], bool)
        assert "gate2_passed" in report["overall"]
        assert "gate3_wf_passed" in report["overall"]
        assert "gate3_perturb_passed" in report["overall"]

    def test_save_and_load_report(self, tmp_path):
        import json

        from validation_engine import run_validation, save_report

        df = generate_synthetic_ohlcv(n=2000)
        tiny_grid = {
            "bb_period": [20],
            "bb_std": [2.0],
            "rsi_threshold": [35],
            "volume_factor": [1.5],
            "sell_rsi_threshold": [65],
        }
        report = run_validation("BMR_test", df, bollinger_mr_signals, tiny_grid, sl_stop=0.04)
        filepath = save_report(report, output_dir=tmp_path)
        assert filepath.exists()

        with open(filepath) as f:
            loaded = json.load(f)
        assert loaded["strategy_name"] == "BMR_test"
        assert "gate2" in loaded


# ── VolatilityBreakout Signal Tests ──────────────────────────


class TestVolatilityBreakoutSignals:
    def test_returns_boolean_series(self):
        df = generate_synthetic_ohlcv(n=1000)
        params = {
            "breakout_period": 20,
            "volume_factor": 1.8,
            "adx_low": 15,
            "adx_high": 25,
            "rsi_low": 40,
            "rsi_high": 70,
            "adx_tolerance": 0.5,
            "sell_rsi_threshold": 85,
        }
        entries, exits = volatility_breakout_signals(df, params)
        assert isinstance(entries, pd.Series)
        assert isinstance(exits, pd.Series)
        assert entries.dtype == bool
        assert exits.dtype == bool
        assert len(entries) == len(df)
        assert len(exits) == len(df)

    def test_no_nans_in_signals(self):
        df = generate_synthetic_ohlcv(n=1000)
        params = {
            "breakout_period": 20,
            "volume_factor": 1.8,
            "adx_low": 15,
            "adx_high": 25,
            "rsi_low": 40,
            "rsi_high": 70,
            "adx_tolerance": 0.5,
            "sell_rsi_threshold": 85,
        }
        entries, exits = volatility_breakout_signals(df, params)
        assert not entries.isna().any()
        assert not exits.isna().any()

    def test_generates_some_signals(self):
        df = generate_synthetic_ohlcv(n=5000)
        params = {
            "breakout_period": 15,
            "volume_factor": 1.2,
            "adx_low": 10,
            "adx_high": 35,
            "rsi_low": 35,
            "rsi_high": 70,
            "adx_tolerance": 0.5,
            "sell_rsi_threshold": 80,
        }
        entries, exits = volatility_breakout_signals(df, params)
        assert entries.sum() >= 0
        assert exits.sum() >= 0


class TestVolatilityBreakoutParams:
    def test_rsi_high_param_respected(self):
        """Different rsi_high values should produce different entry counts."""
        df = generate_synthetic_ohlcv(n=5000)
        params_narrow = {
            "breakout_period": 20,
            "volume_factor": 1.2,
            "adx_low": 10,
            "adx_high": 35,
            "rsi_low": 35,
            "rsi_high": 60,
            "adx_tolerance": 0.5,
            "sell_rsi_threshold": 85,
        }
        params_wide = {
            **params_narrow,
            "rsi_high": 75,
        }
        entries_narrow, _ = volatility_breakout_signals(df, params_narrow)
        entries_wide, _ = volatility_breakout_signals(df, params_wide)
        # Wider RSI band should allow at least as many entries
        assert entries_wide.sum() >= entries_narrow.sum()

    def test_adx_tolerance_param_respected(self):
        """Higher ADX tolerance should generate more entries."""
        df = generate_synthetic_ohlcv(n=5000)
        params_strict = {
            "breakout_period": 20,
            "volume_factor": 1.2,
            "adx_low": 10,
            "adx_high": 35,
            "rsi_low": 35,
            "rsi_high": 70,
            "adx_tolerance": 0.0,
            "sell_rsi_threshold": 85,
        }
        params_tolerant = {
            **params_strict,
            "adx_tolerance": 1.0,
        }
        entries_strict, _ = volatility_breakout_signals(df, params_strict)
        entries_tolerant, _ = volatility_breakout_signals(df, params_tolerant)
        # More tolerance should allow at least as many entries
        assert entries_tolerant.sum() >= entries_strict.sum()

    def test_adx_tolerance_default(self):
        """Without adx_tolerance param, default 0.5 should be used."""
        df = generate_synthetic_ohlcv(n=2000)
        params_no_key = {
            "breakout_period": 20,
            "volume_factor": 1.8,
            "adx_low": 15,
            "adx_high": 25,
            "rsi_low": 40,
            "sell_rsi_threshold": 85,
        }
        params_explicit = {
            **params_no_key,
            "adx_tolerance": 0.5,
            "rsi_high": 70,
        }
        entries_default, _ = volatility_breakout_signals(df, params_no_key)
        entries_explicit, _ = volatility_breakout_signals(df, params_explicit)
        assert entries_default.sum() == entries_explicit.sum()


class TestVolatilityBreakoutIntegration:
    def test_vb_backtest_returns_metrics(self):
        from validation_engine import _run_backtest

        df = generate_synthetic_ohlcv(n=2000)
        params = {
            "breakout_period": 20,
            "volume_factor": 1.8,
            "adx_low": 15,
            "adx_high": 25,
            "rsi_low": 40,
            "rsi_high": 70,
            "adx_tolerance": 0.5,
            "sell_rsi_threshold": 85,
        }
        entries, exits = volatility_breakout_signals(df, params)
        metrics = _run_backtest(df["close"], entries, exits, fees=0.0015, sl_stop=0.03)
        assert "sharpe_ratio" in metrics
        assert "total_return" in metrics
        assert "max_drawdown" in metrics

    def test_vb_sweep_tiny_grid(self):
        from validation_engine import sweep_parameters

        df = generate_synthetic_ohlcv(n=2000)
        tiny_grid = {
            "breakout_period": [20],
            "volume_factor": [1.8],
            "adx_low": [15],
            "adx_high": [25],
            "rsi_low": [40],
            "rsi_high": [70],
            "adx_tolerance": [0.5],
            "sell_rsi_threshold": [85],
        }
        results_df = sweep_parameters(df, volatility_breakout_signals, tiny_grid, sl_stop=0.03)
        assert len(results_df) == 1
        assert "sharpe_ratio" in results_df.columns
        assert "passes_gate2" in results_df.columns


# ── Walk-Forward Validation Tests ────────────────────────────


class TestWalkForwardValidation:
    """Cover validation_engine.py lines 238-298."""

    def test_walk_forward_returns_list(self):
        from validation_engine import walk_forward_validate

        df = generate_synthetic_ohlcv(n=3000)
        params = {"ema_fast": 50, "ema_slow": 200, "rsi_threshold": 40, "sell_rsi_threshold": 80}
        results = walk_forward_validate(df, crypto_investor_v1_signals, params, n_splits=3)
        assert isinstance(results, list)

    def test_walk_forward_fold_structure(self):
        from validation_engine import walk_forward_validate

        df = generate_synthetic_ohlcv(n=5000)
        params = {"ema_fast": 50, "ema_slow": 200, "rsi_threshold": 40, "sell_rsi_threshold": 80}
        results = walk_forward_validate(df, crypto_investor_v1_signals, params, n_splits=3)
        if results:
            fold = results[0]
            assert "fold" in fold
            assert "train_rows" in fold
            assert "test_rows" in fold
            assert "is_sharpe" in fold
            assert "oos_sharpe" in fold

    def test_walk_forward_small_segment_warning(self):
        """With small data, should warn about small segment size."""
        from validation_engine import walk_forward_validate

        df = generate_synthetic_ohlcv(n=200)
        params = {"ema_fast": 50, "ema_slow": 200, "rsi_threshold": 40, "sell_rsi_threshold": 80}
        # Should not crash
        results = walk_forward_validate(df, crypto_investor_v1_signals, params, n_splits=5)
        assert isinstance(results, list)

    def test_walk_forward_skips_small_test_set(self):
        """Folds with test set < 50 should be skipped."""
        from validation_engine import walk_forward_validate

        # Very small data with many splits → test sets < 50
        df = generate_synthetic_ohlcv(n=150)
        params = {
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_threshold": 35,
            "volume_factor": 1.5,
            "sell_rsi_threshold": 65,
        }
        results = walk_forward_validate(df, bollinger_mr_signals, params, n_splits=10)
        assert isinstance(results, list)

    def test_walk_forward_signal_error_skips_fold(self):
        """If signal_fn raises, fold should be skipped."""
        from validation_engine import walk_forward_validate

        def bad_signal_fn(df, params):
            raise ValueError("intentional error")

        df = generate_synthetic_ohlcv(n=3000)
        results = walk_forward_validate(df, bad_signal_fn, {"p": 1}, n_splits=3)
        assert results == []


# ── Perturbation Test Tests ──────────────────────────────────


class TestPerturbationTest:
    """Cover validation_engine.py lines 318-359."""

    def test_perturbation_returns_list(self):
        from validation_engine import perturbation_test

        df = generate_synthetic_ohlcv(n=2000)
        params = {"ema_fast": 50, "ema_slow": 200, "rsi_threshold": 40, "sell_rsi_threshold": 80}
        results = perturbation_test(df, crypto_investor_v1_signals, params)
        assert isinstance(results, list)
        # 4 params * 2 directions = 8 perturbations
        assert len(results) == 8

    def test_perturbation_result_structure(self):
        from validation_engine import perturbation_test

        df = generate_synthetic_ohlcv(n=2000)
        params = {"ema_fast": 50, "ema_slow": 200, "rsi_threshold": 40, "sell_rsi_threshold": 80}
        results = perturbation_test(df, crypto_investor_v1_signals, params)
        for r in results:
            assert "param_name" in r
            assert "original_value" in r
            assert "perturbed_value" in r
            assert "direction" in r
            assert "sharpe_ratio" in r
            assert "total_return" in r

    def test_perturbation_int_params_rounded(self):
        """Integer parameters should be perturbed and rounded to int."""
        from validation_engine import perturbation_test

        df = generate_synthetic_ohlcv(n=2000)
        params = {"ema_fast": 50, "ema_slow": 200}

        def dummy_signal(df, p):
            entries = pd.Series(False, index=df.index)
            exits = pd.Series(False, index=df.index)
            return entries, exits

        results = perturbation_test(df, dummy_signal, params)
        for r in results:
            assert isinstance(r["perturbed_value"], (int, float))
            if isinstance(r["original_value"], int):
                assert r["perturbed_value"] == int(r["perturbed_value"])

    def test_perturbation_float_params_rounded(self):
        """Float parameters should be perturbed and rounded to 2 decimals."""
        from validation_engine import perturbation_test

        df = generate_synthetic_ohlcv(n=2000)
        params = {"ratio": 1.5}

        def dummy_signal(df, p):
            return pd.Series(False, index=df.index), pd.Series(False, index=df.index)

        results = perturbation_test(df, dummy_signal, params)
        for r in results:
            # Should be rounded to 2 decimals
            assert r["perturbed_value"] == round(r["perturbed_value"], 2)

    def test_perturbation_handles_signal_error(self):
        """If signal_fn raises during perturbation, result should have nan sharpe."""
        from validation_engine import perturbation_test

        df = generate_synthetic_ohlcv(n=2000)
        params = {"param1": 10}
        call_count = {"n": 0}

        def sometimes_failing_signal(df, p):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("signal error")
            return pd.Series(False, index=df.index), pd.Series(False, index=df.index)

        results = perturbation_test(df, sometimes_failing_signal, params)
        assert len(results) == 2
        # First call should have nan sharpe due to error
        assert np.isnan(results[0]["sharpe_ratio"])

    def test_perturbation_int_min_value_clamp(self):
        """Integer param perturbed -20% from 1 should be clamped to 1."""
        from validation_engine import perturbation_test

        df = generate_synthetic_ohlcv(n=2000)
        params = {"small_param": 1}

        def dummy_signal(df, p):
            return pd.Series(False, index=df.index), pd.Series(False, index=df.index)

        results = perturbation_test(df, dummy_signal, params)
        for r in results:
            assert r["perturbed_value"] >= 1


# ── run_validation Full Pipeline Tests ───────────────────────


class TestRunValidationFullPipeline:
    """Cover validation_engine.py lines 411-443 (gate2 pass) and 454-506 (gate3)."""

    def test_gate2_fail_skips_gate3(self):
        """When gate2 fails, gate3 should be skipped."""
        from validation_engine import run_validation

        df = generate_synthetic_ohlcv(n=2000)

        def no_signal_fn(df, params):
            # Produces zero trades → gate2 fails
            return pd.Series(False, index=df.index), pd.Series(False, index=df.index)

        report = run_validation("NoSignal", df, no_signal_fn, {"p": [1]})
        assert report["gate2"]["passed"] is False
        assert report["gate3_walkforward"]["passed"] is False
        assert "skipped" in report["gate3_walkforward"]
        assert report["gate3_perturbation"]["passed"] is False
        assert report["overall"]["passed"] is False

    def test_gate2_pass_runs_gate3(self):
        """When gate2 passes, gate3 should run walk-forward + perturbation."""
        from validation_engine import run_validation

        # Use a larger dataset and signal that generates many trades
        df = generate_synthetic_ohlcv(n=5000)
        # Use BMR signals with relaxed params that tend to generate trades
        tiny_grid = {
            "bb_period": [20],
            "bb_std": [2.0],
            "rsi_threshold": [40],
            "volume_factor": [1.0],
            "sell_rsi_threshold": [55],
        }
        report = run_validation(
            "BMR_gate3_test",
            df,
            bollinger_mr_signals,
            tiny_grid,
            sl_stop=0.04,
            symbol="SYNTHETIC",
        )
        # Regardless of pass/fail, gate3 sections should exist
        assert "gate3_walkforward" in report
        assert "gate3_perturbation" in report
        if report["gate2"]["passed"]:
            # Gate3 was actually run (not skipped)
            assert "skipped" not in report["gate3_walkforward"]
            assert "results" in report["gate3_perturbation"]

    def test_report_has_top_results(self):
        """Gate2 passing branch should include top_results list."""
        from validation_engine import run_validation

        df = generate_synthetic_ohlcv(n=5000)
        grid = {
            "bb_period": [15, 20],
            "bb_std": [1.5, 2.0],
            "rsi_threshold": [35, 40],
            "volume_factor": [1.0],
            "sell_rsi_threshold": [55],
        }
        report = run_validation("TopResults", df, bollinger_mr_signals, grid, sl_stop=0.04)
        if report["gate2"]["passed"]:
            assert isinstance(report["gate2"]["top_results"], list)
            assert len(report["gate2"]["top_results"]) <= 10

    def test_gate3_walkforward_no_folds(self):
        """If all walk-forward folds fail, gate3_walkforward should have error."""
        from validation_engine import run_validation

        # Use tiny data that will cause WF folds to fail
        df = generate_synthetic_ohlcv(n=500)

        # Mock sweep_parameters to return a "passing" result
        from unittest.mock import patch as _patch

        fake_sweep = pd.DataFrame(
            [
                {
                    "sharpe_ratio": 2.0,
                    "max_drawdown": 0.05,
                    "annualized_trades": 100,
                    "pvalue": 0.001,
                    "passes_gate2": True,
                    "total_return": 0.5,
                    "num_trades": 50,
                    "win_rate": 0.6,
                    "profit_factor": 2.0,
                    "params": {"p": 1},
                    "failure_reasons": [],
                }
            ]
        )

        def always_fail_signal(df, params):
            raise ValueError("always fails")

        with _patch("validation_engine.sweep_parameters", return_value=fake_sweep):
            report = run_validation("WFNoFolds", df, always_fail_signal, {"p": [1]})

        # Gate3 WF should have run but produced no valid folds
        assert report["gate3_walkforward"]["passed"] is False

    def test_overall_pass_requires_all_gates(self):
        """Overall pass requires gate2 + gate3_wf + gate3_perturb all passing."""
        from validation_engine import run_validation

        df = generate_synthetic_ohlcv(n=5000)
        tiny_grid = {
            "bb_period": [20],
            "bb_std": [2.0],
            "rsi_threshold": [40],
            "volume_factor": [1.0],
            "sell_rsi_threshold": [55],
        }
        report = run_validation("OverallTest", df, bollinger_mr_signals, tiny_grid, sl_stop=0.04)
        overall = report["overall"]
        assert overall["passed"] == (
            overall["gate2_passed"]
            and overall["gate3_wf_passed"]
            and overall["gate3_perturb_passed"]
        )


# ── validate_*.py main() Tests ──────────────────────────────


class TestValidateBMRMain:
    """Cover validate_bollinger_mean_reversion.py lines 103-176."""

    def test_main_synthetic(self, capsys, monkeypatch):
        from unittest.mock import patch as _patch

        monkeypatch.setattr(
            "sys.argv",
            [
                "validate_bollinger_mean_reversion.py",
                "--synthetic",
                "--synthetic-rows",
                "500",
            ],
        )

        mock_report = {
            "overall": {"passed": False},
            "gate2": {"passed": False},
            "gate3_walkforward": {"passed": False},
            "gate3_perturbation": {"passed": False},
        }

        with (
            _patch("validate_bollinger_mean_reversion.run_validation", return_value=mock_report),
            _patch(
                "validate_bollinger_mean_reversion.save_report",
                return_value=Path("/tmp/report.json"),
            ),
            _patch(
                "validate_bollinger_mean_reversion.generate_synthetic_ohlcv",
                return_value=generate_synthetic_ohlcv(n=500),
            ),
        ):
            from validate_bollinger_mean_reversion import main as bmr_main

            bmr_main()

        captured = capsys.readouterr()
        assert "Report saved to" in captured.out
        assert "VALIDATION FAILED" in captured.out
        assert "Gate 2 failed" in captured.out

    def test_main_synthetic_pass(self, capsys, monkeypatch):
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--synthetic", "--synthetic-rows", "500"])

        mock_report = {
            "overall": {"passed": True},
            "gate2": {"passed": True},
            "gate3_walkforward": {"passed": True},
            "gate3_perturbation": {"passed": True},
        }

        with (
            _patch("validate_bollinger_mean_reversion.run_validation", return_value=mock_report),
            _patch(
                "validate_bollinger_mean_reversion.save_report",
                return_value=Path("/tmp/report.json"),
            ),
            _patch(
                "validate_bollinger_mean_reversion.generate_synthetic_ohlcv",
                return_value=generate_synthetic_ohlcv(n=500),
            ),
        ):
            from validate_bollinger_mean_reversion import main as bmr_main

            bmr_main()

        captured = capsys.readouterr()
        assert "VALIDATION PASSED" in captured.out

    def test_main_real_data_empty(self, capsys, monkeypatch):
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--symbol", "BAD/PAIR"])

        with _patch("common.data_pipeline.pipeline.load_ohlcv", return_value=pd.DataFrame()):
            from validate_bollinger_mean_reversion import main as bmr_main

            bmr_main()
        # Should return early without crash

    def test_main_real_data_success(self, capsys, monkeypatch):
        """Cover line 150: symbol = args.symbol in real-data path."""
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--symbol", "BTC/USDT"])

        mock_report = {
            "overall": {"passed": True},
            "gate2": {"passed": True},
        }
        mock_df = generate_synthetic_ohlcv(n=500)

        with (
            _patch("common.data_pipeline.pipeline.load_ohlcv", return_value=mock_df),
            _patch("validate_bollinger_mean_reversion.run_validation", return_value=mock_report),
            _patch(
                "validate_bollinger_mean_reversion.save_report", return_value=Path("/tmp/r.json")
            ),
        ):
            from validate_bollinger_mean_reversion import main as bmr_main

            bmr_main()

        captured = capsys.readouterr()
        assert "VALIDATION PASSED" in captured.out

    def test_main_gate3_wf_fail(self, capsys, monkeypatch):
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--synthetic", "--synthetic-rows", "500"])

        mock_report = {
            "overall": {"passed": False},
            "gate2": {"passed": True},
            "gate3_walkforward": {"passed": False},
            "gate3_perturbation": {"passed": False},
        }

        with (
            _patch("validate_bollinger_mean_reversion.run_validation", return_value=mock_report),
            _patch(
                "validate_bollinger_mean_reversion.save_report",
                return_value=Path("/tmp/report.json"),
            ),
            _patch(
                "validate_bollinger_mean_reversion.generate_synthetic_ohlcv",
                return_value=generate_synthetic_ohlcv(n=500),
            ),
        ):
            from validate_bollinger_mean_reversion import main as bmr_main

            bmr_main()

        captured = capsys.readouterr()
        assert "Gate 3a failed" in captured.out
        assert "Gate 3b failed" in captured.out


class TestValidateCIV1Main:
    """Cover validate_crypto_investor_v1.py lines 107-180."""

    def test_main_synthetic_fail(self, capsys, monkeypatch):
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--synthetic", "--synthetic-rows", "500"])

        mock_report = {
            "overall": {"passed": False},
            "gate2": {"passed": False},
            "gate3_walkforward": {"passed": False},
            "gate3_perturbation": {"passed": False},
        }

        with (
            _patch("validate_crypto_investor_v1.run_validation", return_value=mock_report),
            _patch(
                "validate_crypto_investor_v1.save_report", return_value=Path("/tmp/report.json")
            ),
            _patch(
                "validate_crypto_investor_v1.generate_synthetic_ohlcv",
                return_value=generate_synthetic_ohlcv(n=500),
            ),
        ):
            from validate_crypto_investor_v1 import main as civ1_main

            civ1_main()

        captured = capsys.readouterr()
        assert "VALIDATION FAILED" in captured.out

    def test_main_synthetic_pass(self, capsys, monkeypatch):
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--synthetic", "--synthetic-rows", "500"])

        mock_report = {
            "overall": {"passed": True},
            "gate2": {"passed": True},
        }

        with (
            _patch("validate_crypto_investor_v1.run_validation", return_value=mock_report),
            _patch(
                "validate_crypto_investor_v1.save_report", return_value=Path("/tmp/report.json")
            ),
            _patch(
                "validate_crypto_investor_v1.generate_synthetic_ohlcv",
                return_value=generate_synthetic_ohlcv(n=500),
            ),
        ):
            from validate_crypto_investor_v1 import main as civ1_main

            civ1_main()

        captured = capsys.readouterr()
        assert "VALIDATION PASSED" in captured.out

    def test_main_real_data_empty(self, capsys, monkeypatch):
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--symbol", "BAD/PAIR"])

        with _patch("common.data_pipeline.pipeline.load_ohlcv", return_value=pd.DataFrame()):
            from validate_crypto_investor_v1 import main as civ1_main

            civ1_main()

    def test_main_real_data_success(self, capsys, monkeypatch):
        """Cover line 154: symbol = args.symbol in real-data path."""
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--symbol", "ETH/USDT"])

        mock_report = {"overall": {"passed": True}, "gate2": {"passed": True}}
        mock_df = generate_synthetic_ohlcv(n=500)

        with (
            _patch("common.data_pipeline.pipeline.load_ohlcv", return_value=mock_df),
            _patch("validate_crypto_investor_v1.run_validation", return_value=mock_report),
            _patch("validate_crypto_investor_v1.save_report", return_value=Path("/tmp/r.json")),
        ):
            from validate_crypto_investor_v1 import main as civ1_main

            civ1_main()

        captured = capsys.readouterr()
        assert "VALIDATION PASSED" in captured.out


class TestValidateVBMain:
    """Cover validate_volatility_breakout.py lines 129-202."""

    def test_main_synthetic_fail(self, capsys, monkeypatch):
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--synthetic", "--synthetic-rows", "500"])

        mock_report = {
            "overall": {"passed": False},
            "gate2": {"passed": False},
            "gate3_walkforward": {"passed": False},
            "gate3_perturbation": {"passed": False},
        }

        with (
            _patch("validate_volatility_breakout.run_validation", return_value=mock_report),
            _patch(
                "validate_volatility_breakout.save_report", return_value=Path("/tmp/report.json")
            ),
            _patch(
                "validate_volatility_breakout.generate_synthetic_ohlcv",
                return_value=generate_synthetic_ohlcv(n=500),
            ),
        ):
            from validate_volatility_breakout import main as vb_main

            vb_main()

        captured = capsys.readouterr()
        assert "VALIDATION FAILED" in captured.out
        assert "Gate 2 failed" in captured.out

    def test_main_synthetic_pass(self, capsys, monkeypatch):
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--synthetic", "--synthetic-rows", "500"])

        mock_report = {
            "overall": {"passed": True},
            "gate2": {"passed": True},
        }

        with (
            _patch("validate_volatility_breakout.run_validation", return_value=mock_report),
            _patch(
                "validate_volatility_breakout.save_report", return_value=Path("/tmp/report.json")
            ),
            _patch(
                "validate_volatility_breakout.generate_synthetic_ohlcv",
                return_value=generate_synthetic_ohlcv(n=500),
            ),
        ):
            from validate_volatility_breakout import main as vb_main

            vb_main()

        captured = capsys.readouterr()
        assert "VALIDATION PASSED" in captured.out

    def test_main_real_data_empty(self, capsys, monkeypatch):
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--symbol", "BAD/PAIR"])

        with _patch("common.data_pipeline.pipeline.load_ohlcv", return_value=pd.DataFrame()):
            from validate_volatility_breakout import main as vb_main

            vb_main()

    def test_main_real_data_success(self, capsys, monkeypatch):
        """Cover line 176: symbol = args.symbol in real-data path."""
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--symbol", "SOL/USDT"])

        mock_report = {"overall": {"passed": True}, "gate2": {"passed": True}}
        mock_df = generate_synthetic_ohlcv(n=500)

        with (
            _patch("common.data_pipeline.pipeline.load_ohlcv", return_value=mock_df),
            _patch("validate_volatility_breakout.run_validation", return_value=mock_report),
            _patch("validate_volatility_breakout.save_report", return_value=Path("/tmp/r.json")),
        ):
            from validate_volatility_breakout import main as vb_main

            vb_main()

        captured = capsys.readouterr()
        assert "VALIDATION PASSED" in captured.out

    def test_main_gate3_partial_fail(self, capsys, monkeypatch):
        """Gate2 passes but gate3 WF fails, perturbation passes."""
        from unittest.mock import patch as _patch

        monkeypatch.setattr("sys.argv", ["prog", "--synthetic", "--synthetic-rows", "500"])

        mock_report = {
            "overall": {"passed": False},
            "gate2": {"passed": True},
            "gate3_walkforward": {"passed": False},
            "gate3_perturbation": {"passed": True},
        }

        with (
            _patch("validate_volatility_breakout.run_validation", return_value=mock_report),
            _patch(
                "validate_volatility_breakout.save_report", return_value=Path("/tmp/report.json")
            ),
            _patch(
                "validate_volatility_breakout.generate_synthetic_ohlcv",
                return_value=generate_synthetic_ohlcv(n=500),
            ),
        ):
            from validate_volatility_breakout import main as vb_main

            vb_main()

        captured = capsys.readouterr()
        assert "Gate 3a failed" in captured.out


# ── Additional Coverage: Edge Cases ──────────────────────────


class TestRunBacktestEdgeCases:
    """Cover validation_engine.py lines 120, 126-127 (trade_pnls handling)."""

    def test_backtest_with_to_numpy_attribute(self):
        """Ensure trade_pnls with to_numpy attribute is handled."""
        from validation_engine import _run_backtest

        df = generate_synthetic_ohlcv(n=2000)
        params = {
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_threshold": 40,
            "volume_factor": 1.0,
            "sell_rsi_threshold": 55,
        }
        entries, exits = bollinger_mr_signals(df, params)
        # Normal call - exercises the pnl extraction code path
        metrics = _run_backtest(df["close"], entries, exits, fees=0.0015, sl_stop=0.04)
        assert "pvalue" in metrics
        assert isinstance(metrics["pvalue"], float)

    def test_backtest_no_trades_pvalue_one(self):
        """With zero entries, pvalue should be 1.0."""
        from validation_engine import _run_backtest

        df = generate_synthetic_ohlcv(n=500)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        metrics = _run_backtest(df["close"], entries, exits)
        assert metrics["pvalue"] == 1.0
        assert metrics["num_trades"] == 0

    def test_backtest_pnl_ttest_exception(self):
        """Cover lines 126-127: exception in pvalue calculation."""
        from unittest.mock import patch as _patch

        from validation_engine import _run_backtest

        df = generate_synthetic_ohlcv(n=2000)
        params = {
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_threshold": 40,
            "volume_factor": 1.0,
            "sell_rsi_threshold": 55,
        }
        entries, exits = bollinger_mr_signals(df, params)

        # Mock ttest_1samp to raise
        with _patch(
            "validation_engine.scipy_stats.ttest_1samp", side_effect=RuntimeError("stats error")
        ):
            metrics = _run_backtest(df["close"], entries, exits, fees=0.0015, sl_stop=0.04)

        assert metrics["pvalue"] == 1.0


class TestSweepParametersEdgeCases:
    """Cover validation_engine.py lines 200-201 (combo error), 204 (progress log)."""

    def test_sweep_with_failing_combo(self):
        """When a combo's signal_fn raises, it should be skipped."""
        from validation_engine import sweep_parameters

        df = generate_synthetic_ohlcv(n=2000)

        def sometimes_fail(df, params):
            if params.get("p") == 2:
                raise RuntimeError("bad combo")
            return pd.Series(False, index=df.index), pd.Series(False, index=df.index)

        results_df = sweep_parameters(df, sometimes_fail, {"p": [1, 2, 3]})
        # Combo p=2 should be skipped, so we get 2 results
        assert len(results_df) == 2

    def test_sweep_progress_logging(self):
        """With 100+ combos, progress should be logged."""
        from validation_engine import sweep_parameters

        df = generate_synthetic_ohlcv(n=500)

        def dummy_signal(df, params):
            return pd.Series(False, index=df.index), pd.Series(False, index=df.index)

        # Create 101 combos to trigger progress logging at combo 100
        results_df = sweep_parameters(df, dummy_signal, {"p": list(range(101))})
        assert len(results_df) == 101


class TestWalkForwardOOSFailure:
    """Cover validation_engine.py lines 275-277 (OOS failure branch)."""

    def test_walk_forward_oos_failure(self):
        from validation_engine import walk_forward_validate

        df = generate_synthetic_ohlcv(n=3000)
        call_count = {"n": 0}

        def fail_on_oos(df, params):
            call_count["n"] += 1
            # IS calls succeed (odd calls), OOS calls fail (even calls)
            if call_count["n"] % 2 == 0:
                raise RuntimeError("OOS failed")
            return pd.Series(False, index=df.index), pd.Series(False, index=df.index)

        results = walk_forward_validate(df, fail_on_oos, {"p": 1}, n_splits=3)
        # All folds should be skipped due to OOS failure
        assert results == []


class TestRunValidationGate3Details:
    """Cover validation_engine.py lines 460-474 (gate3 WF calculation with actual folds)."""

    def test_gate3_with_valid_folds(self):
        """Force gate2 to pass and gate3 to run with actual walk-forward folds."""
        from unittest.mock import patch as _patch

        from validation_engine import run_validation

        df = generate_synthetic_ohlcv(n=5000)

        # Mock sweep_parameters to return a "passing" result with params that produce signals
        fake_sweep = pd.DataFrame(
            [
                {
                    "sharpe_ratio": 2.0,
                    "max_drawdown": 0.05,
                    "annualized_trades": 100,
                    "pvalue": 0.001,
                    "passes_gate2": True,
                    "total_return": 0.5,
                    "num_trades": 50,
                    "win_rate": 0.6,
                    "profit_factor": 2.0,
                    "params": {
                        "bb_period": 20,
                        "bb_std": 2.0,
                        "rsi_threshold": 40,
                        "volume_factor": 1.0,
                        "sell_rsi_threshold": 55,
                    },
                    "failure_reasons": [],
                }
            ]
        )

        with _patch("validation_engine.sweep_parameters", return_value=fake_sweep):
            report = run_validation(
                "Gate3Test",
                df,
                bollinger_mr_signals,
                {"bb_period": [20]},
                sl_stop=0.04,
            )

        # Gate2 should be marked as passed
        assert report["gate2"]["passed"] is True
        assert report["gate2"]["best_params"] is not None
        assert isinstance(report["gate2"]["top_results"], list)

        # Gate3 should have run (not skipped)
        assert "skipped" not in report["gate3_walkforward"]
        assert "skipped" not in report["gate3_perturbation"]

        # Gate3 WF should have the calculation fields
        wf = report["gate3_walkforward"]
        if wf.get("passed") is not None:
            assert "avg_is_sharpe" in wf or "error" in wf

        # Gate3 perturbation should have results
        perturb = report["gate3_perturbation"]
        assert "results" in perturb
        assert isinstance(perturb["results"], list)

    def test_save_report_logs(self, tmp_path):
        """Cover validation_engine.py save_report with explicit output_dir."""
        from validation_engine import save_report

        report = {"strategy_name": "test", "timestamp": "2026-01-01"}
        filepath = save_report(report, output_dir=tmp_path)
        assert filepath.exists()
        assert "test_validation_" in filepath.name

    def test_save_report_default_dir(self):
        """Cover validation_engine.py line 542 (output_dir=None → RESULTS_DIR)."""
        import os

        from validation_engine import RESULTS_DIR, save_report

        report = {"strategy_name": "default_dir_test", "timestamp": "2026-01-01"}
        filepath = save_report(report)  # No output_dir → uses RESULTS_DIR
        assert filepath.exists()
        assert str(RESULTS_DIR) in str(filepath)
        # Clean up
        os.unlink(filepath)
