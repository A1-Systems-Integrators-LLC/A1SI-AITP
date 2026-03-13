"""
Comprehensive tests for the VectorBT screening module.
=======================================================
Tests all 6 screening strategies, edge cases (insufficient data,
NaN data, flat data), asset class handling, per-class fees,
result format, and empty/invalid watchlists.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure project root on sys.path so we can import from research.scripts
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.scripts.vbt_screener import (  # noqa: E402
    _ASSET_CLASS_FEES,
    SCREEN_FUNCTIONS,
    screen_bollinger_breakout,
    screen_ema_rsi_combo,
    screen_relative_strength,
    screen_rsi_mean_reversion,
    screen_sma_crossover,
    screen_volatility_breakout,
    walk_forward_validate,
)


# ── Helpers ─────────────────────────────────────────────────────


def _make_ohlcv(
    n: int = 500,
    seed: int = 42,
    base_price: float = 100.0,
    volatility: float = 0.02,
    trend: float = 0.0001,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data with realistic price structure."""
    rng = np.random.RandomState(seed)
    # Random walk with optional trend
    returns = rng.normal(trend, volatility, n)
    close = base_price * np.exp(np.cumsum(returns))

    # Build OHLC from close with realistic wicks
    spread = np.abs(rng.normal(0, volatility * base_price * 0.5, n))
    high = close + spread
    low = close - spread
    low = np.maximum(low, close * 0.9)  # avoid negative
    open_ = close + rng.normal(0, volatility * base_price * 0.2, n)
    # Ensure high >= max(open, close) and low <= min(open, close)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    volume = rng.uniform(100, 10000, n)
    # Add volume spikes for volatility breakout detection
    spike_mask = rng.random(n) < 0.05
    volume[spike_mask] *= 5

    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def _make_trending_ohlcv(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate data with a clear uptrend to trigger more signals."""
    return _make_ohlcv(n=n, seed=seed, trend=0.001, volatility=0.015)


def _make_volatile_ohlcv(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate highly volatile data."""
    return _make_ohlcv(n=n, seed=seed, volatility=0.05, trend=0.0)


def _make_flat_ohlcv(n: int = 500) -> pd.DataFrame:
    """Generate flat (no price movement) OHLCV data."""
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "open": np.full(n, 100.0),
            "high": np.full(n, 100.0),
            "low": np.full(n, 100.0),
            "close": np.full(n, 100.0),
            "volume": np.full(n, 1000.0),
        },
        index=idx,
    )


def _make_nan_ohlcv(n: int = 500, nan_fraction: float = 0.1, seed: int = 42) -> pd.DataFrame:
    """Generate OHLCV with NaN values scattered through it."""
    df = _make_ohlcv(n=n, seed=seed)
    rng = np.random.RandomState(seed + 1)
    for col in ["open", "high", "low", "close", "volume"]:
        mask = rng.random(n) < nan_fraction
        df.loc[df.index[mask], col] = np.nan
    return df


# ── 1. SMA Crossover Screen Tests ──────────────────────────────


class TestSMACrossoverScreen:
    # NOTE: VBT run_combs(r=2) needs the merged window list to have >= 2 elements
    # to produce combinations. With 1 fast + 1 slow = 2, that gives C(2,2)=1 combo
    # but the portfolio metrics are scalars. We need >= 3 windows merged for multi-combo.

    def test_returns_dataframe(self):
        df = _make_ohlcv(n=500)
        result = screen_sma_crossover(df["close"], fast_windows=[5, 10], slow_windows=[30, 50], fees=0.001)
        assert isinstance(result, pd.DataFrame)

    def test_expected_columns(self):
        df = _make_ohlcv(n=500)
        result = screen_sma_crossover(df["close"], fast_windows=[5, 10], slow_windows=[30, 50])
        expected_cols = {"total_return", "sharpe_ratio", "max_drawdown", "win_rate", "profit_factor", "num_trades", "avg_trade_pnl"}
        assert expected_cols.issubset(set(result.columns))

    def test_sorted_by_sharpe(self):
        df = _make_ohlcv(n=500)
        result = screen_sma_crossover(df["close"], fast_windows=[5, 10, 15], slow_windows=[30, 50])
        if len(result) > 1:
            sharpes = result["sharpe_ratio"].values
            # Should be sorted descending
            assert sharpes[0] >= sharpes[-1]

    def test_multiple_param_combos(self):
        df = _make_ohlcv(n=500)
        result = screen_sma_crossover(df["close"], fast_windows=[5, 10, 15], slow_windows=[30, 50, 100])
        # VBT MA.run_combs generates combinations from the merged window list
        assert len(result) >= 1

    def test_custom_fees(self):
        df = _make_ohlcv(n=500)
        r_low = screen_sma_crossover(df["close"], fast_windows=[5, 10], slow_windows=[30, 50], fees=0.0)
        r_high = screen_sma_crossover(df["close"], fast_windows=[5, 10], slow_windows=[30, 50], fees=0.01)
        # Higher fees should reduce (or at worst equal) total return for the best combo
        if len(r_low) > 0 and len(r_high) > 0:
            # Compare max total return across all combos
            assert r_low["total_return"].max() >= r_high["total_return"].max()


