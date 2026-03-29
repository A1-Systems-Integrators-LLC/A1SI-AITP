"""NautilusTrader HTTP worker — lightweight API for backtest execution.

Runs inside the NautilusTrader Docker container. The Django backend calls
this service to run backtests without needing nautilus_trader installed
in the main backend image.

Endpoints:
    GET  /health              — Liveness/readiness probe
    GET  /strategies          — List registered strategies
    POST /backtest            — Run a single backtest
    POST /backtest/batch      — Run backtests across strategies x symbols
"""

import json
import logging
import traceback
from datetime import datetime, timezone

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("nautilus.worker")

# Detect native NautilusTrader availability at import time
try:
    import nautilus_trader  # noqa: F401

    HAS_NATIVE = True
    NT_VERSION = getattr(nautilus_trader, "__version__", "unknown")
except ImportError:
    HAS_NATIVE = False
    NT_VERSION = "not installed"


async def health(request: Request) -> JSONResponse:
    """Liveness probe."""
    return JSONResponse({
        "status": "ok",
        "service": "nautilus-worker",
        "native_engine": HAS_NATIVE,
        "nautilus_version": NT_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def list_strategies(request: Request) -> JSONResponse:
    """List all registered NautilusTrader strategies."""
    from nautilus.nautilus_runner import list_nautilus_strategies

    strategies = list_nautilus_strategies()
    return JSONResponse({"strategies": strategies, "count": len(strategies)})


async def run_backtest(request: Request) -> JSONResponse:
    """Run a single NautilusTrader backtest.

    Body JSON:
        strategy: str           — Strategy name (e.g. "NautilusTrendFollowing")
        symbol: str             — Symbol (e.g. "BTC/USDT")
        timeframe: str          — Timeframe (e.g. "1h")
        exchange: str           — Exchange (default: "kraken")
        initial_balance: float  — Starting balance (default: 10000.0)
        asset_class: str        — "crypto", "equity", or "forex"
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    strategy = body.get("strategy")
    if not strategy:
        return JSONResponse({"error": "strategy is required"}, status_code=400)

    try:
        from nautilus.nautilus_runner import run_nautilus_backtest

        result = run_nautilus_backtest(
            strategy_name=strategy,
            symbol=body.get("symbol", "BTC/USDT"),
            timeframe=body.get("timeframe", "1h"),
            exchange=body.get("exchange", "kraken"),
            initial_balance=body.get("initial_balance", 10000.0),
            asset_class=body.get("asset_class", "crypto"),
        )
        return JSONResponse({"status": "completed", "result": result})
    except Exception as e:
        logger.error("Backtest failed: %s\n%s", e, traceback.format_exc())
        return JSONResponse(
            {"status": "error", "error": str(e)},
            status_code=500,
        )


async def run_backtest_batch(request: Request) -> JSONResponse:
    """Run backtests across multiple strategies and symbols.

    Body JSON:
        asset_class: str        — "crypto", "equity", or "forex"
        strategies: list[str]   — Strategy names (optional; defaults by asset class)
        symbols: list[str]      — Symbols to test (optional; defaults from config)
        timeframe: str          — Timeframe (default: "1h")
        exchange: str           — Exchange (default: "kraken")
        initial_balance: float  — Starting balance (default: 10000.0)
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    asset_class = body.get("asset_class", "crypto")
    timeframe = body.get("timeframe", "1h")
    exchange = body.get("exchange", "kraken")
    initial_balance = body.get("initial_balance", 10000.0)

    strategy_map = {
        "crypto": ["NautilusTrendFollowing", "NautilusMeanReversion", "NautilusVolatilityBreakout"],
        "equity": ["EquityMomentum", "EquityMeanReversion"],
        "forex": ["ForexTrend", "ForexRange"],
    }

    strategies = body.get("strategies") or strategy_map.get(asset_class, [])
    symbols = body.get("symbols")

    if not symbols:
        # Load from platform config
        try:
            import yaml

            with open("/project/configs/platform_config.yaml") as f:
                config = yaml.safe_load(f)
            watchlist_key = {"crypto": "watchlist", "equity": "equity_watchlist", "forex": "forex_watchlist"}
            symbols = config.get("data", {}).get(watchlist_key.get(asset_class, "watchlist"), [])[:5]
        except Exception:
            symbols = ["BTC/USDT"] if asset_class == "crypto" else ["AAPL/USD"]

    from nautilus.nautilus_runner import list_nautilus_strategies, run_nautilus_backtest

    available = list_nautilus_strategies()
    strategies = [s for s in strategies if s in available]

    results = []
    for strategy in strategies:
        for symbol in symbols:
            try:
                result = run_nautilus_backtest(
                    strategy, symbol, timeframe, exchange, initial_balance,
                    asset_class=asset_class,
                )
                results.append({
                    "strategy": strategy, "symbol": symbol,
                    "status": "completed", "result": result,
                })
            except Exception as e:
                logger.warning("Backtest failed %s/%s: %s", strategy, symbol, e)
                results.append({
                    "strategy": strategy, "symbol": symbol,
                    "status": "error", "error": str(e),
                })

    completed = sum(1 for r in results if r["status"] == "completed")
    return JSONResponse({
        "status": "completed",
        "framework": "nautilus",
        "asset_class": asset_class,
        "native_engine": HAS_NATIVE,
        "strategies_run": len(strategies),
        "symbols_tested": len(symbols),
        "total_backtests": len(results),
        "completed": completed,
        "results": results,
    })


routes = [
    Route("/health", health),
    Route("/strategies", list_strategies),
    Route("/backtest", run_backtest, methods=["POST"]),
    Route("/backtest/batch", run_backtest_batch, methods=["POST"]),
]

app = Starlette(routes=routes)
"""ASGI app — run with: uvicorn nautilus.worker:app --host 0.0.0.0 --port 4090"""
