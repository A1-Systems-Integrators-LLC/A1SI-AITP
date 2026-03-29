"""VectorBT HTTP worker — lightweight API for strategy screening.

Runs inside the VectorBT Docker container. The Django backend calls
this service to run parameter sweeps and screening without needing
vectorbt installed in the main backend image.

Endpoints:
    GET  /health              — Liveness/readiness probe
    GET  /strategies          — List available screening strategies
    POST /screen              — Run screening on a single symbol
    POST /screen/batch        — Run screening across watchlist symbols
"""

import logging
import traceback
from datetime import datetime, timezone

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("research.worker")

# Detect VectorBT availability at import time
try:
    import vectorbt as vbt  # noqa: F401

    HAS_VBT = True
    VBT_VERSION = getattr(vbt, "__version__", "unknown")
except ImportError:
    HAS_VBT = False
    VBT_VERSION = "not installed"

STRATEGY_TYPES = [
    {"name": "sma_crossover", "label": "SMA Crossover", "combos": 171},
    {"name": "rsi_mean_reversion", "label": "RSI Mean Reversion", "combos": 64},
    {"name": "bollinger_breakout", "label": "Bollinger Breakout", "combos": 20},
    {"name": "ema_rsi_combo", "label": "EMA + RSI Combo", "combos": 9},
    {"name": "volatility_breakout", "label": "Volatility Breakout", "combos": 60},
]


async def health(request: Request) -> JSONResponse:
    """Liveness probe."""
    return JSONResponse({
        "status": "ok",
        "service": "vectorbt-worker",
        "vectorbt_available": HAS_VBT,
        "vectorbt_version": VBT_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def list_strategies(request: Request) -> JSONResponse:
    """List available screening strategies."""
    return JSONResponse({"strategies": STRATEGY_TYPES, "count": len(STRATEGY_TYPES)})


async def run_screen(request: Request) -> JSONResponse:
    """Run VectorBT screening on a single symbol.

    Body JSON:
        symbol: str         — Symbol (e.g. "BTC/USDT")
        timeframe: str      — Timeframe (default: "1h")
        exchange: str       — Exchange (default: "kraken")
        asset_class: str    — "crypto", "equity", or "forex"
        strategies: list    — Optional subset of strategy names
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    symbol = body.get("symbol")
    if not symbol:
        return JSONResponse({"error": "symbol is required"}, status_code=400)

    if not HAS_VBT:
        return JSONResponse(
            {"status": "error", "error": "vectorbt not installed in this container"},
            status_code=503,
        )

    try:
        from research.scripts.vbt_screener import run_full_screen
        from common.data_pipeline.pipeline import load_ohlcv

        timeframe = body.get("timeframe", "1h")
        exchange = body.get("exchange", "kraken")
        asset_class = body.get("asset_class", "crypto")

        if asset_class in ("equity", "forex"):
            exchange = "yfinance"

        df = load_ohlcv(symbol, timeframe, exchange)
        if df is None or df.empty:
            return JSONResponse({
                "status": "error",
                "error": f"No data available for {symbol} {timeframe} on {exchange}",
            }, status_code=404)

        result = run_full_screen(
            df=df,
            symbol=symbol,
            timeframe=timeframe,
            strategies=body.get("strategies"),
        )

        return JSONResponse({
            "status": "completed",
            "symbol": symbol,
            "timeframe": timeframe,
            "exchange": exchange,
            "result": result,
        })
    except Exception as e:
        logger.error("Screen failed for %s: %s\n%s", symbol, e, traceback.format_exc())
        return JSONResponse(
            {"status": "error", "error": str(e)},
            status_code=500,
        )


async def run_screen_batch(request: Request) -> JSONResponse:
    """Run VectorBT screening across multiple symbols.

    Body JSON:
        asset_class: str    — "crypto", "equity", or "forex"
        symbols: list[str]  — Symbols to screen (optional; defaults from config)
        timeframe: str      — Timeframe (default: "1h")
        exchange: str       — Exchange (default: "kraken")
        strategies: list    — Optional subset of strategy names
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    if not HAS_VBT:
        return JSONResponse(
            {"status": "error", "error": "vectorbt not installed in this container"},
            status_code=503,
        )

    asset_class = body.get("asset_class", "crypto")
    timeframe = body.get("timeframe", "1d" if asset_class in ("equity", "forex") else "1h")
    exchange = body.get("exchange", "yfinance" if asset_class in ("equity", "forex") else "kraken")
    symbols = body.get("symbols")

    if not symbols:
        try:
            import yaml

            with open("/project/configs/platform_config.yaml") as f:
                config = yaml.safe_load(f)
            watchlist_key = {"crypto": "watchlist", "equity": "equity_watchlist", "forex": "forex_watchlist"}
            symbols = config.get("data", {}).get(watchlist_key.get(asset_class, "watchlist"), [])
        except Exception:
            symbols = ["BTC/USDT"] if asset_class == "crypto" else ["AAPL/USD"]

    from research.scripts.vbt_screener import run_full_screen
    from common.data_pipeline.pipeline import load_ohlcv

    results = []
    for symbol in symbols:
        try:
            df = load_ohlcv(symbol, timeframe, exchange)
            if df is None or df.empty:
                results.append({"symbol": symbol, "status": "skipped", "reason": "no data"})
                continue

            result = run_full_screen(
                df=df,
                symbol=symbol,
                timeframe=timeframe,
                strategies=body.get("strategies"),
            )
            results.append({"symbol": symbol, "status": "completed", "result": result})
        except Exception as e:
            logger.warning("Screen failed for %s: %s", symbol, e)
            results.append({"symbol": symbol, "status": "error", "error": str(e)})

    completed = sum(1 for r in results if r["status"] == "completed")
    return JSONResponse({
        "status": "completed",
        "framework": "vectorbt",
        "asset_class": asset_class,
        "symbols_screened": len(results),
        "completed": completed,
        "errors": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    })


routes = [
    Route("/health", health),
    Route("/strategies", list_strategies),
    Route("/screen", run_screen, methods=["POST"]),
    Route("/screen/batch", run_screen_batch, methods=["POST"]),
]

app = Starlette(routes=routes)
"""ASGI app — run with: uvicorn research.worker:app --host 0.0.0.0 --port 4092"""