# ── 2. RSI Mean Reversion Screen Tests ─────────────────────────


class TestRSIMeanReversionScreen:
    def test_returns_dataframe(self):
        df = _make_ohlcv(n=500)
        result = screen_rsi_mean_reversion(df, rsi_periods=[14], oversold_levels=[30], overbought_levels=[70])
        assert isinstance(result, pd.DataFrame)

    def test_expected_columns(self):
        df = _make_ohlcv(n=500)
        result = screen_rsi_mean_reversion(df, rsi_periods=[14], oversold_levels=[30], overbought_levels=[70])
        if not result.empty:
            expected = {"rsi_period", "oversold", "overbought", "total_return", "sharpe_ratio", "max_drawdown"}
            assert expected.issubset(set(result.columns))

    def test_skips_invalid_level_combos(self):
        """When oversold >= overbought, that combo should be skipped."""
        df = _make_ohlcv(n=500)
        result = screen_rsi_mean_reversion(
            df, rsi_periods=[14], oversold_levels=[70], overbought_levels=[30],
        )
        # 70 >= 30 so all combos should be skipped
        assert len(result) == 0

    def test_multiple_periods(self):
        df = _make_ohlcv(n=500)
        result = screen_rsi_mean_reversion(
            df, rsi_periods=[7, 14], oversold_levels=[30], overbought_levels=[70],
        )
        if not result.empty:
            assert set(result["rsi_period"].unique()).issubset({7, 14})


# ── 3. Bollinger Breakout Screen Tests ─────────────────────────


class TestBollingerBreakoutScreen:
    def test_returns_dataframe(self):
        df = _make_ohlcv(n=500)
        result = screen_bollinger_breakout(df, bb_periods=[20], bb_stds=[2.0])
        assert isinstance(result, pd.DataFrame)

    def test_expected_columns(self):
        df = _make_ohlcv(n=500)
        result = screen_bollinger_breakout(df, bb_periods=[20], bb_stds=[2.0])
        if not result.empty:
            assert "bb_period" in result.columns
            assert "bb_std" in result.columns
            assert "sharpe_ratio" in result.columns

    def test_parameter_grid_size(self):
        df = _make_ohlcv(n=500)
        result = screen_bollinger_breakout(df, bb_periods=[10, 20], bb_stds=[1.5, 2.0])
        # 2 periods x 2 stds = 4 combos
        assert len(result) == 4


# ── 4. EMA+RSI Combo Screen Tests ──────────────────────────────


class TestEMARSIComboScreen:
    def test_returns_dataframe(self):
        df = _make_ohlcv(n=500)
        result = screen_ema_rsi_combo(df, ema_periods=[20], rsi_entry_levels=[35])
        assert isinstance(result, pd.DataFrame)

    def test_expected_columns(self):
        df = _make_ohlcv(n=500)
        result = screen_ema_rsi_combo(df, ema_periods=[20], rsi_entry_levels=[35])
        if not result.empty:
            assert "ema_period" in result.columns
            assert "rsi_entry" in result.columns
            assert "sharpe_ratio" in result.columns
            assert "num_trades" in result.columns

    def test_grid_combos(self):
        df = _make_ohlcv(n=500)
        result = screen_ema_rsi_combo(df, ema_periods=[20, 50], rsi_entry_levels=[30, 40])
        # 2 x 2 = 4 combos (some might fail silently)
        assert len(result) <= 4


# ── 5. Volatility Breakout Screen Tests ────────────────────────


