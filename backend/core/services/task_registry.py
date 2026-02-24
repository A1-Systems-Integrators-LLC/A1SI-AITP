"""Registry mapping task_type strings to executor functions.

Each executor has signature: (params: dict, progress_cb: Callable) -> dict
"""

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("scheduler")

ProgressCallback = Callable[[float, str], None]
TaskExecutor = Callable[[dict, ProgressCallback], dict[str, Any]]


def _run_data_refresh(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Refresh OHLCV data for an asset class watchlist."""
    from core.platform_bridge import ensure_platform_imports, get_platform_config

    ensure_platform_imports()
    from common.data_pipeline.pipeline import DataPipeline

    asset_class = params.get("asset_class", "crypto")
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

    progress_cb(0.1, f"Refreshing {len(symbols)} {asset_class} symbols")
    pipeline = DataPipeline()
    results = pipeline.fetch_ohlcv_multi(
        symbols=symbols[:50],
        timeframes=["1h"],
        asset_class=asset_class,
    )
    progress_cb(0.9, "Saving data")
    saved = 0
    for key, df in results.items():
        if df is not None and not df.empty:
            pipeline.save_ohlcv(df, key[0], key[1], asset_class=asset_class)
            saved += 1

    return {"status": "completed", "symbols": len(symbols), "saved": saved}


def _run_regime_detection(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run regime detection for all crypto watchlist symbols."""
    progress_cb(0.1, "Detecting regimes")
    try:
        from market.services.regime import RegimeService

        service = RegimeService()
        regimes = service.get_all_current_regimes()
        return {"status": "completed", "regimes_detected": len(regimes)}
    except Exception as e:
        logger.warning("Regime detection failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_order_sync(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Sync open live orders with exchange."""
    progress_cb(0.1, "Syncing orders")
    try:
        from trading.models import Order, OrderStatus, TradingMode

        open_orders = Order.objects.filter(
            mode=TradingMode.LIVE,
            status__in=[OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIAL_FILL],
        )
        count = open_orders.count()
        if count == 0:
            return {"status": "completed", "synced": 0, "message": "No open orders"}

        from trading.services.live import LiveTradingService

        service = LiveTradingService()
        synced = 0
        for order in open_orders:
            try:
                service.sync_order(order)
                synced += 1
            except Exception as e:
                logger.warning("Failed to sync order %s: %s", order.id, e)

        return {"status": "completed", "synced": synced, "total": count}
    except Exception as e:
        logger.warning("Order sync failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_data_quality(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Check for stale data across asset classes."""
    from core.platform_bridge import ensure_platform_imports

    ensure_platform_imports()
    progress_cb(0.1, "Checking data quality")
    try:
        from common.data_pipeline.pipeline import DataPipeline

        pipeline = DataPipeline()
        stale = {}
        for ac in ("crypto", "equity", "forex"):
            result = pipeline.detect_stale_data(asset_class=ac)
            if result:
                stale[ac] = result
        return {"status": "completed", "stale_data": stale}
    except Exception as e:
        logger.warning("Data quality check failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_news_fetch(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Fetch latest news for all asset classes."""
    progress_cb(0.1, "Fetching news")
    try:
        from market.services.news import NewsService

        service = NewsService()
        total = 0
        for ac in ("crypto", "equity", "forex"):
            count = service.fetch_and_store(ac)
            total += count
        return {"status": "completed", "articles_fetched": total}
    except Exception as e:
        logger.warning("News fetch failed: %s", e)
        return {"status": "error", "error": str(e)}


TASK_REGISTRY: dict[str, TaskExecutor] = {
    "data_refresh": _run_data_refresh,
    "regime_detection": _run_regime_detection,
    "order_sync": _run_order_sync,
    "data_quality": _run_data_quality,
    "news_fetch": _run_news_fetch,
}
