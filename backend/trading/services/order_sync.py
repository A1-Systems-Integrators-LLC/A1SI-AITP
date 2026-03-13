"""Background order sync — polls exchange for status updates on live orders."""

import asyncio
import contextlib
import logging

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

_sync_task: asyncio.Task | None = None
_sync_lock = asyncio.Lock()

SYNC_INTERVAL_SECONDS = 15


async def _sync_loop() -> None:
    """Periodically sync all active live orders with their exchanges."""
    while True:
        try:
            from trading.models import Order, OrderStatus, TradingMode
            from trading.services.live_trading import LiveTradingService

            active_statuses = [
                OrderStatus.SUBMITTED,
                OrderStatus.OPEN,
                OrderStatus.PARTIAL_FILL,
            ]
            orders = await sync_to_async(list)(
                Order.objects.filter(
                    mode=TradingMode.LIVE,
                    status__in=active_statuses,
                ),
            )

            for order in orders:
                try:
                    await LiveTradingService.sync_order(order)
                except Exception as e:
                    logger.warning(f"Sync failed for order {order.id}: {e}")

        except Exception as e:
            logger.error(f"Order sync loop error: {e}")

        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


async def start_order_sync() -> None:
    """Start the order sync loop if not already running. Idempotent."""
    global _sync_task

    async with _sync_lock:
        if _sync_task is not None and not _sync_task.done():
            return
        _sync_task = asyncio.create_task(_sync_loop())
        logger.info("Order sync started")


async def stop_order_sync() -> None:
    """Stop the order sync loop if running. Idempotent."""
    global _sync_task

    async with _sync_lock:
        if _sync_task is not None and not _sync_task.done():
            _sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await _sync_task
            _sync_task = None
            logger.info("Order sync stopped")