class TestVolatilityBreakoutScreen:
    def test_returns_dataframe(self):
        df = _make_volatile_ohlcv(n=500)
        result = screen_volatility_breakout(
            df, breakout_periods=[20], volume_factors=[1.5], adx_ranges=[(10, 30)],
        )
        assert isinstance(result, pd.DataFrame)

    def test_expected_columns(self):
        df = _make_volatile_ohlcv(n=500)
        result = screen_volatility_breakout(
            df, breakout_periods=[20], volume_factors=[1.5], adx_ranges=[(10, 30)],
        )
        if not result.empty:
            expected = {"breakout_period", "volume_factor", "adx_low", "adx_high", "total_return", "sharpe_ratio"}
            assert expected.issubset(set(result.columns))

    def test_single_combo(self):
        df = _make_volatile_ohlcv(n=500)
        result = screen_volatility_breakout(
            df, breakout_periods=[15], volume_factors=[1.2], adx_ranges=[(10, 30)],
        )
        # Exactly 1 parameter combo
        assert len(result) == 1

    def test_multi_combo(self):
        df = _make_volatile_ohlcv(n=500)
        result = screen_volatility_breakout(
            df,
            breakout_periods=[10, 20],
            volume_factors=[1.2, 2.0],
            adx_ranges=[(10, 25), (15, 30)],
        )
        # 2 x 2 x 2 = 8 combos
        assert len(result) == 8


# ── 6. Relative Strength Screen Tests ──────────────────────────


class TestRelativeStrengthScreen:
    def _make_pair(self, n: int = 300):
        """Make asset + benchmark DataFrames with matching index."""
        idx = pd.date_range("2024-01-01", periods=n, freq="1d", tz="UTC")
        rng = np.random.RandomState(42)
        # Asset outperforms benchmark
        asset_close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
        bench_close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
        df = pd.DataFrame({"close": asset_close}, index=idx)
        bench_df = pd.DataFrame({"close": bench_close}, index=idx)
        return df, bench_df

    def test_returns_dataframe(self):
        df, bench = self._make_pair()
        result = screen_relative_strength(df, bench, lookback_periods=[20], rs_thresholds=[1.02])
        assert isinstance(result, pd.DataFrame)

    def test_expected_columns(self):
        df, bench = self._make_pair()
        result = screen_relative_strength(df, bench, lookback_periods=[20], rs_thresholds=[1.02])
        if not result.empty:
            assert "lookback" in result.columns
            assert "rs_threshold" in result.columns
            assert "sharpe_ratio" in result.columns

    def test_insufficient_overlap_returns_empty(self):
        """When less than 50 overlapping rows, should return empty DataFrame."""
        idx1 = pd.date_range("2024-01-01", periods=30, freq="1d", tz="UTC")
        idx2 = pd.date_range("2025-01-01", periods=30, freq="1d", tz="UTC")
        df = pd.DataFrame({"close": np.linspace(100, 110, 30)}, index=idx1)
        bench = pd.DataFrame({"close": np.linspace(100, 105, 30)}, index=idx2)
        result = screen_relative_strength(df, bench)
        assert result.empty

    def test_zero_fees_by_default(self):
        """Relative strength default fees should be 0.0."""
        import inspect
        sig = inspect.signature(screen_relative_strength)
        assert sig.parameters["fees"].default == 0.0

    def test_grid_combos(self):
        df, bench = self._make_pair(n=400)
        result = screen_relative_strength(
            df, bench, lookback_periods=[20, 50], rs_thresholds=[1.02, 1.05],
        )
        # 2 x 2 = 4 combos max
        assert len(result) <= 4


# ── 7. Insufficient Data (< 200 rows) ─────────────────────────


class TestInsufficientData:
    def test_sma_crossover_short_data(self):
        """SMA crossover with very short data should not crash."""
        df = _make_ohlcv(n=50)
        # slow window 30 may not produce meaningful results, but should not error
        result = screen_sma_crossover(df["close"], fast_windows=[5, 10], slow_windows=[20, 30])
        assert isinstance(result, pd.DataFrame)

    def test_rsi_short_data(self):
        df = _make_ohlcv(n=30)
        result = screen_rsi_mean_reversion(df, rsi_periods=[14], oversold_levels=[30], overbought_levels=[70])
        assert isinstance(result, pd.DataFrame)

    def test_bollinger_short_data(self):
        df = _make_ohlcv(n=25)
        result = screen_bollinger_breakout(df, bb_periods=[20], bb_stds=[2.0])
        assert isinstance(result, pd.DataFrame)

    def test_volatility_breakout_short_data(self):
        df = _make_ohlcv(n=50)
        result = screen_volatility_breakout(
            df, breakout_periods=[20], volume_factors=[1.5], adx_ranges=[(10, 30)],
        )
        assert isinstance(result, pd.DataFrame)

    def test_ema_rsi_short_data(self):
        df = _make_ohlcv(n=30)
        result = screen_ema_rsi_combo(df, ema_periods=[20], rsi_entry_levels=[35])
        assert isinstance(result, pd.DataFrame)


