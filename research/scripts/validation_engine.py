"""
Gate 2+3 Strategy Validation Engine
====================================
Shared infrastructure for validating Freqtrade strategies via VectorBT.

Gate 2 (VectorBT Screen):
    - Sharpe ratio > 1.0
    - Max drawdown < 20%
    - > 30 trades per year (annualized)
    - Statistically significant (one-sided t-test p < 0.05 on trade PnLs)

Gate 3 (Backtest Validation):
    - Walk-forward OOS: avg OOS Sharpe >= 50% of avg IS Sharpe
    - Parameter perturbation: ±20% perturbation maintains positive Sharpe
    - Realistic transaction costs (0.1% fee + 0.05% slippage = 0.15%)
"""

import sys
import json
import logging
import itertools
from pathlib import Path
from datetime import datetime
from typing import Callable

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("validation_engine")

RESULTS_DIR = PROJECT_ROOT / "research" / "results" / "validation"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Gate criteria ─────────────────────────────────────────────
GATE2_MIN_SHARPE = 1.0
GATE2_MAX_DRAWDOWN = 0.20
GATE2_MIN_TRADES_PER_YEAR = 30
GATE2_PVALUE = 0.05

GATE3_OOS_SHARPE_FLOOR = 0.50  # OOS Sharpe >= 50% of IS Sharpe
GATE3_PERTURB_PCT = 0.20
GATE3_WF_SPLITS = 5

# Realistic costs: 0.1% exchange fee + 0.05% slippage
DEFAULT_FEES = 0.0015

# Type alias for signal generators
SignalFn = Callable[[pd.DataFrame, dict], tuple[pd.Series, pd.Series]]


def generate_synthetic_ohlcv(
    n: int = 5000, freq: str = "1h", seed: int = 42
) -> pd.DataFrame:
    """Generate synthetic OHLCV data with trend + mean-reversion regimes."""
    np.random.seed(seed)
    index = pd.date_range("2023-01-01", periods=n, freq=freq, tz="UTC")

    returns = np.random.randn(n) * 0.005
    for i in range(0, n, 500):
        trend_len = min(200, n - i)
        trend_dir = np.random.choice([-1, 1])
        returns[i : i + trend_len] += trend_dir * 0.001

    close = 50000 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(np.random.randn(n) * 0.005))
    low = close * (1 - np.abs(np.random.randn(n) * 0.005))
    open_ = close * (1 + np.random.randn(n) * 0.002)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    volume = np.abs(np.random.randn(n) * 1000) + 500

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


def _run_backtest(
    close: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    fees: float = DEFAULT_FEES,
    sl_stop: float = 0.05,
    freq: str = "1h",
) -> dict:
    """Run a single VectorBT backtest and extract metrics."""
    import vectorbt as vbt

    entries = entries.fillna(False).astype(bool)
    exits = exits.fillna(False).astype(bool)

    pf = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        fees=fees,
        sl_stop=sl_stop,
        freq=freq,
        init_cash=10000,
    )

    num_trades = int(pf.trades.count())

    # Annualized trade count
    days = (close.index[-1] - close.index[0]).total_seconds() / 86400
    years = max(days / 365.25, 0.01)
    annualized_trades = num_trades / years

    # T-test on trade PnLs for statistical significance
    pvalue = 1.0
    if num_trades >= 2:
        try:
            trade_pnls = pf.trades.pnl.values
            if hasattr(trade_pnls, "to_numpy"):  # pragma: no cover — VBT version-dependent
                trade_pnls = trade_pnls.to_numpy()
            trade_pnls = np.asarray(trade_pnls, dtype=float)
            trade_pnls = trade_pnls[~np.isnan(trade_pnls)]
            if len(trade_pnls) >= 2:
                t_stat, p_two = scipy_stats.ttest_1samp(trade_pnls, 0)
                pvalue = float(p_two / 2) if t_stat > 0 else 1.0
        except Exception:
            pvalue = 1.0

    return {
        "total_return": float(pf.total_return()),
        "sharpe_ratio": float(pf.sharpe_ratio()),
        "max_drawdown": float(pf.max_drawdown()),
        "num_trades": num_trades,
        "annualized_trades": round(annualized_trades, 1),
        "win_rate": float(pf.trades.win_rate()) if num_trades > 0 else 0.0,
        "profit_factor": float(pf.trades.profit_factor()) if num_trades > 0 else 0.0,
        "pvalue": pvalue,
    }


