"""WebSocket consumer tests."""

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model

from market.consumers import MarketTickerConsumer, SystemEventsConsumer

User = get_user_model()


@database_sync_to_async
def _create_user():
    return User.objects.create_user(username="wsuser", password="testpass123!")


def _make_communicator(consumer_class, path, user=None):
    """Build a WebsocketCommunicator with an optional authenticated user."""
    communicator = WebsocketCommunicator(consumer_class.as_asgi(), path)
    if user:
        communicator.scope["user"] = user
    return communicator


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestMarketTickerConsumer:
    async def test_anonymous_rejected(self):
        from django.contrib.auth.models import AnonymousUser

        comm = _make_communicator(MarketTickerConsumer, "/ws/market/tickers/", user=AnonymousUser())
        connected, code = await comm.connect()
        assert not connected or code == 4001
        await comm.disconnect()

    async def test_authenticated_accepted(self):
        user = await _create_user()
        comm = _make_communicator(MarketTickerConsumer, "/ws/market/tickers/", user=user)
        connected, _ = await comm.connect()
        assert connected
        await comm.disconnect()

    async def test_ticker_update_relayed(self):
        from channels.layers import get_channel_layer

        user = await _create_user()
        comm = _make_communicator(MarketTickerConsumer, "/ws/market/tickers/", user=user)
        connected, _ = await comm.connect()
        assert connected

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "market_tickers",
            {
                "type": "ticker_update",
                "data": {"tickers": [{"symbol": "BTC/USDT", "price": 50000}]},
            },
        )

        response = await comm.receive_json_from(timeout=5)
        assert response["tickers"][0]["symbol"] == "BTC/USDT"
        await comm.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestSystemEventsConsumer:
    async def test_anonymous_rejected(self):
        from django.contrib.auth.models import AnonymousUser

        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=AnonymousUser())
        connected, code = await comm.connect()
        assert not connected or code == 4001
        await comm.disconnect()

    async def test_order_update_relayed(self):
        user = await _create_user()
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "system_events",
            {
                "type": "order_update",
                "data": {"order_id": 1, "status": "filled"},
            },
        )

        response = await comm.receive_json_from(timeout=5)
        assert response["type"] == "order_update"
        assert response["data"]["order_id"] == 1
        await comm.disconnect()

    async def test_halt_status_relayed(self):
        user = await _create_user()
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "system_events",
            {
                "type": "halt_status",
                "data": {"is_halted": True, "halt_reason": "emergency"},
            },
        )

        response = await comm.receive_json_from(timeout=5)
        assert response["type"] == "halt_status"
        assert response["data"]["is_halted"] is True
        await comm.disconnect()

    async def test_news_update_relayed(self):
        user = await _create_user()
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "system_events",
            {
                "type": "news_update",
                "data": {"asset_class": "crypto", "articles_fetched": 5},
            },
        )

        response = await comm.receive_json_from(timeout=5)
        assert response["type"] == "news_update"
        assert response["data"]["articles_fetched"] == 5
        await comm.disconnect()

    async def test_sentiment_update_relayed(self):
        user = await _create_user()
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "system_events",
            {
                "type": "sentiment_update",
                "data": {"asset_class": "crypto", "avg_score": 0.3, "overall_label": "positive"},
            },
        )

        response = await comm.receive_json_from(timeout=5)
        assert response["type"] == "sentiment_update"
        assert response["data"]["avg_score"] == 0.3
        await comm.disconnect()

    async def test_scheduler_event_relayed(self):
        user = await _create_user()
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "system_events",
            {
                "type": "scheduler_event",
                "data": {"task_id": "t1", "task_name": "Test", "status": "submitted"},
            },
        )

        response = await comm.receive_json_from(timeout=5)
        assert response["type"] == "scheduler_event"
        assert response["data"]["status"] == "submitted"
        await comm.disconnect()

    async def test_regime_change_relayed(self):
        user = await _create_user()
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "system_events",
            {
                "type": "regime_change",
                "data": {
                    "symbol": "BTC/USDT",
                    "previous_regime": "ranging",
                    "new_regime": "strong_trend_up",
                    "confidence": 0.85,
                },
            },
        )

        response = await comm.receive_json_from(timeout=5)
        assert response["type"] == "regime_change"
        assert response["data"]["symbol"] == "BTC/USDT"
        assert response["data"]["new_regime"] == "strong_trend_up"
        await comm.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestConnectionLimiter:
    async def test_ws_allows_connection_within_limit(self):
        """Connections within limit should be accepted."""
        from market.consumers import _conn_lock, _connection_counts

        user = await _create_user()
        async with _conn_lock:
            _connection_counts.pop(user.pk, None)  # Clean state

        comm = _make_communicator(MarketTickerConsumer, "/ws/market/tickers/", user=user)
        connected, _ = await comm.connect()
        assert connected
        await comm.disconnect()

        # Cleanup
        async with _conn_lock:
            _connection_counts.pop(user.pk, None)

    async def test_ws_rejects_connection_over_limit(self):
        """6th connection should be rejected with code 4029."""
        from market.consumers import MAX_WS_CONNECTIONS_PER_USER, _conn_lock, _connection_counts

        user = await _create_user()
        # Simulate MAX connections already open
        async with _conn_lock:
            _connection_counts[user.pk] = MAX_WS_CONNECTIONS_PER_USER

        comm = _make_communicator(MarketTickerConsumer, "/ws/market/tickers/", user=user)
        connected, code = await comm.connect()
        assert not connected or code == 4029
        await comm.disconnect()

        # Cleanup
        async with _conn_lock:
            _connection_counts.pop(user.pk, None)

    async def test_ws_decrements_on_disconnect(self):
        """Disconnecting should decrement the connection count."""
        from market.consumers import _conn_lock, _connection_counts

        user = await _create_user()
        async with _conn_lock:
            _connection_counts.pop(user.pk, None)

        comm = _make_communicator(MarketTickerConsumer, "/ws/market/tickers/", user=user)
        connected, _ = await comm.connect()
        assert connected

        # Count should be 1
        async with _conn_lock:
            assert _connection_counts.get(user.pk, 0) == 1

        await comm.disconnect()

        # Count should be 0
        async with _conn_lock:
            assert _connection_counts.get(user.pk, 0) == 0

    async def test_ws_independent_limits_per_user(self):
        """Different users should have independent limits."""
        from market.consumers import _conn_lock, _connection_counts

        user1 = await _create_user()
        user2 = await database_sync_to_async(User.objects.create_user)(
            username="wsuser2", password="testpass123!",
        )
        async with _conn_lock:
            _connection_counts.pop(user1.pk, None)
            _connection_counts.pop(user2.pk, None)

        comm1 = _make_communicator(MarketTickerConsumer, "/ws/market/tickers/", user=user1)
        comm2 = _make_communicator(MarketTickerConsumer, "/ws/market/tickers/", user=user2)

        connected1, _ = await comm1.connect()
        connected2, _ = await comm2.connect()
        assert connected1
        assert connected2

        async with _conn_lock:
            assert _connection_counts.get(user1.pk, 0) == 1
            assert _connection_counts.get(user2.pk, 0) == 1

        await comm1.disconnect()
        await comm2.disconnect()

        async with _conn_lock:
            _connection_counts.pop(user1.pk, None)
            _connection_counts.pop(user2.pk, None)

    async def test_ws_system_events_same_limit(self):
        """SystemEventsConsumer should also enforce the connection limit."""
        from market.consumers import MAX_WS_CONNECTIONS_PER_USER, _conn_lock, _connection_counts

        user = await _create_user()
        async with _conn_lock:
            _connection_counts[user.pk] = MAX_WS_CONNECTIONS_PER_USER

        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, code = await comm.connect()
        assert not connected or code == 4029
        await comm.disconnect()

        async with _conn_lock:
            _connection_counts.pop(user.pk, None)

    async def test_ws_allows_reconnect_after_disconnect(self):
        """After disconnecting, user should be able to reconnect."""
        from market.consumers import MAX_WS_CONNECTIONS_PER_USER, _conn_lock, _connection_counts

        user = await _create_user()
        # Fill to limit
        async with _conn_lock:
            _connection_counts[user.pk] = MAX_WS_CONNECTIONS_PER_USER

        # Simulate a disconnect
        async with _conn_lock:
            _connection_counts[user.pk] = MAX_WS_CONNECTIONS_PER_USER - 1

        comm = _make_communicator(MarketTickerConsumer, "/ws/market/tickers/", user=user)
        connected, _ = await comm.connect()
        assert connected
        await comm.disconnect()

        async with _conn_lock:
            _connection_counts.pop(user.pk, None)
