"""Notification service — Telegram + webhook delivery for risk alerts.
Includes formatted message templates and preference-aware delivery.
"""

import logging
import threading
import time
from typing import TYPE_CHECKING

import httpx
from django.conf import settings

if TYPE_CHECKING:
    from core.models import NotificationPreferences

logger = logging.getLogger("notification_service")

# ── Module-level rate limiter ────────────────────────────────
_rate_limit_lock = threading.Lock()
_last_sent: dict[str, float] = {}


def is_rate_limited(key: str, cooldown: float = 300.0) -> bool:
    """Return True if *key* was sent within the last *cooldown* seconds."""
    now = time.monotonic()
    with _rate_limit_lock:
        if key in _last_sent and now - _last_sent[key] < cooldown:
            return True
        _last_sent[key] = now
        return False


def send_telegram_rate_limited(
    message: str,
    rate_key: str,
    cooldown: float = 300.0,
) -> tuple[bool, str]:
    """Send via Telegram unless *rate_key* is on cooldown."""
    if is_rate_limited(rate_key, cooldown):
        logger.debug("Telegram rate-limited for key=%s", rate_key)
        return False, "rate_limited"
    return NotificationService.send_telegram_sync(message)


class TelegramFormatter:
    """Static methods that produce HTML-formatted messages for Telegram."""

    @staticmethod
    def order_submitted(order) -> str:
        return (
            f"<b>Order Submitted</b>\n"
            f"{order.side.upper()} {order.amount} {order.symbol}\n"
            f"Type: {order.order_type} | Exchange: {order.exchange_id}\n"
            f"ID: <code>{order.exchange_order_id or 'pending'}</code>"
        )

    @staticmethod
    def order_filled(order) -> str:
        fee_str = f" | Fee: {order.fee} {order.fee_currency}" if order.fee else ""
        return (
            f"<b>Order Filled</b>\n"
            f"{order.side.upper()} {order.amount} {order.symbol}\n"
            f"Fill price: {order.avg_fill_price}{fee_str}\n"
            f"ID: <code>{order.exchange_order_id}</code>"
        )

    @staticmethod
    def order_cancelled(order) -> str:
        return (
            f"<b>Order Cancelled</b>\n"
            f"{order.side.upper()} {order.amount} {order.symbol}\n"
            f"ID: <code>{order.exchange_order_id or 'N/A'}</code>"
        )

    @staticmethod
    def risk_halt(reason: str, cancelled_count: int) -> str:
        return f"<b>TRADING HALTED</b>\nReason: {reason}\nCancelled orders: {cancelled_count}"

    @staticmethod
    def daily_summary(equity: float, daily_pnl: float, drawdown: float) -> str:
        pnl_str = f"+${daily_pnl:,.2f}" if daily_pnl >= 0 else f"-${abs(daily_pnl):,.2f}"
        return (
            f"<b>Daily Summary</b>\n"
            f"Equity: ${equity:,.2f}\n"
            f"Daily PnL: {pnl_str}\n"
            f"Drawdown: {drawdown * 100:.2f}%"
        )


# Map event types to NotificationPreferences field names
EVENT_PREF_MAP = {
    "order_submitted": "on_order_submitted",
    "order_filled": "on_order_filled",
    "order_cancelled": "on_order_cancelled",
    "halt": "on_risk_halt",
    "resume": "on_risk_halt",
    "trade_rejected": "on_trade_rejected",
    "daily_reset": "on_daily_summary",
    "daily_summary": "on_daily_summary",
}


class NotificationService:
    """Fire-and-forget notification delivery to Telegram and webhooks."""

    @staticmethod
    def _get_preferences(portfolio_id: int) -> "NotificationPreferences":
        from core.models import NotificationPreferences

        prefs, _ = NotificationPreferences.objects.get_or_create(portfolio_id=portfolio_id)
        return prefs

    @staticmethod
    def should_notify(portfolio_id: int, event_type: str, channel: str) -> bool:
        """Check if a notification should be sent based on preferences."""
        prefs = NotificationService._get_preferences(portfolio_id)

        # Check channel toggle
        if channel == "telegram" and not prefs.telegram_enabled:
            return False
        if channel == "webhook" and not prefs.webhook_enabled:
            return False

        # Check event toggle
        pref_field = EVENT_PREF_MAP.get(event_type)
        return not (pref_field and not getattr(prefs, pref_field, True))

    @staticmethod
    async def send_telegram(message: str) -> tuple[bool, str]:
        """Send a message via Telegram Bot API. Returns (delivered, error)."""
        token = settings.TELEGRAM_BOT_TOKEN
        chat_id = settings.TELEGRAM_CHAT_ID

        if not token or not chat_id:
            return False, "Telegram not configured"

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": "HTML",
                    },
                )
                if resp.status_code == 200:
                    return True, ""
                return False, f"Telegram API returned {resp.status_code}"
        except Exception as e:
            logger.error(f"Telegram delivery failed: {e}")
            return False, str(e)

    @staticmethod
    async def send_webhook(message: str, event_type: str) -> tuple[bool, str]:
        """POST to a generic webhook URL. Returns (delivered, error)."""
        webhook_url = settings.NOTIFICATION_WEBHOOK_URL

        if not webhook_url:
            return False, "Webhook not configured"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    webhook_url,
                    json={
                        "event_type": event_type,
                        "message": message,
                    },
                )
                if resp.status_code < 300:
                    return True, ""
                return False, f"Webhook returned {resp.status_code}"
        except Exception as e:
            logger.error(f"Webhook delivery failed: {e}")
            return False, str(e)

    @staticmethod
    def send_telegram_sync(message: str) -> tuple[bool, str]:
        """Synchronous Telegram send for use in non-async contexts."""
        token = settings.TELEGRAM_BOT_TOKEN
        chat_id = settings.TELEGRAM_CHAT_ID

        if not token or not chat_id:
            return False, "Telegram not configured"

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": "HTML",
                    },
                )
                if resp.status_code == 200:
                    return True, ""
                return False, f"Telegram API returned {resp.status_code}"
        except Exception as e:
            logger.error(f"Telegram delivery failed: {e}")
            return False, str(e)
