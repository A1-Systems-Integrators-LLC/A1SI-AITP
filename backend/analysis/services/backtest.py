"""Backtest service — wraps Freqtrade (subprocess) and NautilusTrader."""

import json
import logging
import subprocess
from collections.abc import Callable

from core.platform_bridge import ensure_platform_imports, get_freqtrade_dir

logger = logging.getLogger("backtest_service")


class BacktestService:
    @staticmethod
    def run_backtest(params: dict, progress_cb: Callable) -> dict:
        framework = params.get("framework", "freqtrade")
        if framework == "freqtrade":
            return BacktestService._run_freqtrade(params, progress_cb)
        elif framework == "nautilus":
            return BacktestService._run_nautilus(params, progress_cb)
        else:
            return {"error": f"Unknown framework: {framework}"}

    @staticmethod
    def _run_freqtrade(params: dict, progress_cb: Callable) -> dict:
        strategy = params.get("strategy", "SampleStrategy")
        timeframe = params.get("timeframe", "1h")
        timerange = params.get("timerange", "")

        ft_dir = get_freqtrade_dir()
        config_path = ft_dir / "config.json"

        if not config_path.exists():
            return {"error": f"Freqtrade config not found at {config_path}"}

        progress_cb(0.1, f"Starting Freqtrade backtest: {strategy}")

        cmd = [
            "freqtrade", "backtesting",
            "--config", str(config_path),
            "--strategy", strategy,
            "--timeframe", timeframe,
            "--userdir", str(ft_dir / "user_data"),
        ]
        if timerange:
            cmd.extend(["--timerange", timerange])

        try:
            progress_cb(0.3, "Running backtest...")
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600, cwd=str(ft_dir)
            )
            progress_cb(0.9, "Parsing results...")

            metrics = {
                "stdout_tail": result.stdout[-2000:] if result.stdout else "",
                "return_code": result.returncode,
            }

            if result.returncode != 0:
                return {
                    "framework": "freqtrade", "strategy": strategy,
                    "metrics": metrics,
                    "error": result.stderr[-1000:] if result.stderr else "Unknown error",
                }

            results_dir = ft_dir / "user_data" / "backtest_results"
            if results_dir.exists():
                result_files = sorted(
                    results_dir.glob("*.json"),
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                )
                if result_files:
                    try:
                        with open(result_files[0]) as f:
                            bt_data = json.load(f)
                        if "strategy" in bt_data:
                            for _name, strat_data in bt_data["strategy"].items():
                                metrics.update({
                                    "total_trades": strat_data.get("total_trades", 0),
                                    "profit_total": strat_data.get("profit_total", 0),
                                    "profit_total_abs": strat_data.get("profit_total_abs", 0),
                                    "max_drawdown": strat_data.get("max_drawdown", 0),
                                    "sharpe_ratio": strat_data.get("sharpe", 0),
                                    "win_rate": (
                                        strat_data.get("wins", 0)
                                        / max(strat_data.get("total_trades", 1), 1)
                                    ),
                                })
                                break
                    except Exception as e:
                        logger.warning(f"Failed to parse Freqtrade results: {e}")

            progress_cb(1.0, "Complete")
            return {
                "framework": "freqtrade", "strategy": strategy,
                "symbol": params.get("symbol", ""),
                "timeframe": timeframe, "timerange": timerange,
                "metrics": metrics,
            }
        except subprocess.TimeoutExpired:
            return {"error": "Backtest timed out (10 min limit)"}
        except FileNotFoundError:
            return {"error": "freqtrade command not found. Install with: pip install freqtrade"}

    @staticmethod
    def _run_nautilus(params: dict, progress_cb: Callable) -> dict:
        ensure_platform_imports()
        strategy = params.get("strategy", "")
        symbol = params.get("symbol", "BTC/USDT")
        timeframe = params.get("timeframe", "1h")
        exchange = params.get("exchange", "binance")

        progress_cb(0.1, "Loading NautilusTrader...")
        try:
            from nautilus.nautilus_runner import (
                convert_ohlcv_to_nautilus_csv,
                run_nautilus_backtest_example,
            )
        except ImportError as e:
            return {"error": f"NautilusTrader not available: {e}"}

        progress_cb(0.3, "Converting data...")
        csv_path = convert_ohlcv_to_nautilus_csv(symbol, timeframe, exchange)
        if not csv_path:
            return {"error": f"No data for {symbol} {timeframe} on {exchange}"}

        progress_cb(0.5, "Running backtest engine...")
        engine = run_nautilus_backtest_example()
        if not engine:
            return {"error": "NautilusTrader engine initialization failed"}

        progress_cb(0.9, "Complete")
        return {
            "framework": "nautilus", "strategy": strategy or "example",
            "symbol": symbol, "timeframe": timeframe,
            "metrics": {"engine_status": "initialized", "data_path": str(csv_path)},
        }

    @staticmethod
    def list_strategies() -> list[dict]:
        strategies = []

        ft_dir = get_freqtrade_dir() / "user_data" / "strategies"
        if ft_dir.exists():
            for f in ft_dir.glob("*.py"):
                if f.stem.startswith("_"):
                    continue
                strategies.append({
                    "name": f.stem, "framework": "freqtrade", "file_path": str(f),
                })

        ensure_platform_imports()
        from core.platform_bridge import PROJECT_ROOT

        nautilus_strat_dir = PROJECT_ROOT / "nautilus" / "strategies"
        if nautilus_strat_dir.exists():
            for f in nautilus_strat_dir.glob("*.py"):
                if f.stem.startswith("_"):
                    continue
                strategies.append({
                    "name": f.stem, "framework": "nautilus", "file_path": str(f),
                })

        return strategies