def check_gate2(result: dict) -> tuple[bool, list[str]]:
    """Check if a backtest result passes Gate 2 criteria."""
    failures = []
    sharpe = result.get("sharpe_ratio", float("nan"))

    if np.isnan(sharpe) or sharpe < GATE2_MIN_SHARPE:
        failures.append(f"Sharpe {sharpe:.3f} < {GATE2_MIN_SHARPE}")
    if result.get("max_drawdown", 1.0) > GATE2_MAX_DRAWDOWN:
        failures.append(
            f"Drawdown {result['max_drawdown']:.1%} > {GATE2_MAX_DRAWDOWN:.0%}"
        )
    if result.get("annualized_trades", 0) < GATE2_MIN_TRADES_PER_YEAR:
        failures.append(
            f"Trades/year {result['annualized_trades']:.0f} < {GATE2_MIN_TRADES_PER_YEAR}"
        )
    if result.get("pvalue", 1.0) > GATE2_PVALUE:
        failures.append(f"p-value {result['pvalue']:.4f} > {GATE2_PVALUE}")

    return len(failures) == 0, failures


# ── Gate 2: Parameter Sweep ──────────────────────────────────


def sweep_parameters(
    df: pd.DataFrame,
    signal_fn: SignalFn,
    param_grid: dict[str, list],
    fees: float = DEFAULT_FEES,
    sl_stop: float = 0.05,
    freq: str = "1h",
) -> pd.DataFrame:
    """
    Run Gate 2 parameter sweep across all combinations.

    Returns DataFrame sorted by Sharpe ratio, with passes_gate2 column.
    """
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    combos = list(itertools.product(*param_values))

    logger.info(
        f"Gate 2: Sweeping {len(combos)} parameter combinations "
        f"({' x '.join(f'{k}[{len(v)}]' for k, v in param_grid.items())})"
    )

    close = df["close"]
    results = []

    for i, combo in enumerate(combos):
        params = dict(zip(param_names, combo))
        try:
            entries, exits = signal_fn(df, params)
            metrics = _run_backtest(close, entries, exits, fees, sl_stop, freq)
            passed, failures = check_gate2(metrics)
            metrics["params"] = params
            metrics["passes_gate2"] = passed
            metrics["failure_reasons"] = failures
            results.append(metrics)
        except Exception as e:
            logger.debug(f"Combo {i} failed ({params}): {e}")

        if (i + 1) % 100 == 0:
            logger.info(f"  ... {i + 1}/{len(combos)} combos tested")

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df = results_df.sort_values(
            "sharpe_ratio", ascending=False
        ).reset_index(drop=True)

    passing = int(results_df["passes_gate2"].sum()) if not results_df.empty else 0
    logger.info(
        f"Gate 2 complete: {passing}/{len(results_df)} combos pass all criteria"
    )
    return results_df


# ── Gate 3a: Walk-Forward Validation ─────────────────────────


def walk_forward_validate(
    df: pd.DataFrame,
    signal_fn: SignalFn,
    best_params: dict,
    fees: float = DEFAULT_FEES,
    sl_stop: float = 0.05,
    freq: str = "1h",
    n_splits: int = GATE3_WF_SPLITS,
) -> list[dict]:
    """
    Expanding-window walk-forward out-of-sample validation.

    Splits data into n_splits+1 segments. For fold k (1..n_splits):
      - Train on segments 0..k-1 (expanding window)
      - Test on segment k (fixed window)
    """
    n = len(df)
    segment_size = n // (n_splits + 1)

    if segment_size < 100:
        logger.warning(
            f"Segment size {segment_size} is small — results may be unreliable"
        )

    results = []

    for fold in range(1, n_splits + 1):
        train_end = segment_size * fold
        test_end = min(segment_size * (fold + 1), n)

        train_df = df.iloc[:train_end]
        test_df = df.iloc[train_end:test_end]

        if len(test_df) < 50:
            logger.warning(
                f"Fold {fold}: test set too small ({len(test_df)} rows), skipping"
            )
            continue

        try:
            is_entries, is_exits = signal_fn(train_df, best_params)
            is_metrics = _run_backtest(
                train_df["close"], is_entries, is_exits, fees, sl_stop, freq
            )
        except Exception as e:
            logger.warning(f"Fold {fold} IS failed: {e}")
            continue

        try:
            oos_entries, oos_exits = signal_fn(test_df, best_params)
            oos_metrics = _run_backtest(
                test_df["close"], oos_entries, oos_exits, fees, sl_stop, freq
            )
        except Exception as e:
            logger.warning(f"Fold {fold} OOS failed: {e}")
            continue

        fold_result = {
            "fold": fold,
            "train_rows": len(train_df),
            "test_rows": len(test_df),
            "train_period": f"{train_df.index[0]} to {train_df.index[-1]}",
            "test_period": f"{test_df.index[0]} to {test_df.index[-1]}",
            "is_sharpe": is_metrics["sharpe_ratio"],
            "is_return": is_metrics["total_return"],
            "is_trades": is_metrics["num_trades"],
            "oos_sharpe": oos_metrics["sharpe_ratio"],
            "oos_return": oos_metrics["total_return"],
            "oos_trades": oos_metrics["num_trades"],
        }
        results.append(fold_result)
        logger.info(
            f"  Fold {fold}: IS Sharpe={is_metrics['sharpe_ratio']:.3f}, "
            f"OOS Sharpe={oos_metrics['sharpe_ratio']:.3f}"
        )

    return results