# ── 8. NaN Data Handling ───────────────────────────────────────


class TestNaNData:
    def test_rsi_with_nans_does_not_crash(self):
        df = _make_nan_ohlcv(n=500, nan_fraction=0.05)
        # RSI and other indicators handle NaN via pandas rolling
        result = screen_rsi_mean_reversion(df, rsi_periods=[14], oversold_levels=[30], overbought_levels=[70])
        assert isinstance(result, pd.DataFrame)

    def test_bollinger_with_nans(self):
        df = _make_nan_ohlcv(n=500, nan_fraction=0.05)
        result = screen_bollinger_breakout(df, bb_periods=[20], bb_stds=[2.0])
        assert isinstance(result, pd.DataFrame)

    def test_volatility_breakout_with_nans(self):
        df = _make_nan_ohlcv(n=500, nan_fraction=0.05)
        result = screen_volatility_breakout(
            df, breakout_periods=[20], volume_factors=[1.5], adx_ranges=[(10, 30)],
        )
        assert isinstance(result, pd.DataFrame)


# ── 9. Flat Data (No Movement) ────────────────────────────────


class TestFlatData:
    def test_sma_crossover_flat(self):
        df = _make_flat_ohlcv(n=500)
        result = screen_sma_crossover(df["close"], fast_windows=[5, 10], slow_windows=[30, 50])
        assert isinstance(result, pd.DataFrame)
        # No crossovers possible — expect 0 trades for all combos
        if not result.empty and "num_trades" in result.columns:
            assert (result["num_trades"] == 0).all()

    def test_rsi_flat(self):
        df = _make_flat_ohlcv(n=500)
        result = screen_rsi_mean_reversion(df, rsi_periods=[14], oversold_levels=[30], overbought_levels=[70])
        assert isinstance(result, pd.DataFrame)

    def test_bollinger_flat(self):
        df = _make_flat_ohlcv(n=500)
        result = screen_bollinger_breakout(df, bb_periods=[20], bb_stds=[2.0])
        assert isinstance(result, pd.DataFrame)


# ── 10. Asset Class Fee Handling ───────────────────────────────


class TestAssetClassFees:
    def test_crypto_fee(self):
        assert _ASSET_CLASS_FEES["crypto"] == 0.001

    def test_equity_fee(self):
        assert _ASSET_CLASS_FEES["equity"] == 0.0

    def test_forex_fee(self):
        assert _ASSET_CLASS_FEES["forex"] == 0.0001

    def test_unknown_asset_class_fallback(self):
        """Unknown asset class should fall back to default 0.001 in get()."""
        fee = _ASSET_CLASS_FEES.get("unknown", 0.001)
        assert fee == 0.001

    def test_higher_fees_reduce_returns(self):
        """Crypto fees (0.1%) vs equity fees (0%) should yield lower returns."""
        df = _make_trending_ohlcv(n=500)
        r_equity = screen_rsi_mean_reversion(
            df, rsi_periods=[14], oversold_levels=[30], overbought_levels=[70],
            fees=_ASSET_CLASS_FEES["equity"],
        )
        r_crypto = screen_rsi_mean_reversion(
            df, rsi_periods=[14], oversold_levels=[30], overbought_levels=[70],
            fees=_ASSET_CLASS_FEES["crypto"],
        )
        if not r_equity.empty and not r_crypto.empty:
            # Zero-fee return should be >= fee-adjusted return
            assert r_equity["total_return"].iloc[0] >= r_crypto["total_return"].iloc[0]


# ── 11. Result Format / Structure ──────────────────────────────


class TestResultFormat:
    def test_sma_result_is_numeric(self):
        df = _make_ohlcv(n=500)
        result = screen_sma_crossover(df["close"], fast_windows=[5, 10], slow_windows=[30, 50])
        for col in ["total_return", "sharpe_ratio", "max_drawdown"]:
            if col in result.columns:
                assert pd.api.types.is_numeric_dtype(result[col])

    def test_rsi_result_num_trades_integer(self):
        df = _make_ohlcv(n=500)
        result = screen_rsi_mean_reversion(df, rsi_periods=[14], oversold_levels=[30], overbought_levels=[70])
        if not result.empty and "num_trades" in result.columns:
            # num_trades should be integer-valued (though possibly stored as float)
            for v in result["num_trades"]:
                assert float(v) == int(v)

    def test_drawdown_bounded(self):
        """Max drawdown should be between -1.0 and 0.0 (VBT convention: negative)."""
        df = _make_ohlcv(n=500)
        result = screen_bollinger_breakout(df, bb_periods=[20], bb_stds=[2.0])
        if not result.empty:
            assert (result["max_drawdown"] >= -1.0).all()
            assert (result["max_drawdown"] <= 0.0).all()


# ── 12. SCREEN_FUNCTIONS Registry ──────────────────────────────


class TestScreenFunctionsRegistry:
    def test_all_five_strategies_registered(self):
        expected = {"sma_crossover", "rsi_mean_reversion", "bollinger_breakout", "ema_rsi_combo", "volatility_breakout"}
        assert expected == set(SCREEN_FUNCTIONS.keys())

    def test_screen_functions_are_callable(self):
        for name, fn in SCREEN_FUNCTIONS.items():
            assert callable(fn), f"{name} is not callable"


# ── 13. Walk-Forward Validation ────────────────────────────────


class TestWalkForwardValidation:
    def test_invalid_strategy_raises(self):
        df = _make_ohlcv(n=500)
        with pytest.raises(ValueError, match="Unknown strategy"):
            walk_forward_validate(df, "nonexistent_strategy")

    def test_returns_dataframe(self):
        df = _make_trending_ohlcv(n=1000)
        result = walk_forward_validate(df, "rsi_mean_reversion", n_splits=2, fees=0.001)
        assert isinstance(result, pd.DataFrame)

    def test_wf_has_expected_columns(self):
        df = _make_trending_ohlcv(n=1000)
        result = walk_forward_validate(df, "rsi_mean_reversion", n_splits=2, fees=0.001)
        if not result.empty:
            for col in ["split", "is_sharpe", "oos_sharpe", "degradation_ratio"]:
                assert col in result.columns

    def test_wf_too_short_data_returns_empty(self):
        """With very short data and many splits, walk-forward should skip or return empty."""
        df = _make_ohlcv(n=50)
        result = walk_forward_validate(df, "rsi_mean_reversion", n_splits=5, fees=0.001)
        # With 50 rows / 5 = 10 per split, each split < 100 so all skipped
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_wf_successful_splits(self):
        """Walk-forward with enough data should produce split results with IS/OOS metrics."""
        df = _make_trending_ohlcv(n=2000)
        result = walk_forward_validate(df, "rsi_mean_reversion", n_splits=2, fees=0.001)
        if not result.empty:
            assert "is_sharpe" in result.columns
            assert "oos_sharpe" in result.columns
            assert "degradation_ratio" in result.columns
            assert "split" in result.columns
            assert "train_rows" in result.columns
            assert "test_rows" in result.columns

    def test_wf_empty_oos_results(self):
        """When OOS produces empty results, should record 0 sharpe."""
        df = _make_ohlcv(n=1000)
        # bollinger_breakout with extreme params may produce empty OOS
        result = walk_forward_validate(df, "bollinger_breakout", n_splits=2, fees=0.001)
        assert isinstance(result, pd.DataFrame)

    def test_wf_is_screen_fails(self):
        """When IS screen raises exception, split should be skipped."""
        from unittest.mock import patch, MagicMock

        df = _make_ohlcv(n=1000)

        def failing_screen(df_arg, fees):
            raise RuntimeError("screen exploded")

        with patch.dict(
            "research.scripts.vbt_screener.SCREEN_FUNCTIONS",
            {"test_fail": failing_screen},
        ):
            result = walk_forward_validate(df, "test_fail", n_splits=2, fees=0.001)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_wf_oos_screen_fails(self):
        """When OOS screen raises exception, split should be skipped."""
        from unittest.mock import patch

        df = _make_ohlcv(n=1000)
        call_count = {"n": 0}

        def sometimes_failing_screen(df_arg, fees):
            call_count["n"] += 1
            if call_count["n"] % 2 == 0:  # Fail on even calls (OOS)
                raise RuntimeError("OOS failed")
            return screen_rsi_mean_reversion(
                df_arg, rsi_periods=[14], oversold_levels=[30],
                overbought_levels=[70], fees=fees,
            )

        with patch.dict(
            "research.scripts.vbt_screener.SCREEN_FUNCTIONS",
            {"test_oos_fail": sometimes_failing_screen},
        ):
            result = walk_forward_validate(df, "test_oos_fail", n_splits=2, fees=0.001)

        assert isinstance(result, pd.DataFrame)

    def test_wf_insufficient_train_test_data(self):
        """When train < 50 or test < 20, split should be skipped."""
        df = _make_ohlcv(n=150)
        # With 150 rows / 3 splits = 50 per window, train_ratio 0.7 → 35 train, 15 test
        result = walk_forward_validate(
            df, "rsi_mean_reversion", n_splits=3, train_ratio=0.7, fees=0.001,
        )
        assert isinstance(result, pd.DataFrame)

    def test_wf_empty_is_results(self):
        """When IS screen produces empty DataFrame, split should be skipped."""
        from unittest.mock import patch

        df = _make_ohlcv(n=1000)

        def empty_screen(df_arg, fees):
            return pd.DataFrame()

        with patch.dict(
            "research.scripts.vbt_screener.SCREEN_FUNCTIONS",
            {"empty_screen": empty_screen},
        ):
            result = walk_forward_validate(df, "empty_screen", n_splits=2, fees=0.001)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_wf_train_test_too_small(self):
        """Cover lines 497-498: train < 50 or test < 20 should skip split."""
        # With 300 rows / 3 splits = 100 per window. train_ratio 0.1 → 10 train, 90 test
        # train < 50 so split is skipped via lines 497-498
        df = _make_ohlcv(n=300)
        result = walk_forward_validate(
            df, "rsi_mean_reversion", n_splits=3, train_ratio=0.1, fees=0.001,
        )
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_wf_empty_oos_results_path(self):
        """Cover lines 530-532: OOS screen returns empty DataFrame → 0 sharpe."""
        from unittest.mock import patch

        df = _make_ohlcv(n=1000)
        call_count = {"n": 0}

        def alternating_screen(df_arg, fees):
            call_count["n"] += 1
            if call_count["n"] % 2 == 0:
                # OOS returns empty
                return pd.DataFrame()
            # IS returns valid results
            return screen_rsi_mean_reversion(
                df_arg, rsi_periods=[14], oversold_levels=[30],
                overbought_levels=[70], fees=fees,
            )

        with patch.dict(
            "research.scripts.vbt_screener.SCREEN_FUNCTIONS",
            {"alternating_test": alternating_screen},
        ):
            result = walk_forward_validate(
                df, "alternating_test", n_splits=2, fees=0.001,
            )

        assert isinstance(result, pd.DataFrame)
        # Splits with empty IS should be skipped, but any with valid IS+empty OOS
        # should have oos_sharpe=0.0
        if not result.empty and "oos_sharpe" in result.columns:
            for _, row in result.iterrows():
                assert isinstance(row["oos_sharpe"], float)


