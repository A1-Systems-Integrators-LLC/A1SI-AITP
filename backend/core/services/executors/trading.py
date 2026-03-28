"""Trading-related task executors: order sync, paper trading."""

import logging
from typing import Any

from core.services.executors._types import ProgressCallback

logger = logging.getLogger("scheduler")


def _run_order_sync(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Sync open live orders with exchange."""
    from datetime import timedelta

    from asgiref.sync import async_to_sync
    from django.conf import settings
    from django.utils import timezone

    from trading.models import Order, OrderStatus, TradingMode
    from trading.services.live_trading import LiveTradingService

    timeout_hours = getattr(settings, "ORDER_SYNC_TIMEOUT_HOURS", 24)
    cutoff = timezone.now() - timedelta(hours=timeout_hours)

    pending = Order.objects.filter(
        mode=TradingMode.LIVE,
        status__in=[OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIAL_FILL],
    )
    total = pending.count()
    progress_cb(0.0, f"Syncing {total} pending orders")

    if total == 0:
        return {"status": "completed", "synced": 0, "timed_out": 0, "errors": 0, "total": 0}

    synced = 0
    timed_out = 0
    errors = 0

    for i, order in enumerate(pending):
        # Timeout stuck SUBMITTED orders
        if order.status == OrderStatus.SUBMITTED and order.created_at < cutoff:
            try:
                order.transition_to(
                    OrderStatus.ERROR,
                    error_message="Order sync timeout: no exchange confirmation",
                )
            except (ValueError, Exception) as e:
                logger.warning("Transition failed for stuck order %s: %s", order.id, e)
                order.status = OrderStatus.ERROR
                order.error_message = "Order sync timeout: no exchange confirmation"
                order.save(update_fields=["status", "error_message"])
            timed_out += 1
            continue

        try:
            async_to_sync(LiveTradingService.sync_order)(order)
            synced += 1
        except Exception as exc:
            logger.error("Order sync failed for %s: %s", order.id, exc)
            errors += 1

        progress_cb((i + 1) / max(total, 1), f"Synced {i + 1}/{total}")

    return {
        "status": "completed",
        "total": total,
        "synced": synced,
        "timed_out": timed_out,
        "errors": errors,
    }


def _run_forex_paper_trading(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run forex paper trading cycle — entries and exits from scanner signals."""
    progress_cb(0.1, "Running forex paper trading cycle")
    try:
        from trading.services.forex_paper_trading import ForexPaperTradingService

        service = ForexPaperTradingService()
        result = service.run_cycle()
        progress_cb(0.9, "Forex paper trading cycle complete")
        return result
    except Exception as e:
        logger.error("Forex paper trading cycle failed: %s", e)
        return {"status": "error", "error": str(e)}