# ── Gate 3b: Parameter Perturbation ──────────────────────────


def perturbation_test(
    df: pd.DataFrame,
    signal_fn: SignalFn,
    best_params: dict,
    fees: float = DEFAULT_FEES,
    sl_stop: float = 0.05,
    freq: str = "1h",
    perturbation_pct: float = GATE3_PERTURB_PCT,
) -> list[dict]:
    """
    Test robustness by perturbing each parameter ±20%.

    A robust strategy maintains positive Sharpe across perturbations.
    """
    close = df["close"]
    results = []

    for param_name, original_value in best_params.items():
        for direction, factor in [
            ("+20%", 1 + perturbation_pct),
            ("-20%", 1 - perturbation_pct),
        ]:
            perturbed_value = original_value * factor
            if isinstance(original_value, int):
                perturbed_value = max(1, round(perturbed_value))
            else:
                perturbed_value = round(perturbed_value, 2)

            perturbed_params = {**best_params, param_name: perturbed_value}

            try:
                entries, exits = signal_fn(df, perturbed_params)
                metrics = _run_backtest(close, entries, exits, fees, sl_stop, freq)
            except Exception as e:
                logger.debug(f"Perturbation {param_name} {direction} failed: {e}")
                metrics = {
                    "sharpe_ratio": float("nan"),
                    "total_return": 0,
                    "max_drawdown": 1.0,
                    "num_trades": 0,
                }

            results.append(
                {
                    "param_name": param_name,
                    "original_value": original_value,
                    "perturbed_value": perturbed_value,
                    "direction": direction,
                    "sharpe_ratio": metrics["sharpe_ratio"],
                    "total_return": metrics["total_return"],
                    "max_drawdown": metrics["max_drawdown"],
                    "num_trades": metrics["num_trades"],
                }
            )

    return results


# ── Full Validation Pipeline ─────────────────────────────────