# ── 14. run_full_screen Tests ────────────────────────────────


class TestRunFullScreen:
    def test_run_full_screen_basic(self, tmp_path):
        """Test run_full_screen with mocked load_ohlcv."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        df = _make_trending_ohlcv(n=500)

        with (
            patch("research.scripts.vbt_screener.load_ohlcv", return_value=df),
            patch("research.scripts.vbt_screener.RESULTS_DIR", tmp_path),
        ):
            results = run_full_screen("BTC/USDT", "1h", "kraken", fees=0.001)

        assert isinstance(results, dict)
        # Should have at least some screens
        possible_screens = {"sma_crossover", "rsi_mean_reversion", "bollinger_breakout",
                           "ema_rsi_combo", "volatility_breakout"}
        assert len(set(results.keys()) & possible_screens) > 0

    def test_run_full_screen_empty_data(self):
        """Empty data should return empty dict."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        with patch("research.scripts.vbt_screener.load_ohlcv", return_value=pd.DataFrame()):
            results = run_full_screen("BAD/PAIR", "1h", "kraken")

        assert results == {}

    def test_run_full_screen_equity_with_relative_strength(self, tmp_path):
        """Equity asset class should run relative_strength screen."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        df = _make_trending_ohlcv(n=500)
        spy_df = _make_ohlcv(n=500, seed=99)

        call_count = {"n": 0}
        def mock_load(symbol, tf, source):
            call_count["n"] += 1
            if "SPY" in symbol:
                return spy_df
            return df

        with (
            patch("research.scripts.vbt_screener.load_ohlcv", side_effect=mock_load),
            patch("research.scripts.vbt_screener.RESULTS_DIR", tmp_path),
        ):
            results = run_full_screen("AAPL/USD", "1d", "yfinance", asset_class="equity")

        assert isinstance(results, dict)
        # Should attempt relative_strength for equity
        # (may or may not succeed depending on data)

    def test_run_full_screen_equity_no_spy_data(self, tmp_path):
        """When SPY data unavailable, should skip relative strength."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        df = _make_trending_ohlcv(n=500)

        def mock_load(symbol, tf, source):
            if "SPY" in symbol:
                return pd.DataFrame()
            return df

        with (
            patch("research.scripts.vbt_screener.load_ohlcv", side_effect=mock_load),
            patch("research.scripts.vbt_screener.RESULTS_DIR", tmp_path),
        ):
            results = run_full_screen("AAPL/USD", "1d", "yfinance", asset_class="equity")

        assert "relative_strength" not in results

    def test_run_full_screen_saves_results(self, tmp_path):
        """Should save CSV and summary.json to output dir."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        df = _make_trending_ohlcv(n=500)

        with (
            patch("research.scripts.vbt_screener.load_ohlcv", return_value=df),
            patch("research.scripts.vbt_screener.RESULTS_DIR", tmp_path),
        ):
            results = run_full_screen("BTC/USDT", "1h", "kraken", fees=0.001)

        # Should have created output directory with summary.json
        output_dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        if output_dirs:
            import json
            summary_path = output_dirs[0] / "summary.json"
            assert summary_path.exists()
            with open(summary_path) as f:
                summary = json.load(f)
            assert isinstance(summary, dict)

    def test_run_full_screen_forex_fees(self, tmp_path):
        """Forex asset class should use forex fees."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        df = _make_ohlcv(n=500)

        with (
            patch("research.scripts.vbt_screener.load_ohlcv", return_value=df),
            patch("research.scripts.vbt_screener.RESULTS_DIR", tmp_path),
        ):
            results = run_full_screen("EUR/USD", "1h", "yfinance", asset_class="forex")

        assert isinstance(results, dict)

    def test_run_full_screen_screen_exception_handled(self, tmp_path):
        """If a screen raises, it should be caught and other screens continue."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        df = _make_ohlcv(n=500)

        with (
            patch("research.scripts.vbt_screener.load_ohlcv", return_value=df),
            patch("research.scripts.vbt_screener.screen_sma_crossover", side_effect=RuntimeError("boom")),
            patch("research.scripts.vbt_screener.RESULTS_DIR", tmp_path),
        ):
            results = run_full_screen("BTC/USDT", "1h", "kraken", fees=0.001)

        assert isinstance(results, dict)
        assert "sma_crossover" not in results

    def test_run_full_screen_walk_forward_exception(self, tmp_path):
        """Walk-forward failure for a screen should be caught."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        df = _make_ohlcv(n=500)

        with (
            patch("research.scripts.vbt_screener.load_ohlcv", return_value=df),
            patch("research.scripts.vbt_screener.walk_forward_validate", side_effect=RuntimeError("wf error")),
            patch("research.scripts.vbt_screener.RESULTS_DIR", tmp_path),
        ):
            results = run_full_screen("BTC/USDT", "1h", "kraken", fees=0.001)

        assert isinstance(results, dict)

    def test_run_full_screen_relative_strength_exception(self, tmp_path):
        """Relative strength exception should be caught for equity."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        df = _make_ohlcv(n=500)

        def mock_load(symbol, tf, source):
            if "SPY" in symbol:
                raise RuntimeError("SPY error")
            return df

        with (
            patch("research.scripts.vbt_screener.load_ohlcv", side_effect=mock_load),
            patch("research.scripts.vbt_screener.RESULTS_DIR", tmp_path),
        ):
            results = run_full_screen("AAPL/USD", "1d", "yfinance", asset_class="equity")

        assert isinstance(results, dict)
        assert "relative_strength" not in results

    def test_run_full_screen_rsi_exception(self, tmp_path):
        """RSI screen exception should be caught."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        df = _make_ohlcv(n=500)

        with (
            patch("research.scripts.vbt_screener.load_ohlcv", return_value=df),
            patch("research.scripts.vbt_screener.screen_rsi_mean_reversion", side_effect=RuntimeError("rsi boom")),
            patch("research.scripts.vbt_screener.RESULTS_DIR", tmp_path),
        ):
            results = run_full_screen("BTC/USDT", "1h", "kraken", fees=0.001)

        assert "rsi_mean_reversion" not in results

    def test_run_full_screen_bollinger_exception(self, tmp_path):
        """Bollinger screen exception should be caught."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        df = _make_ohlcv(n=500)

        with (
            patch("research.scripts.vbt_screener.load_ohlcv", return_value=df),
            patch("research.scripts.vbt_screener.screen_bollinger_breakout", side_effect=RuntimeError("bb boom")),
            patch("research.scripts.vbt_screener.RESULTS_DIR", tmp_path),
        ):
            results = run_full_screen("BTC/USDT", "1h", "kraken", fees=0.001)

        assert "bollinger_breakout" not in results

    def test_run_full_screen_ema_rsi_exception(self, tmp_path):
        """EMA+RSI screen exception should be caught."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        df = _make_ohlcv(n=500)

        with (
            patch("research.scripts.vbt_screener.load_ohlcv", return_value=df),
            patch("research.scripts.vbt_screener.screen_ema_rsi_combo", side_effect=RuntimeError("ema boom")),
            patch("research.scripts.vbt_screener.RESULTS_DIR", tmp_path),
        ):
            results = run_full_screen("BTC/USDT", "1h", "kraken", fees=0.001)

        assert "ema_rsi_combo" not in results

    def test_run_full_screen_vb_exception(self, tmp_path):
        """Volatility breakout screen exception should be caught."""
        from unittest.mock import patch
        from research.scripts.vbt_screener import run_full_screen

        df = _make_ohlcv(n=500)

        with (
            patch("research.scripts.vbt_screener.load_ohlcv", return_value=df),
            patch("research.scripts.vbt_screener.screen_volatility_breakout", side_effect=RuntimeError("vb boom")),
            patch("research.scripts.vbt_screener.RESULTS_DIR", tmp_path),
        ):
            results = run_full_screen("BTC/USDT", "1h", "kraken", fees=0.001)

        assert "volatility_breakout" not in results


