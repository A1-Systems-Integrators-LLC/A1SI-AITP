"""Framework backtest executors: VectorBT screen, NautilusTrader, HFT."""

import logging
from typing import Any

from core.services.executors._types import ProgressCallback

logger = logging.getLogger("scheduler")


def _run_vbt_screen(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run VectorBT strategy screen on watchlist symbols."""
    from core.platform_bridge import ensure_platform_imports, get_platform_config

    ensure_platform_imports()
    asset_class = params.get("asset_class", "crypto")
    timeframe = params.get("timeframe", "1h")
    config = get_platform_config()
    data_cfg = config.get("data", {})

    watchlist_key = {
        "crypto": "watchlist",
        "equity": "equity_watchlist",
        "forex": "forex_watchlist",
    }.get(asset_class, "watchlist")
    symbols = data_cfg.get(watchlist_key, [])

    if not symbols:
        return {"status": "skipped", "reason": f"No {asset_class} watchlist configured"}

    progress_cb(0.1, f"Screening {len(symbols)} {asset_class} symbols")
    results = []
    for i, symbol in enumerate(symbols):
        try:
            from analysis.services.screening import ScreenerService

            default_exchange = "yfinance" if asset_class in ("equity", "forex") else "kraken"
            screen_params = {
                "symbol": symbol,
                "timeframe": "1d" if asset_class in ("equity", "forex") else timeframe,
                "exchange": params.get("exchange", default_exchange),
                "asset_class": asset_class,
            }
            result = ScreenerService.run_full_screen(
                screen_params,
                lambda p, m, _i=i: progress_cb(0.1 + 0.8 * (_i + p) / len(symbols), m),
            )
            results.append({"symbol": symbol, "status": "completed", "result": result})
        except Exception as e:
            logger.warning("VBT screen failed for %s: %s", symbol, e)
            results.append({"symbol": symbol, "status": "error", "error": str(e)})
        progress_cb(0.1 + 0.8 * (i + 1) / len(symbols), f"Screened {i + 1}/{len(symbols)}")

    succeeded = sum(1 for r in results if r["status"] == "completed")
    errors = sum(1 for r in results if r["status"] == "error")
    if errors > 0:
        logger.error(
            "VBT screen: %d/%d symbols failed", errors, len(results),
        )
    return {
        "status": "completed" if succeeded > 0 else "error",
        "symbols_screened": len(results),
        "succeeded": succeeded,
        "errors": errors,
        "results": results,
    }


def _run_nautilus_backtest(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run NautilusTrader backtests across configured strategies for an asset class."""
    from core.platform_bridge import ensure_platform_imports, get_platform_config

    ensure_platform_imports()
    asset_class = params.get("asset_class", "crypto")
    timeframe = params.get("timeframe", "1h")
    exchange = params.get("exchange", "kraken")
    initial_balance = params.get("initial_balance", 10000.0)

    try:
        from nautilus.nautilus_runner import list_nautilus_strategies, run_nautilus_backtest
    except ImportError as e:
        return {"status": "error", "error": f"NautilusTrader not available: {e}"}

    # Map asset class to strategy subset
    strategy_map = {
        "crypto": ["NautilusTrendFollowing", "NautilusMeanReversion", "NautilusVolatilityBreakout"],
        "equity": ["EquityMomentum", "EquityMeanReversion"],
        "forex": ["ForexTrend", "ForexRange"],
    }
    strategies = params.get("strategies") or strategy_map.get(asset_class, [])
    available = list_nautilus_strategies()
    strategies = [s for s in strategies if s in available]

    if not strategies:
        return {"status": "skipped", "reason": f"No Nautilus strategies for {asset_class}"}

    # Get symbols from watchlist
    config = get_platform_config()
    data_cfg = config.get("data", {})
    watchlist_key = {
        "crypto": "watchlist",
        "equity": "equity_watchlist",
        "forex": "forex_watchlist",
    }.get(asset_class, "watchlist")
    symbols = data_cfg.get(watchlist_key, [])[:3]  # Top 3 symbols per run

    if not symbols:
        return {"status": "skipped", "reason": f"No {asset_class} watchlist configured"}

    progress_cb(
        0.1,
        f"Running {len(strategies)} Nautilus strategies on {len(symbols)} {asset_class} symbols",
    )
    results = []
    total_steps = len(strategies) * len(symbols)
    step = 0

    for strategy in strategies:
        for symbol in symbols:
            step += 1
            try:
                result = run_nautilus_backtest(
                    strategy,
                    symbol,
                    timeframe,
                    exchange,
                    initial_balance,
                    asset_class=asset_class,
                )
                results.append(
                    {
                        "strategy": strategy,
                        "symbol": symbol,
                        "status": "completed",
                        "result": result,
                    }
                )
            except Exception as e:
                logger.warning("Nautilus backtest failed %s/%s: %s", strategy, symbol, e)
                results.append(
                    {
                        "strategy": strategy,
                        "symbol": symbol,
                        "status": "error",
                        "error": str(e),
                    }
                )
            progress_cb(0.1 + 0.8 * step / total_steps, f"{strategy} on {symbol}")

    completed = sum(1 for r in results if r["status"] == "completed")
    progress_cb(0.95, f"Nautilus backtests done: {completed}/{len(results)}")
    return {
        "status": "completed",
        "framework": "nautilus",
        "asset_class": asset_class,
        "strategies_run": len(strategies),
        "symbols_tested": len(symbols),
        "total_backtests": len(results),
        "completed": completed,
        "results": results,
    }


def _run_hft_backtest(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run HFT backtests across configured strategies."""
    from core.platform_bridge import ensure_platform_imports, get_platform_config

    ensure_platform_imports()
    exchange = params.get("exchange", "kraken")
    initial_balance = params.get("initial_balance", 10000.0)
    latency_ns = params.get("latency_ns", 1_000_000)

    try:
        from hftbacktest.hft_runner import list_hft_strategies, run_hft_backtest
    except ImportError as e:
        return {"status": "error", "error": f"hftbacktest not available: {e}"}

    strategies = params.get("strategies") or list_hft_strategies()
    if not strategies:
        return {"status": "skipped", "reason": "No HFT strategies available"}

    # HFT is crypto-only, use top crypto symbols
    config = get_platform_config()
    symbols = config.get("data", {}).get("watchlist", [])[:3]
    timeframe = params.get("timeframe", "1h")

    if not symbols:
        return {"status": "skipped", "reason": "No crypto watchlist configured"}

    progress_cb(0.1, f"Running {len(strategies)} HFT strategies on {len(symbols)} symbols")
    results = []
    total_steps = len(strategies) * len(symbols)
    step = 0

    for strategy in strategies:
        for symbol in symbols:
            step += 1
            try:
                result = run_hft_backtest(
                    strategy,
                    symbol,
                    timeframe,
                    exchange,
                    latency_ns,
                    initial_balance,
                )
                results.append(
                    {
                        "strategy": strategy,
                        "symbol": symbol,
                        "status": "completed",
                        "result": result,
                    }
                )
            except Exception as e:
                logger.warning("HFT backtest failed %s/%s: %s", strategy, symbol, e)
                results.append(
                    {
                        "strategy": strategy,
                        "symbol": symbol,
                        "status": "error",
                        "error": str(e),
                    }
                )
            progress_cb(0.1 + 0.8 * step / total_steps, f"{strategy} on {symbol}")

    completed = sum(1 for r in results if r["status"] == "completed")
    progress_cb(0.95, f"HFT backtests done: {completed}/{len(results)}")
    return {
        "status": "completed",
        "framework": "hftbacktest",
        "strategies_run": len(strategies),
        "symbols_tested": len(symbols),
        "total_backtests": len(results),
        "completed": completed,
        "results": results,
    }
