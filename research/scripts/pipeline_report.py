"""E2E pipeline report aggregator.

Collects results from all pipeline phases and produces a consolidated JSON report.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "research" / "results"
VALIDATION_DIR = RESULTS_DIR / "validation"
DATA_DIR = PROJECT_ROOT / "data" / "processed"
FT_RESULTS_DIR = PROJECT_ROOT / "freqtrade" / "user_data" / "backtest_results"


def collect_data_summary() -> dict:
    """Summarize downloaded OHLCV data files."""
    files = sorted(DATA_DIR.glob("*.parquet"))
    summary = {"total_files": len(files), "files": []}
    for f in files:
        size_kb = f.stat().st_size / 1024
        summary["files"].append({"name": f.name, "size_kb": round(size_kb, 1)})
    return summary


def collect_vbt_screening() -> dict:
    """Collect VBT screening summaries."""
    results = {}
    for summary_file in sorted(RESULTS_DIR.glob("*/summary.json")):
        symbol_dir = summary_file.parent.name
        with open(summary_file) as fh:
            data = json.load(fh)
        results[symbol_dir] = data
    return results


def collect_gate_validation() -> dict:
    """Collect Gate 2/3 validation results."""
    results = {}
    for val_file in sorted(VALIDATION_DIR.glob("*_validation_*.json")):
        with open(val_file) as fh:
            data = json.load(fh)
        strategy = data.get("strategy_name", val_file.stem)
        results[strategy] = {
            "file": val_file.name,
            "symbol": data.get("symbol"),
            "timeframe": data.get("timeframe"),
            "data_rows": data.get("data_rows"),
            "gate2_passed": data.get("gate2", {}).get("passed", False),
            "gate2_passing_combos": data.get("gate2", {}).get("passing_combos", 0),
            "gate2_total_combos": data.get("gate2", {}).get("total_combos", 0),
            "gate2_best_sharpe": data.get("gate2", {}).get("best_sharpe"),
            "gate2_best_return": data.get("gate2", {}).get("best_return"),
            "gate2_best_drawdown": data.get("gate2", {}).get("best_drawdown"),
            "gate3_wf_passed": data.get("gate3_walkforward", {}).get("passed", False),
            "gate3_wf_oos_ratio": data.get("gate3_walkforward", {}).get(
                "oos_vs_is_ratio"
            ),
            "gate3_perturb_passed": data.get("gate3_perturbation", {}).get(
                "passed", False
            ),
            "gate3_perturb_min_sharpe": data.get("gate3_perturbation", {}).get(
                "min_sharpe"
            ),
            "overall_passed": data.get("overall", {}).get("passed", False),
        }
    return results


def collect_freqtrade_backtests() -> dict:
    """Collect Freqtrade backtest results from zip files."""
    import zipfile

    results = {}
    last_result_file = FT_RESULTS_DIR / ".last_result.json"
    if not last_result_file.exists():
        return results

    for zf_path in sorted(FT_RESULTS_DIR.glob("*.zip")):
        try:
            with zipfile.ZipFile(zf_path) as zf:
                names = zf.namelist()
                with zf.open(names[0]) as fh:
                    data = json.load(fh)
                for strategy, details in data.get("strategy", {}).items():
                    results[strategy] = {
                        "file": zf_path.name,
                        "total_trades": details.get("total_trades", 0),
                        "profit_total_pct": round(
                            details.get("profit_total", 0) * 100, 2
                        ),
                        "profit_total_abs": round(
                            details.get("profit_total_abs", 0), 2
                        ),
                        "max_drawdown_abs": round(
                            details.get("max_drawdown_abs", 0), 2
                        ),
                        "max_drawdown_pct": round(
                            details.get("max_drawdown", 0) * 100, 2
                        ),
                        "wins": details.get("wins", 0),
                        "losses": details.get("losses", 0),
                        "win_rate_pct": round(
                            details.get("wins", 0)
                            / max(details.get("total_trades", 1), 1)
                            * 100,
                            1,
                        ),
                        "backtest_start": details.get(
                            "backtest_start", ""
                        ),
                        "backtest_end": details.get("backtest_end", ""),
                        "market_change_pct": round(
                            details.get("market_change", 0) * 100, 2
                        ),
                    }
        except Exception as e:
            results[zf_path.stem] = {"error": str(e)}
    return results


def build_report() -> dict:
    """Build the full pipeline report."""
    report = {
        "pipeline_run": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": "a1si-aitp",
            "run_type": "e2e_pipeline",
        },
        "phase1_data": collect_data_summary(),
        "phase2_vbt_screening": collect_vbt_screening(),
        "phase3_gate_validation": collect_gate_validation(),
        "phase5_freqtrade_backtests": collect_freqtrade_backtests(),
    }

    # Summary
    gate_results = report["phase3_gate_validation"]
    ft_results = report["phase5_freqtrade_backtests"]

    report["summary"] = {
        "data_files": report["phase1_data"]["total_files"],
        "strategies_validated": len(gate_results),
        "strategies_gate2_passed": sum(
            1 for v in gate_results.values() if v.get("gate2_passed")
        ),
        "strategies_gate3_wf_passed": sum(
            1
            for v in gate_results.values()
            if str(v.get("gate3_wf_passed")).lower() == "true"
        ),
        "strategies_gate3_perturb_passed": sum(
            1 for v in gate_results.values() if v.get("gate3_perturb_passed")
        ),
        "strategies_overall_passed": sum(
            1 for v in gate_results.values() if v.get("overall_passed")
        ),
        "freqtrade_strategies_tested": len(ft_results),
        "freqtrade_total_trades": sum(
            v.get("total_trades", 0) for v in ft_results.values()
        ),
        "freqtrade_total_profit": round(
            sum(v.get("profit_total_abs", 0) for v in ft_results.values()), 2
        ),
    }

    return report


def main():
    report = build_report()

    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = RESULTS_DIR / f"e2e_report_{timestamp}.json"
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(output_path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(f"Report saved to: {output_path}")

    # Print summary
    s = report["summary"]
    print("\n" + "=" * 60)
    print("  E2E PIPELINE REPORT SUMMARY")
    print("=" * 60)
    print(f"\n  Data files downloaded:        {s['data_files']}")
    print(f"  Strategies validated:         {s['strategies_validated']}")
    print(f"  Gate 2 passed:                {s['strategies_gate2_passed']}")
    print(f"  Gate 3 WF passed:             {s['strategies_gate3_wf_passed']}")
    print(f"  Gate 3 Perturbation passed:   {s['strategies_gate3_perturb_passed']}")
    print(f"  Overall passed:               {s['strategies_overall_passed']}")

    print(f"\n  Freqtrade strategies tested:  {s['freqtrade_strategies_tested']}")
    print(f"  Freqtrade total trades:       {s['freqtrade_total_trades']}")
    print(f"  Freqtrade total profit:       {s['freqtrade_total_profit']} USDT")

    # Per-strategy gate results
    print("\n  --- Gate Validation Per Strategy ---")
    for name, g in report["phase3_gate_validation"].items():
        g2 = "PASS" if g.get("gate2_passed") else "FAIL"
        g3w = "PASS" if str(g.get("gate3_wf_passed")).lower() == "true" else "FAIL"
        g3p = "PASS" if g.get("gate3_perturb_passed") else "FAIL"
        overall = "PASS" if g.get("overall_passed") else "FAIL"
        sharpe = g.get("gate2_best_sharpe")
        sharpe_str = f"{sharpe:.3f}" if sharpe is not None else "N/A"
        print(f"  {name:30s} Gate2={g2} G3-WF={g3w} G3-Pert={g3p} => {overall}  (Sharpe={sharpe_str})")

    # Per-strategy FT results
    print("\n  --- Freqtrade Backtest Per Strategy ---")
    for name, ft in report["phase5_freqtrade_backtests"].items():
        trades = ft.get("total_trades", 0)
        profit = ft.get("profit_total_abs", 0)
        wr = ft.get("win_rate_pct", 0)
        dd = ft.get("max_drawdown_abs", 0)
        mkt = ft.get("market_change_pct", 0)
        print(f"  {name:30s} trades={trades:3d}  profit={profit:+8.2f} USDT  WR={wr:.1f}%  DD={dd:.2f}  mkt={mkt:.1f}%")

    # VBT screening highlights
    print("\n  --- VBT Screening Highlights ---")
    for symbol_dir, screens in report["phase2_vbt_screening"].items():
        best_screen = None
        best_sharpe = float("-inf")
        for screen_name, screen_data in screens.items():
            s_val = screen_data.get("top_sharpe", 0)
            if s_val != float("inf") and s_val > best_sharpe:
                best_sharpe = s_val
                best_screen = screen_name
        if best_screen:
            ret = screens[best_screen].get("top_return", 0)
            print(f"  {symbol_dir:40s} best={best_screen} Sharpe={best_sharpe:.3f} Return={ret*100:.1f}%")
        else:
            print(f"  {symbol_dir:40s} no valid screens (all inf/0-trade)")

    print("\n" + "=" * 60)
    return report


if __name__ == "__main__":  # pragma: no cover
    main()