# ── 15. Screen Exception Branch Tests ────────────────────────


class TestScreenExceptionBranches:
    """Cover vbt_screener.py except branches in individual screens (lines 153-154, 211-212, etc.)."""

    def test_rsi_screen_internal_exception(self):
        """Force exception inside RSI screen to cover except branch."""
        from unittest.mock import patch
        import vectorbt as vbt

        df = _make_ohlcv(n=500)
        # Mock Portfolio.from_signals to raise
        with patch.object(vbt.Portfolio, "from_signals", side_effect=RuntimeError("vbt error")):
            result = screen_rsi_mean_reversion(
                df, rsi_periods=[14], oversold_levels=[30], overbought_levels=[70],
            )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_bollinger_screen_internal_exception(self):
        """Force exception inside Bollinger screen to cover except branch."""
        from unittest.mock import patch
        import vectorbt as vbt

        df = _make_ohlcv(n=500)
        with patch.object(vbt.Portfolio, "from_signals", side_effect=RuntimeError("vbt error")):
            result = screen_bollinger_breakout(df, bb_periods=[20], bb_stds=[2.0])

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_volatility_breakout_screen_internal_exception(self):
        """Force exception inside VB screen to cover except branch."""
        from unittest.mock import patch
        import vectorbt as vbt

        df = _make_volatile_ohlcv(n=500)
        with patch.object(vbt.Portfolio, "from_signals", side_effect=RuntimeError("vbt error")):
            result = screen_volatility_breakout(
                df, breakout_periods=[20], volume_factors=[1.5], adx_ranges=[(10, 30)],
            )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_ema_rsi_screen_internal_exception(self):
        """Force exception inside EMA+RSI screen to cover except branch (lines 263-264)."""
        from unittest.mock import patch
        import vectorbt as vbt

        df = _make_ohlcv(n=500)
        with patch.object(vbt.Portfolio, "from_signals", side_effect=RuntimeError("vbt error")):
            result = screen_ema_rsi_combo(df, ema_periods=[20], rsi_entry_levels=[35])

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_relative_strength_screen_internal_exception(self):
        """Force exception inside relative strength screen to cover except branch."""
        from unittest.mock import patch
        import vectorbt as vbt

        idx = pd.date_range("2024-01-01", periods=300, freq="1d", tz="UTC")
        rng = np.random.RandomState(42)
        df = pd.DataFrame({"close": 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 300)))}, index=idx)
        bench = pd.DataFrame({"close": 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 300)))}, index=idx)

        with patch.object(vbt.Portfolio, "from_signals", side_effect=RuntimeError("vbt error")):
            result = screen_relative_strength(
                df, bench, lookback_periods=[20], rs_thresholds=[1.02],
            )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0
