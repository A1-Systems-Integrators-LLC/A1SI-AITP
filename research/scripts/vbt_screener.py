"""
VectorBT Strategy Research & Screening Engine
==============================================
Rapid strategy screening using vectorized backtesting.
Screens thousands of parameter combinations in seconds.

Workflow:
    1. Load data from shared pipeline
    2. Run parameter sweeps across strategy variants
    3. Rank results by composite score
    4. Export top candidates for Freqtrade/Nautilus event-driven backtesting
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
import vectorbt as vbt

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.data_pipeline.pipeline import load_ohlcv  # noqa: E402
from common.indicators.technical import sma, ema, rsi, adx, bollinger_bands  # noqa: E402

logger = logging.getLogger("vbt_screener")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RESULTS_DIR = PROJECT_ROOT / "research" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────
# Strategy Definitions
# ──────────────────────────────────────────────

def screen_sma_crossover(
    close: pd.Series,
    fast_windows: list = None,
    slow_windows: list = None,
    fees: float = 0.001,
) -> pd.DataFrame:
    """
    Screen SMA crossover strategies across parameter grid.

    Tests all combinations of fast/slow moving average windows.
    """
    if fast_windows is None:
        fast_windows = list(range(5, 50, 5))
    if slow_windows is None:
        slow_windows = list(range(20, 200, 10))

    logger.info(
        f"Screening SMA crossover: {len(fast_windows)} fast x {len(slow_windows)} slow "
        f"= {len(fast_windows) * len(slow_windows)} combinations"
    )

    # VectorBT parameter sweep
    fast_ma, slow_ma = vbt.MA.run_combs(
        close,
        window=fast_windows + slow_windows,
        r=2,
        short_names=["fast", "slow"],
    )

    # Generate entries/exits from crossovers
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run portfolio simulation
    pf = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        fees=fees,
        freq="1h",
        init_cash=10000,
    )

    # Extract metrics
    results = pd.DataFrame({
        "total_return": pf.total_return(),
        "sharpe_ratio": pf.sharpe_ratio(),
        "max_drawdown": pf.max_drawdown(),
        "win_rate": pf.trades.win_rate(),
        "profit_factor": pf.trades.profit_factor(),
        "num_trades": pf.trades.count(),
        "avg_trade_pnl": pf.trades.pnl.mean(),
    })

    results = results.sort_values("sharpe_ratio", ascending=False)
    logger.info(f"Screening complete. Top Sharpe: {results['sharpe_ratio'].iloc[0]:.3f}")
    return results


def screen_rsi_mean_reversion(
    df: pd.DataFrame,
    rsi_periods: list = None,
    oversold_levels: list = None,
    overbought_levels: list = None,
    fees: float = 0.001,
) -> pd.DataFrame:
    """
    Screen RSI mean-reversion strategies.

    Buy when RSI drops below oversold, sell when RSI rises above overbought.
    """
    if rsi_periods is None:
        rsi_periods = [7, 10, 14, 21]
    if oversold_levels is None:
        oversold_levels = [20, 25, 30, 35]
    if overbought_levels is None:
        overbought_levels = [65, 70, 75, 80]

    close = df["close"]
    results = []

    for period in rsi_periods:
        rsi_values = rsi(close, period)
        for os_level in oversold_levels:
            for ob_level in overbought_levels:
                if os_level >= ob_level:
                    continue

                entries = rsi_values < os_level
                exits = rsi_values > ob_level

                try:
                    pf = vbt.Portfolio.from_signals(
                        close,
                        entries=entries,
                        exits=exits,
                        fees=fees,
                        freq="1h",
                        init_cash=10000,
                    )

                    results.append({
                        "rsi_period": period,
                        "oversold": os_level,
                        "overbought": ob_level,
                        "total_return": pf.total_return(),
                        "sharpe_ratio": pf.sharpe_ratio(),
                        "max_drawdown": pf.max_drawdown(),
                        "win_rate": pf.trades.win_rate() if pf.trades.count() > 0 else 0,
                        "profit_factor": pf.trades.profit_factor() if pf.trades.count() > 0 else 0,
                        "num_trades": pf.trades.count(),
                    })
                except Exception as e:
                    logger.debug(f"Skipping RSI({period}, {os_level}, {ob_level}): {e}")

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df = results_df.sort_values("sharpe_ratio", ascending=False)
    logger.info(f"RSI screening complete: {len(results_df)} parameter combos tested")
    return results_df


def screen_bollinger_breakout(
    df: pd.DataFrame,
    bb_periods: list = None,
    bb_stds: list = None,
    fees: float = 0.001,
) -> pd.DataFrame:
    """
    Screen Bollinger Band breakout strategies.

    Buy when price closes above upper band, sell when it closes below lower band.
    """
    if bb_periods is None:
        bb_periods = [10, 15, 20, 25, 30]
    if bb_stds is None:
        bb_stds = [1.5, 2.0, 2.5, 3.0]

    close = df["close"]
    results = []

    for period in bb_periods:
        mid = sma(close, period)
        std = close.rolling(window=period).std()
        for std_mult in bb_stds:
            upper = mid + (std * std_mult)
            lower = mid - (std * std_mult)

            entries = close > upper
            exits = close < lower

            try:
                pf = vbt.Portfolio.from_signals(
                    close,
                    entries=entries,
                    exits=exits,
                    fees=fees,
                    freq="1h",
                    init_cash=10000,
                )
                results.append({
                    "bb_period": period,
                    "bb_std": std_mult,
                    "total_return": pf.total_return(),
                    "sharpe_ratio": pf.sharpe_ratio(),
                    "max_drawdown": pf.max_drawdown(),
                    "win_rate": pf.trades.win_rate() if pf.trades.count() > 0 else 0,
                    "profit_factor": pf.trades.profit_factor() if pf.trades.count() > 0 else 0,
                    "num_trades": pf.trades.count(),
                })
            except Exception as e:
                logger.debug(f"Skipping BB({period}, {std_mult}): {e}")

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df = results_df.sort_values("sharpe_ratio", ascending=False)
    return results_df


def screen_ema_rsi_combo(
    df: pd.DataFrame,
    ema_periods: list = None,
    rsi_entry_levels: list = None,
    fees: float = 0.001,
) -> pd.DataFrame:
    """
    Screen combined EMA trend + RSI momentum strategies.

    Buy when price > EMA (uptrend) AND RSI < oversold (pullback entry).
    Sell when price < EMA OR RSI > overbought.
    """
    if ema_periods is None:
        ema_periods = [20, 50, 100]
    if rsi_entry_levels is None:
        rsi_entry_levels = [30, 35, 40]

    close = df["close"]
    rsi_14 = rsi(close, 14)
    results = []

    for ema_p in ema_periods:
        ema_val = ema(close, ema_p)
        in_uptrend = close > ema_val

        for rsi_entry in rsi_entry_levels:
            entries = in_uptrend & (rsi_14 < rsi_entry)
            exits = (close < ema_val) | (rsi_14 > 75)

            try:
                pf = vbt.Portfolio.from_signals(
                    close, entries=entries, exits=exits,
                    fees=fees, freq="1h", init_cash=10000,
                )
                results.append({
                    "ema_period": ema_p,
                    "rsi_entry": rsi_entry,
                    "total_return": pf.total_return(),
                    "sharpe_ratio": pf.sharpe_ratio(),
                    "max_drawdown": pf.max_drawdown(),
                    "win_rate": pf.trades.win_rate() if pf.trades.count() > 0 else 0,
                    "num_trades": pf.trades.count(),
                })
            except Exception:
                pass

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df = results_df.sort_values("sharpe_ratio", ascending=False)
    return results_df


def screen_volatility_breakout(
    df: pd.DataFrame,
    breakout_periods: list = None,
    volume_factors: list = None,
    adx_ranges: list = None,
    fees: float = 0.001,
) -> pd.DataFrame:
    """
    Screen volatility breakout strategies.

    Buy when close breaks above N-period high with volume spike,
    expanding BB width, and ADX in emerging-trend range.
    Sell when RSI > 85 (exhaustion) or price crosses below EMA(20).
    """
    if breakout_periods is None:
        breakout_periods = [10, 15, 20, 25, 30]
    if volume_factors is None:
        volume_factors = [1.2, 1.5, 2.0, 2.5]
    if adx_ranges is None:
        adx_ranges = [(10, 25), (15, 30), (15, 25)]

    close = df["close"]
    high = df["high"]
    volume = df["volume"]
    rsi_14 = rsi(close, 14)
    adx_14 = adx(df, 14)
    ema_20 = ema(close, 20)
    volume_sma = sma(volume, 20)
    volume_ratio = volume / volume_sma
    bb = bollinger_bands(close, 20, 2.0)
    bb_width = bb["bb_width"]
    bb_width_expanding = bb_width > bb_width.shift(1)

    results = []

    for bp in breakout_periods:
        n_high = high.rolling(window=bp).max().shift(1)
        breakout = close > n_high

        for vf in volume_factors:
            vol_ok = volume_ratio > vf

            for adx_lo, adx_hi in adx_ranges:
                adx_ok = (adx_14 >= adx_lo) & (adx_14 <= adx_hi) & (adx_14 > adx_14.shift(1))
                rsi_ok = (rsi_14 >= 40) & (rsi_14 <= 70)

                entries = breakout & vol_ok & bb_width_expanding & adx_ok & rsi_ok & (volume > 0)
                exits = (rsi_14 > 85) | (
                    (close < ema_20)
                    & (close.shift(1) >= ema_20.shift(1))
                    & (volume_ratio > 1.0)
                )
                entries = entries.fillna(False)
                exits = exits.fillna(False)

                try:
                    pf = vbt.Portfolio.from_signals(
                        close,
                        entries=entries,
                        exits=exits,
                        fees=fees,
                        freq="1h",
                        init_cash=10000,
                        sl_stop=0.03,
                    )
                    results.append({
                        "breakout_period": bp,
                        "volume_factor": vf,
                        "adx_low": adx_lo,
                        "adx_high": adx_hi,
                        "total_return": pf.total_return(),
                        "sharpe_ratio": pf.sharpe_ratio(),
                        "max_drawdown": pf.max_drawdown(),
                        "win_rate": pf.trades.win_rate() if pf.trades.count() > 0 else 0,
                        "profit_factor": pf.trades.profit_factor() if pf.trades.count() > 0 else 0,
                        "num_trades": pf.trades.count(),
                    })
                except Exception as e:
                    logger.debug(f"Skipping VB({bp}, {vf}, {adx_lo}-{adx_hi}): {e}")

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df = results_df.sort_values("sharpe_ratio", ascending=False)
    logger.info(f"Volatility breakout screening complete: {len(results_df)} combos tested")
    return results_df


def screen_relative_strength(
    df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    lookback_periods: list = None,
    rs_thresholds: list = None,
    fees: float = 0.0,
) -> pd.DataFrame:
    """
    Screen relative strength strategies for equities (vs a benchmark like SPY).

    Buy when asset's relative strength vs benchmark exceeds threshold.
    Sell when relative strength drops below 1.0 (underperforming benchmark).
    """
    if lookback_periods is None:
        lookback_periods = [20, 50, 100, 200]
    if rs_thresholds is None:
        rs_thresholds = [1.02, 1.05, 1.10, 1.15]

    close = df["close"]
    bench_close = benchmark_df["close"]

    # Align to common index
    common_idx = close.index.intersection(bench_close.index)
    if len(common_idx) < 50:
        logger.warning("Insufficient overlapping data for relative strength screen")
        return pd.DataFrame()

    close = close.loc[common_idx]
    bench_close = bench_close.loc[common_idx]

    results = []

    for lookback in lookback_periods:
        # Relative strength = (asset return over lookback) / (benchmark return over lookback)
        asset_return = close / close.shift(lookback)
        bench_return = bench_close / bench_close.shift(lookback)
        relative_strength = asset_return / bench_return.replace(0, float("nan"))

        for threshold in rs_thresholds:
            entries = relative_strength > threshold
            exits = relative_strength < 1.0

            try:
                pf = vbt.Portfolio.from_signals(
                    close,
                    entries=entries,
                    exits=exits,
                    fees=fees,
                    freq="1d",
                    init_cash=10000,
                )
                results.append({
                    "lookback": lookback,
                    "rs_threshold": threshold,
                    "total_return": pf.total_return(),
                    "sharpe_ratio": pf.sharpe_ratio(),
                    "max_drawdown": pf.max_drawdown(),
                    "win_rate": pf.trades.win_rate() if pf.trades.count() > 0 else 0,
                    "profit_factor": pf.trades.profit_factor() if pf.trades.count() > 0 else 0,
                    "num_trades": pf.trades.count(),
                })
            except Exception as e:
                logger.debug(f"Skipping RS({lookback}, {threshold}): {e}")

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df = results_df.sort_values("sharpe_ratio", ascending=False)
    logger.info(f"Relative strength screening complete: {len(results_df)} combos tested")
    return results_df


# ──────────────────────────────────────────────
# Walk-Forward Out-of-Sample Validation
# ──────────────────────────────────────────────

# Strategy screen functions keyed by name for walk-forward dispatch
SCREEN_FUNCTIONS = {
    "sma_crossover": lambda df, fees: screen_sma_crossover(df["close"], fees=fees),
    "rsi_mean_reversion": lambda df, fees: screen_rsi_mean_reversion(df, fees=fees),
    "bollinger_breakout": lambda df, fees: screen_bollinger_breakout(df, fees=fees),
    "ema_rsi_combo": lambda df, fees: screen_ema_rsi_combo(df, fees=fees),
    "volatility_breakout": lambda df, fees: screen_volatility_breakout(df, fees=fees),
}


def walk_forward_validate(
    df: pd.DataFrame,
    strategy_name: str,
    n_splits: int = 3,
    train_ratio: float = 0.7,
    fees: float = 0.001,
) -> pd.DataFrame:
    """Walk-forward out-of-sample validation for a strategy screen.

    Splits data into sequential windows. For each window:
      1. Optimize parameters on the train portion
      2. Evaluate the best parameters on the OOS test portion

    This prevents curve-fitting by ensuring every reported metric
    comes from data the optimizer never saw.

    Args:
        df: Full OHLCV DataFrame.
        strategy_name: Key in SCREEN_FUNCTIONS.
        n_splits: Number of walk-forward windows.
        train_ratio: Fraction of each window used for training.
        fees: Trading fees.

    Returns:
        DataFrame with one row per split showing IS and OOS metrics.
    """
    if strategy_name not in SCREEN_FUNCTIONS:
        raise ValueError(f"Unknown strategy: {strategy_name}. Options: {list(SCREEN_FUNCTIONS.keys())}")

    screen_fn = SCREEN_FUNCTIONS[strategy_name]
    n_rows = len(df)
    window_size = n_rows // n_splits
    results = []

    logger.info(
        f"Walk-forward validation: {strategy_name}, {n_splits} splits, "
        f"{n_rows} total rows, ~{window_size} per window"
    )

    for i in range(n_splits):
        start = i * window_size
        end = min(start + window_size, n_rows)
        if end - start < 100:
            logger.warning(f"Split {i + 1}: too few rows ({end - start}), skipping")
            continue

        window_df = df.iloc[start:end].copy()
        train_end = int(len(window_df) * train_ratio)

        train_df = window_df.iloc[:train_end]
        test_df = window_df.iloc[train_end:]

        if len(train_df) < 50 or len(test_df) < 20:
            logger.warning(f"Split {i + 1}: insufficient data (train={len(train_df)}, test={len(test_df)})")
            continue

        # Phase 1: Optimize on training data
        try:
            is_results = screen_fn(train_df, fees)
        except Exception as e:
            logger.error(f"Split {i + 1} IS screen failed: {e}")
            continue

        if is_results.empty:
            logger.warning(f"Split {i + 1}: no valid IS results")
            continue

        # Get best params from IS (first row after sort by sharpe)
        best_row = is_results.iloc[0]
        best_params = {
            col: best_row[col]
            for col in is_results.columns
            if col not in {
                "total_return", "sharpe_ratio", "max_drawdown",
                "win_rate", "profit_factor", "num_trades", "avg_trade_pnl",
            }
        }

        # Phase 2: Evaluate best params on OOS test data
        try:
            oos_results = screen_fn(test_df, fees)
        except Exception as e:
            logger.error(f"Split {i + 1} OOS screen failed: {e}")
            continue

        if oos_results.empty:
            oos_sharpe = 0.0
            oos_return = 0.0
            oos_drawdown = 0.0
        else:
            # Find matching params in OOS results, or take the best OOS result
            oos_best = oos_results.iloc[0]
            oos_sharpe = float(oos_best.get("sharpe_ratio", 0))
            oos_return = float(oos_best.get("total_return", 0))
            oos_drawdown = float(oos_best.get("max_drawdown", 0))

        is_sharpe = float(best_row.get("sharpe_ratio", 0))
        is_return = float(best_row.get("total_return", 0))
        is_drawdown = float(best_row.get("max_drawdown", 0))

        # Degradation ratio: how much worse is OOS vs IS?
        degradation = oos_sharpe / is_sharpe if is_sharpe > 0 else 0.0

        results.append({
            "split": i + 1,
            "train_rows": len(train_df),
            "test_rows": len(test_df),
            "is_sharpe": round(is_sharpe, 4),
            "is_return": round(is_return, 4),
            "is_max_drawdown": round(is_drawdown, 4),
            "oos_sharpe": round(oos_sharpe, 4),
            "oos_return": round(oos_return, 4),
            "oos_max_drawdown": round(oos_drawdown, 4),
            "degradation_ratio": round(degradation, 4),
            **{f"best_{k}": v for k, v in best_params.items()},
        })

        logger.info(
            f"Split {i + 1}: IS Sharpe={is_sharpe:.3f}, OOS Sharpe={oos_sharpe:.3f}, "
            f"degradation={degradation:.2f}"
        )

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        avg_oos = results_df["oos_sharpe"].mean()
        avg_deg = results_df["degradation_ratio"].mean()
        logger.info(
            f"Walk-forward complete: avg OOS Sharpe={avg_oos:.3f}, "
            f"avg degradation={avg_deg:.2f}"
        )
        # Flag: robust if avg OOS Sharpe > 0 and degradation > 0.5
        robust = avg_oos > 0 and avg_deg > 0.5
        logger.info(f"Robustness verdict: {'PASS' if robust else 'FAIL'}")
    else:
        logger.warning("Walk-forward validation produced no results")

    return results_df


# ──────────────────────────────────────────────
# Composite Screener
# ──────────────────────────────────────────────

_ASSET_CLASS_FEES: dict[str, float] = {
    "crypto": 0.001,   # 0.1%
    "equity": 0.0,     # Commission-free
    "forex": 0.0001,   # ~1 pip spread
}


def run_full_screen(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    exchange: str = "kraken",
    fees: float | None = None,
    asset_class: str = "crypto",
) -> dict:
    """
    Run all strategy screens for a given symbol and return ranked results.

    When asset_class is "equity", also runs a relative strength screen
    using SPY as benchmark (if data available).
    """
    if fees is None:
        fees = _ASSET_CLASS_FEES.get(asset_class, 0.001)

    source = "yfinance" if asset_class in ("equity", "forex") else exchange
    logger.info(f"=== Full strategy screen: {symbol} {timeframe} on {source} ({asset_class}) ===")

    df = load_ohlcv(symbol, timeframe, source)
    if df.empty:
        logger.error(f"No data available for {symbol} {timeframe}. Run data pipeline first.")
        return {}

    close = df["close"]
    results = {}

    # 1. SMA Crossover
    logger.info("Running SMA crossover screen...")
    try:
        results["sma_crossover"] = screen_sma_crossover(close, fees=fees)
    except Exception as e:
        logger.error(f"SMA crossover screen failed: {e}")

    # 2. RSI Mean Reversion
    logger.info("Running RSI mean-reversion screen...")
    try:
        results["rsi_mean_reversion"] = screen_rsi_mean_reversion(df, fees=fees)
    except Exception as e:
        logger.error(f"RSI screen failed: {e}")

    # 3. Bollinger Breakout
    logger.info("Running Bollinger breakout screen...")
    try:
        results["bollinger_breakout"] = screen_bollinger_breakout(df, fees=fees)
    except Exception as e:
        logger.error(f"Bollinger screen failed: {e}")

    # 4. EMA + RSI Combo
    logger.info("Running EMA+RSI combo screen...")
    try:
        results["ema_rsi_combo"] = screen_ema_rsi_combo(df, fees=fees)
    except Exception as e:
        logger.error(f"EMA+RSI screen failed: {e}")

    # 5. Volatility Breakout
    logger.info("Running Volatility breakout screen...")
    try:
        results["volatility_breakout"] = screen_volatility_breakout(df, fees=fees)
    except Exception as e:
        logger.error(f"Volatility breakout screen failed: {e}")

    # 6. Relative Strength (equities only, vs SPY benchmark)
    if asset_class == "equity":
        logger.info("Running Relative Strength screen (vs SPY)...")
        try:
            spy_df = load_ohlcv("SPY/USD", timeframe, "yfinance")
            if not spy_df.empty:
                results["relative_strength"] = screen_relative_strength(
                    df, spy_df, fees=fees,
                )
            else:
                logger.warning("SPY benchmark data not available, skipping relative strength")
        except Exception as e:
            logger.error(f"Relative strength screen failed: {e}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_symbol = symbol.replace("/", "_")
    output_dir = RESULTS_DIR / f"{safe_symbol}_{timeframe}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {}
    for name, df_result in results.items():
        if isinstance(df_result, pd.DataFrame) and not df_result.empty:
            path = output_dir / f"{name}.csv"
            df_result.to_csv(path)
            top = df_result.head(3)
            summary[name] = {
                "total_combos": len(df_result),
                "top_sharpe": float(top["sharpe_ratio"].iloc[0]) if "sharpe_ratio" in top.columns else None,
                "top_return": float(top["total_return"].iloc[0]) if "total_return" in top.columns else None,
            }

    # Walk-forward OOS validation for each strategy
    wf_summary = {}
    logger.info("Running walk-forward OOS validation...")
    for name in results:
        try:
            wf = walk_forward_validate(df, name, n_splits=3, fees=fees)
            if not wf.empty:
                wf_path = output_dir / f"{name}_walkforward.csv"
                wf.to_csv(wf_path, index=False)
                avg_oos = float(wf["oos_sharpe"].mean())
                avg_deg = float(wf["degradation_ratio"].mean())
                wf_summary[name] = {
                    "avg_oos_sharpe": round(avg_oos, 4),
                    "avg_degradation": round(avg_deg, 4),
                    "robust": avg_oos > 0 and avg_deg > 0.5,
                    "splits": len(wf),
                }
        except Exception as e:
            logger.error(f"Walk-forward for {name} failed: {e}")

    summary["walk_forward"] = wf_summary

    # Save summary
    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    logger.info(f"Results saved to {output_dir}")
    logger.info(f"Summary: {json.dumps(summary, indent=2, default=str)}")
    return results


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VectorBT Strategy Screener")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair")
    parser.add_argument("--timeframe", default="1h", help="Candle timeframe")
    parser.add_argument("--exchange", default="kraken", help="Exchange")
    parser.add_argument("--fees", type=float, default=None, help="Trading fees (0.001 = 0.1%%)")
    parser.add_argument("--asset-class", default="crypto", choices=["crypto", "equity", "forex"],
                        dest="asset_class", help="Asset class")
    parser.add_argument(
        "--walk-forward-only",
        metavar="STRATEGY",
        help="Run walk-forward OOS validation for a single strategy instead of full screen",
    )
    parser.add_argument("--splits", type=int, default=3, help="Number of walk-forward splits")

    args = parser.parse_args()
    fees = args.fees if args.fees is not None else _ASSET_CLASS_FEES.get(args.asset_class, 0.001)

    if args.walk_forward_only:
        from common.data_pipeline.pipeline import load_ohlcv as _load

        source = "yfinance" if args.asset_class in ("equity", "forex") else args.exchange
        _df = _load(args.symbol, args.timeframe, source)
        if _df.empty:
            logger.error(f"No data for {args.symbol} {args.timeframe}")
        else:
            wf = walk_forward_validate(
                _df, args.walk_forward_only, n_splits=args.splits, fees=fees,
            )
            if not wf.empty:
                print(wf.to_string(index=False))
    else:
        run_full_screen(args.symbol, args.timeframe, args.exchange, fees, args.asset_class)
