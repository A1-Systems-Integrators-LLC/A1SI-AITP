"""
Notification service — Telegram + webhook delivery for risk alerts.
"""

import logging

import httpx
from django.conf import settings

logger = logging.getLogger("notification_service")


class NotificationService:
    """Fire-and-forget notification delivery to Telegram and webhooks."""

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
                resp = await client.post(url, json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                })
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
                resp = await client.post(webhook_url, json={
                    "event_type": event_type,
                    "message": message,
                })
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
                resp = client.post(url, json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                })
                if resp.status_code == 200:
                    return True, ""
                return False, f"Telegram API returned {resp.status_code}"
        except Exception as e:
            logger.error(f"Telegram delivery failed: {e}")
            return False, str(e)
