"""WebSocket consumers for real-time market data and system events."""

import asyncio
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)

# Module-level WS connection tracker
_connection_counts: dict[int, int] = {}  # user_id -> count
_conn_lock = asyncio.Lock()
MAX_WS_CONNECTIONS_PER_USER = 5


class ConnectionLimiterMixin:
    """Mixin to limit WebSocket connections per user."""

    async def _check_connection_limit(self) -> bool:
        """Check if user is within connection limit. Returns True if allowed."""
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            return True  # Auth check happens separately
        user_id = user.pk
        async with _conn_lock:
            count = _connection_counts.get(user_id, 0)
            if count >= MAX_WS_CONNECTIONS_PER_USER:
                logger.warning("WS connection limit reached for user %s (%d)", user_id, count)
                return False
            _connection_counts[user_id] = count + 1
        return True

    async def _release_connection(self):
        """Decrement connection count for the user."""
        user = self.scope.get("user")
        if user and user.is_authenticated:
            async with _conn_lock:
                uid = user.pk
                _connection_counts[uid] = max(0, _connection_counts.get(uid, 0) - 1)


class MarketTickerConsumer(ConnectionLimiterMixin, AsyncJsonWebsocketConsumer):
    """Streams live ticker updates to authenticated clients.

    URL: /ws/market/tickers/
    Group: market_tickers
    """

    async def connect(self):
        if not await self._is_authenticated():
            await self.close(code=4001)
            return

        if not await self._check_connection_limit():
            await self.close(code=4029)
            return

        await self.channel_layer.group_add("market_tickers", self.channel_name)
        await self.accept()

        # Lazily start the ticker poller on first connection
        from market.services.ticker_poller import start_poller

        await start_poller()

    async def disconnect(self, close_code):
        await self._release_connection()
        await self.channel_layer.group_discard("market_tickers", self.channel_name)

    async def ticker_update(self, event):
        """Handle ticker_update messages from the channel layer."""
        await self.send_json(event["data"])

    @database_sync_to_async
    def _is_authenticated(self) -> bool:
        user = self.scope.get("user")
        return user is not None and user.is_authenticated


class SystemEventsConsumer(ConnectionLimiterMixin, AsyncJsonWebsocketConsumer):
    """Streams system events: halt status, order updates, risk alerts.

    URL: /ws/system/
    Group: system_events
    """

    async def connect(self):
        if not await self._is_authenticated():
            await self.close(code=4001)
            return

        if not await self._check_connection_limit():
            await self.close(code=4029)
            return

        await self.channel_layer.group_add("system_events", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self._release_connection()
        await self.channel_layer.group_discard("system_events", self.channel_name)

    async def halt_status(self, event):
        """Handle halt_status messages."""
        await self.send_json(
            {
                "type": "halt_status",
                "data": event["data"],
            },
        )

    async def order_update(self, event):
        """Handle order_update messages."""
        await self.send_json(
            {
                "type": "order_update",
                "data": event["data"],
            },
        )

    async def risk_alert(self, event):
        """Handle risk_alert messages."""
        await self.send_json(
            {
                "type": "risk_alert",
                "data": event["data"],
            },
        )

    async def news_update(self, event):
        """Handle news_update messages."""
        await self.send_json(
            {
                "type": "news_update",
                "data": event["data"],
            },
        )

    async def sentiment_update(self, event):
        """Handle sentiment_update messages."""
        await self.send_json(
            {
                "type": "sentiment_update",
                "data": event["data"],
            },
        )

    async def scheduler_event(self, event):
        """Handle scheduler_event messages."""
        await self.send_json(
            {
                "type": "scheduler_event",
                "data": event["data"],
            },
        )

    async def regime_change(self, event):
        """Handle regime_change messages."""
        await self.send_json(
            {
                "type": "regime_change",
                "data": event["data"],
            },
        )

    async def opportunity_alert(self, event):
        """Handle opportunity_alert messages."""
        await self.send_json(
            {
                "type": "opportunity_alert",
                "data": event["data"],
            },
        )

    @database_sync_to_async
    def _is_authenticated(self) -> bool:
        user = self.scope.get("user")
        return user is not None and user.is_authenticated