def run_validation(
    strategy_name: str,
    df: pd.DataFrame,
    signal_fn: SignalFn,
    param_grid: dict[str, list],
    fees: float = DEFAULT_FEES,
    sl_stop: float = 0.05,
    freq: str = "1h",
    symbol: str = "unknown",
    timeframe: str = "1h",
) -> dict:
    """Run full Gate 2 + Gate 3 validation and return structured report."""
    logger.info(f"{'=' * 60}")
    logger.info(f"Validation: {strategy_name}")
    logger.info(f"Data: {len(df)} rows, {df.index[0]} to {df.index[-1]}")
    logger.info(f"Fees: {fees:.4f}, Stop Loss: {sl_stop:.2%}")
    logger.info(f"{'=' * 60}")

    report = {
        "strategy_name": strategy_name,
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        "data_rows": len(df),
        "date_range": f"{df.index[0]} to {df.index[-1]}",
        "fees": fees,
        "sl_stop": sl_stop,
    }

    # ── Gate 2: Parameter Sweep ──
    logger.info("\n-- Gate 2: Parameter Sweep --")
    sweep_df = sweep_parameters(df, signal_fn, param_grid, fees, sl_stop, freq)

    gate2_passed = False
    best_params = None

    if sweep_df.empty or sweep_df["passes_gate2"].sum() == 0:
        logger.warning("Gate 2 FAILED: No parameter combination passes all criteria")
        report["gate2"] = {
            "passed": False,
            "total_combos": len(sweep_df),
            "passing_combos": 0,
            "best_params": None,
            "top_results": [],
        }
    else:
        passing = sweep_df[sweep_df["passes_gate2"]]
        best_row = passing.iloc[0]
        best_params = best_row["params"]
        gate2_passed = True

        top_results = []
        for _, row in passing.head(10).iterrows():
            top_results.append(
                {
                    "params": row["params"],
                    "sharpe_ratio": row["sharpe_ratio"],
                    "total_return": row["total_return"],
                    "max_drawdown": row["max_drawdown"],
                    "num_trades": row["num_trades"],
                    "annualized_trades": row["annualized_trades"],
                    "win_rate": row["win_rate"],
                    "profit_factor": row["profit_factor"],
                    "pvalue": row["pvalue"],
                }
            )

        report["gate2"] = {
            "passed": True,
            "total_combos": len(sweep_df),
            "passing_combos": int(len(passing)),
            "best_params": best_params,
            "best_sharpe": float(best_row["sharpe_ratio"]),
            "best_return": float(best_row["total_return"]),
            "best_drawdown": float(best_row["max_drawdown"]),
            "best_trades": int(best_row["num_trades"]),
            "top_results": top_results,
        }
        logger.info(
            f"Gate 2 PASSED: {len(passing)} combos pass, "
            f"best Sharpe={best_row['sharpe_ratio']:.3f}"
        )

    # ── Gate 3 ──
    gate3_wf_passed = False
    gate3_perturb_passed = False

    if gate2_passed and best_params is not None:
        # Gate 3a: Walk-Forward
        logger.info("\n-- Gate 3a: Walk-Forward OOS Validation --")
        wf_results = walk_forward_validate(
            df, signal_fn, best_params, fees, sl_stop, freq
        )

        if wf_results:
            avg_is = np.mean([r["is_sharpe"] for r in wf_results])
            avg_oos = np.mean([r["oos_sharpe"] for r in wf_results])
            ratio = avg_oos / avg_is if avg_is != 0 else 0

            gate3_wf_passed = avg_oos > 0 and ratio >= GATE3_OOS_SHARPE_FLOOR

            report["gate3_walkforward"] = {
                "passed": gate3_wf_passed,
                "avg_is_sharpe": round(avg_is, 4),
                "avg_oos_sharpe": round(avg_oos, 4),
                "oos_vs_is_ratio": round(ratio, 4),
                "threshold": GATE3_OOS_SHARPE_FLOOR,
                "folds": wf_results,
            }
            logger.info(
                f"Walk-forward: IS={avg_is:.3f}, OOS={avg_oos:.3f}, "
                f"ratio={ratio:.2f} {'PASS' if gate3_wf_passed else 'FAIL'}"
            )
        else:
            report["gate3_walkforward"] = {
                "passed": False,
                "error": "No valid folds",
            }

        # Gate 3b: Perturbation
        logger.info("\n-- Gate 3b: Parameter Perturbation (+/-20%) --")
        perturb_results = perturbation_test(
            df, signal_fn, best_params, fees, sl_stop, freq
        )

        sharpes = [r["sharpe_ratio"] for r in perturb_results]
        valid_sharpes = [s for s in sharpes if not np.isnan(s)]
        min_sharpe = min(valid_sharpes) if valid_sharpes else float("nan")

        gate3_perturb_passed = (
            all(s > 0 for s in valid_sharpes) if valid_sharpes else False
        )

        report["gate3_perturbation"] = {
            "passed": gate3_perturb_passed,
            "min_sharpe": round(min_sharpe, 4)
            if not np.isnan(min_sharpe)
            else None,
            "all_positive": gate3_perturb_passed,
            "results": perturb_results,
        }
        logger.info(
            f"Perturbation: min Sharpe={min_sharpe:.3f}, "
            f"all positive={'YES' if gate3_perturb_passed else 'NO'} "
            f"{'PASS' if gate3_perturb_passed else 'FAIL'}"
        )
    else:
        report["gate3_walkforward"] = {"passed": False, "skipped": "Gate 2 failed"}
        report["gate3_perturbation"] = {"passed": False, "skipped": "Gate 2 failed"}

    # ── Overall ──
    overall = gate2_passed and gate3_wf_passed and gate3_perturb_passed
    report["overall"] = {
        "passed": overall,
        "gate2_passed": gate2_passed,
        "gate3_wf_passed": gate3_wf_passed,
        "gate3_perturb_passed": gate3_perturb_passed,
    }

    status = "PASSED" if overall else "FAILED"
    logger.info(f"\n{'=' * 60}")
    logger.info(f"VALIDATION {status}: {strategy_name}")
    logger.info(f"  Gate 2 (Parameter Sweep): {'PASS' if gate2_passed else 'FAIL'}")
    logger.info(
        f"  Gate 3a (Walk-Forward):   {'PASS' if gate3_wf_passed else 'FAIL'}"
    )
    logger.info(
        f"  Gate 3b (Perturbation):   {'PASS' if gate3_perturb_passed else 'FAIL'}"
    )
    logger.info(f"{'=' * 60}")

    return report


def save_report(report: dict, output_dir: Path = None) -> Path:
    """Save validation report to JSON."""
    if output_dir is None:
        output_dir = RESULTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    strategy = report["strategy_name"].lower().replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"{strategy}_validation_{timestamp}.json"

    with open(filepath, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Report saved to {filepath}")
    return filepath
