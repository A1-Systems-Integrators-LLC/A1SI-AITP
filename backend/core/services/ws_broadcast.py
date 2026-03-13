"""Centralized WebSocket broadcast helpers.

Wraps channel_layer.group_send for sync callers (APScheduler threads, JobRunner threads).
All broadcasts are fire-and-forget — failures never break core operations.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("ws_broadcast")


def _send(event_type: str, data: dict) -> None:
    """Send an event to the system_events group. Safe for sync callers."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            "system_events",
            {"type": event_type, "data": data},
        )
    except Exception:
        logger.debug("WS broadcast failed for %s", event_type, exc_info=True)


def broadcast_news_update(
    asset_class: str,
    articles_fetched: int,
    sentiment_summary: dict | None = None,
) -> None:
    """Broadcast news fetch completion."""
    _send("news_update", {
        "asset_class": asset_class,
        "articles_fetched": articles_fetched,
        "sentiment_summary": sentiment_summary or {},
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })


def broadcast_sentiment_update(
    asset_class: str,
    avg_score: float,
    overall_label: str,
    total_articles: int,
) -> None:
    """Broadcast sentiment summary update."""
    _send("sentiment_update", {
        "asset_class": asset_class,
        "avg_score": avg_score,
        "overall_label": overall_label,
        "total_articles": total_articles,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })


def broadcast_scheduler_event(
    task_id: str,
    task_name: str,
    task_type: str,
    status: str,
    job_id: str = "",
    message: str = "",
) -> None:
    """Broadcast scheduler task lifecycle event."""
    _send("scheduler_event", {
        "task_id": task_id,
        "task_name": task_name,
        "task_type": task_type,
        "status": status,
        "job_id": job_id,
        "message": message,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })


def broadcast_opportunity(
    symbol: str,
    opportunity_type: str,
    score: int,
    details: dict,
) -> None:
    """Broadcast high-score market opportunity."""
    _send("opportunity_alert", {
        "symbol": symbol,
        "opportunity_type": opportunity_type,
        "score": score,
        "details": details,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })


def broadcast_strategy_status(
    strategy: str,
    asset_class: str,
    regime: str,
    alignment: int,
    action: str,
) -> None:
    """Broadcast strategy orchestrator status change (pause/resume/reduce)."""
    _send("strategy_status", {
        "strategy": strategy,
        "asset_class": asset_class,
        "regime": regime,
        "alignment": alignment,
        "action": action,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })


def broadcast_regime_change(
    symbol: str,
    previous_regime: str,
    new_regime: str,
    confidence: float,
) -> None:
    """Broadcast regime transition detection."""
    _send("regime_change", {
        "symbol": symbol,
        "previous_regime": previous_regime,
        "new_regime": new_regime,
        "confidence": confidence,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })
