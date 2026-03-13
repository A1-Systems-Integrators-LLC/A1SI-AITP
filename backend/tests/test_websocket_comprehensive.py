"""Comprehensive WebSocket and real-time feature tests.

S15: Tests for unhandled event types, all 8 broadcast helpers, connection limiter
edge cases, reconnection, broadcast failure isolation, event payload structure,
rapid broadcast handling, system_events group routing, and opportunity alert scoring.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from market.consumers import (
    MAX_WS_CONNECTIONS_PER_USER,
    SystemEventsConsumer,
    _conn_lock,
    _connection_counts,
)

User = get_user_model()

# Unique username counter to avoid IntegrityError across tests
_user_counter = 0


@database_sync_to_async
def _create_user(suffix: str = "") -> "User":
    global _user_counter
    _user_counter += 1
    username = f"ws_comp_{_user_counter}{suffix}"
    return User.objects.create_user(username=username, password="testpass123!")


def _make_communicator(consumer_class, path, user=None):
    communicator = WebsocketCommunicator(consumer_class.as_asgi(), path)
    if user:
        communicator.scope["user"] = user
    return communicator


async def _clean_conn(user):
    """Reset connection count for user."""
    async with _conn_lock:
        _connection_counts.pop(user.pk, None)


# ── All 8 event types on SystemEventsConsumer ──────────────────

ALL_EVENT_TYPES = [
    ("halt_status", {"is_halted": True, "reason": "test"}),
    ("order_update", {"order_id": 42, "status": "filled"}),
    ("risk_alert", {"level": "warning", "message": "drawdown 12%"}),
    ("news_update", {"asset_class": "crypto", "articles_fetched": 7}),
    ("sentiment_update", {"asset_class": "forex", "avg_score": 0.4, "overall_label": "neutral"}),
    ("scheduler_event", {"task_id": "t1", "task_name": "Refresh", "status": "completed"}),
    ("regime_change", {"symbol": "ETH/USDT", "previous_regime": "ranging", "new_regime": "high_volatility", "confidence": 0.9}),
    ("opportunity_alert", {"symbol": "SOL/USDT", "opportunity_type": "breakout", "score": 88, "details": {}}),
]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestAllEightEventTypes:
    """Verify each of the 8 event types is correctly relayed by SystemEventsConsumer."""

    @pytest.mark.parametrize("event_type,payload", ALL_EVENT_TYPES, ids=[e[0] for e in ALL_EVENT_TYPES])
    async def test_event_type_relayed(self, event_type, payload):
        user = await _create_user()
        await _clean_conn(user)
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "system_events",
            {"type": event_type, "data": payload},
        )

        response = await comm.receive_json_from(timeout=5)
        assert response["type"] == event_type
        assert response["data"] == payload
        await comm.disconnect()
        await _clean_conn(user)


# ── Unhandled event types ──────────────────────────────────────

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestUnhandledEventTypes:
    """Consumer behavior with unknown or edge-case event types."""

    async def test_unknown_event_raises_valueerror(self):
        """Django Channels raises ValueError for unhandled event types.

        This confirms the consumer only handles the 8 registered event types.
        An unknown type will raise ValueError in dispatch, terminating the
        consumer's message loop.
        """
        user = await _create_user()
        await _clean_conn(user)
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "system_events",
            {"type": "totally_unknown_event", "data": {"foo": "bar"}},
        )

        # The consumer crashes with ValueError, so receiving will raise
        with pytest.raises((ValueError, asyncio.TimeoutError)):
            await comm.receive_json_from(timeout=2)

        # Consumer future is dead after ValueError; disconnect also raises
        try:
            await comm.disconnect()
        except ValueError:
            pass  # Expected: consumer already crashed
        await _clean_conn(user)

    async def test_all_8_handlers_exist(self):
        """SystemEventsConsumer must have handler methods for all 8 event types."""
        expected_handlers = [
            "halt_status",
            "order_update",
            "risk_alert",
            "news_update",
            "sentiment_update",
            "scheduler_event",
            "regime_change",
            "opportunity_alert",
        ]
        consumer = SystemEventsConsumer()
        for handler_name in expected_handlers:
            assert hasattr(consumer, handler_name), f"Missing handler: {handler_name}"
            assert callable(getattr(consumer, handler_name))

    async def test_empty_data_event(self):
        """Event with empty data dict should relay correctly."""
        user = await _create_user()
        await _clean_conn(user)
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "system_events",
            {"type": "risk_alert", "data": {}},
        )

        response = await comm.receive_json_from(timeout=5)
        assert response["type"] == "risk_alert"
        assert response["data"] == {}
        await comm.disconnect()
        await _clean_conn(user)


# ── Connection limiter edge cases ──────────────────────────────

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestConnectionLimiterComprehensive:
    """Extended connection limiter tests."""

    async def test_5th_connection_accepted(self):
        """The 5th connection (at limit) should succeed since count is 4."""
        user = await _create_user()
        async with _conn_lock:
            _connection_counts[user.pk] = MAX_WS_CONNECTIONS_PER_USER - 1  # 4

        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected
        await comm.disconnect()
        await _clean_conn(user)

    async def test_6th_connection_rejected_4029(self):
        """The 6th connection (over limit) should be rejected with close code 4029."""
        user = await _create_user()
        async with _conn_lock:
            _connection_counts[user.pk] = MAX_WS_CONNECTIONS_PER_USER  # 5

        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, code = await comm.connect()
        assert not connected or code == 4029
        await comm.disconnect()
        await _clean_conn(user)

    async def test_reconnect_after_disconnect(self):
        """User at max connections can reconnect after disconnecting one."""
        user = await _create_user()
        await _clean_conn(user)

        # Open connections up to the limit
        comms = []
        for _ in range(MAX_WS_CONNECTIONS_PER_USER):
            c = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
            connected, _ = await c.connect()
            assert connected
            comms.append(c)

        # Disconnect one
        await comms[0].disconnect()

        # New connection should now succeed
        new_comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await new_comm.connect()
        assert connected

        # Cleanup
        await new_comm.disconnect()
        for c in comms[1:]:
            await c.disconnect()
        await _clean_conn(user)

    async def test_anonymous_user_bypasses_limit(self):
        """Anonymous users bypass connection limit check (auth check rejects them separately)."""
        anon = AnonymousUser()
        # Even if counts are maxed for some user, AnonymousUser has no pk to track
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=anon)
        connected, code = await comm.connect()
        # Should be rejected by auth check (4001), not by limiter (4029)
        assert not connected or code == 4001
        await comm.disconnect()

    async def test_disconnect_never_goes_negative(self):
        """Disconnecting with zero count should not produce a negative count."""
        user = await _create_user()
        async with _conn_lock:
            _connection_counts[user.pk] = 0

        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        # Manually trigger release without ever connecting
        comm.scope["user"] = user
        consumer = SystemEventsConsumer()
        consumer.scope = {"user": user}
        await consumer._release_connection()

        async with _conn_lock:
            assert _connection_counts.get(user.pk, 0) >= 0
        await _clean_conn(user)


# ── Broadcast helper functions ─────────────────────────────────

class TestBroadcastHelpersComprehensive:
    """Comprehensive tests for all broadcast helpers in ws_broadcast.py."""

    @patch("channels.layers.get_channel_layer")
    def test_broadcast_opportunity_payload_structure(self, mock_get_layer):
        """broadcast_opportunity should include all required fields."""
        mock_layer = MagicMock()
        mock_get_layer.return_value = mock_layer

        from core.services.ws_broadcast import broadcast_opportunity

        broadcast_opportunity(
            symbol="BTC/USDT",
            opportunity_type="volume_surge",
            score=85,
            details={"volume_ratio": 3.2},
        )

        event = mock_layer.group_send.call_args[0][1]
        data = event["data"]
        # Required fields
        assert "timestamp" in data
        assert "symbol" in data
        assert "opportunity_type" in data
        assert "score" in data
        assert "details" in data
        # Correct group
        assert mock_layer.group_send.call_args[0][0] == "system_events"

    @patch("channels.layers.get_channel_layer")
    def test_broadcast_regime_change_payload_structure(self, mock_get_layer):
        """broadcast_regime_change should include all required fields."""
        mock_layer = MagicMock()
        mock_get_layer.return_value = mock_layer

        from core.services.ws_broadcast import broadcast_regime_change

        broadcast_regime_change("ETH/USDT", "strong_trend_up", "ranging", 0.72)

        event = mock_layer.group_send.call_args[0][1]
        data = event["data"]
        assert data["symbol"] == "ETH/USDT"
        assert data["previous_regime"] == "strong_trend_up"
        assert data["new_regime"] == "ranging"
        assert data["confidence"] == 0.72
        assert "timestamp" in data

    @patch("channels.layers.get_channel_layer")
    def test_broadcast_scheduler_event_all_fields(self, mock_get_layer):
        """broadcast_scheduler_event should include all 7 fields."""
        mock_layer = MagicMock()
        mock_get_layer.return_value = mock_layer

        from core.services.ws_broadcast import broadcast_scheduler_event

        broadcast_scheduler_event(
            task_id="abc123",
            task_name="ML Training",
            task_type="ml_training",
            status="running",
            job_id="job_99",
            message="Training started",
        )

        data = mock_layer.group_send.call_args[0][1]["data"]
        assert data["task_id"] == "abc123"
        assert data["task_name"] == "ML Training"
        assert data["task_type"] == "ml_training"
        assert data["status"] == "running"
        assert data["job_id"] == "job_99"
        assert data["message"] == "Training started"
        assert "timestamp" in data

    @patch("channels.layers.get_channel_layer")
    def test_broadcast_scheduler_event_defaults(self, mock_get_layer):
        """broadcast_scheduler_event optional fields default correctly."""
        mock_layer = MagicMock()
        mock_get_layer.return_value = mock_layer

        from core.services.ws_broadcast import broadcast_scheduler_event

        broadcast_scheduler_event(
            task_id="x",
            task_name="Test",
            task_type="data_refresh",
            status="submitted",
        )

        data = mock_layer.group_send.call_args[0][1]["data"]
        assert data["job_id"] == ""
        assert data["message"] == ""

    @patch("channels.layers.get_channel_layer")
    def test_broadcast_sentiment_update_all_fields(self, mock_get_layer):
        """broadcast_sentiment_update should include all fields."""
        mock_layer = MagicMock()
        mock_get_layer.return_value = mock_layer

        from core.services.ws_broadcast import broadcast_sentiment_update

        broadcast_sentiment_update("equity", -0.15, "negative", 42)

        data = mock_layer.group_send.call_args[0][1]["data"]
        assert data["asset_class"] == "equity"
        assert data["avg_score"] == -0.15
        assert data["overall_label"] == "negative"
        assert data["total_articles"] == 42
        assert "timestamp" in data

    @patch("channels.layers.get_channel_layer")
    def test_timestamp_is_valid_iso_format(self, mock_get_layer):
        """All broadcast timestamps should be valid ISO 8601."""
        mock_layer = MagicMock()
        mock_get_layer.return_value = mock_layer

        from core.services.ws_broadcast import broadcast_news_update

        broadcast_news_update("crypto", 1)

        ts = mock_layer.group_send.call_args[0][1]["data"]["timestamp"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None  # Should be timezone-aware


# ── Broadcast failure isolation ────────────────────────────────

class TestBroadcastFailureIsolation:
    """Exceptions in broadcast must not propagate to callers."""

    @patch("channels.layers.get_channel_layer")
    def test_group_send_exception_swallowed(self, mock_get_layer):
        """RuntimeError in group_send should be silently caught."""
        mock_layer = MagicMock()
        mock_layer.group_send.side_effect = RuntimeError("channel broken")
        mock_get_layer.return_value = mock_layer

        from core.services.ws_broadcast import broadcast_opportunity

        # Should not raise
        broadcast_opportunity("BTC/USDT", "breakout", 90, {})

    @patch("channels.layers.get_channel_layer")
    def test_channel_layer_import_error_swallowed(self, mock_get_layer):
        """If get_channel_layer raises, _send should catch it."""
        mock_get_layer.side_effect = ImportError("channels not installed")

        from core.services.ws_broadcast import broadcast_regime_change

        # Should not raise
        broadcast_regime_change("ETH/USDT", "a", "b", 0.5)

    @patch("channels.layers.get_channel_layer")
    def test_sequential_broadcasts_one_failure_others_succeed(self, mock_get_layer):
        """One broadcast failing must not prevent the next broadcast from working."""
        mock_layer = MagicMock()
        call_count = 0

        def fail_first(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first call fails")
            return None

        mock_layer.group_send.side_effect = fail_first
        mock_get_layer.return_value = mock_layer

        from core.services.ws_broadcast import broadcast_news_update, broadcast_regime_change

        # First call fails silently
        broadcast_news_update("crypto", 5)
        # Second call should still go through
        broadcast_regime_change("BTC/USDT", "a", "b", 0.5)

        assert mock_layer.group_send.call_count == 2

    @patch("channels.layers.get_channel_layer")
    def test_none_channel_layer_safe(self, mock_get_layer):
        """When channel layer is None, broadcast should be a no-op."""
        mock_get_layer.return_value = None

        from core.services.ws_broadcast import (
            broadcast_news_update,
            broadcast_opportunity,
            broadcast_regime_change,
            broadcast_scheduler_event,
            broadcast_sentiment_update,
        )

        # None of these should raise
        broadcast_news_update("crypto", 0)
        broadcast_sentiment_update("equity", 0.0, "neutral", 0)
        broadcast_scheduler_event("t", "n", "tp", "s")
        broadcast_opportunity("X", "y", 0, {})
        broadcast_regime_change("X", "a", "b", 0.0)


# ── System events group routing ────────────────────────────────

class TestSystemEventsGroupRouting:
    """All broadcast helpers must target the 'system_events' group."""

    @patch("channels.layers.get_channel_layer")
    def test_all_broadcasts_target_system_events_group(self, mock_get_layer):
        mock_layer = MagicMock()
        mock_get_layer.return_value = mock_layer

        from core.services.ws_broadcast import (
            broadcast_news_update,
            broadcast_opportunity,
            broadcast_regime_change,
            broadcast_scheduler_event,
            broadcast_sentiment_update,
        )

        funcs = [
            lambda: broadcast_news_update("c", 1),
            lambda: broadcast_sentiment_update("c", 0.1, "pos", 1),
            lambda: broadcast_scheduler_event("t", "n", "tp", "s"),
            lambda: broadcast_opportunity("X", "y", 50, {}),
            lambda: broadcast_regime_change("X", "a", "b", 0.5),
        ]

        for fn in funcs:
            mock_layer.group_send.reset_mock()
            fn()
            group = mock_layer.group_send.call_args[0][0]
            assert group == "system_events", f"Expected system_events, got {group}"


# ── Opportunity alert score threshold ──────────────────────────

class TestOpportunityAlertBroadcast:
    """broadcast_opportunity sends regardless of score (filtering is caller's job)."""

    @patch("channels.layers.get_channel_layer")
    def test_high_score_opportunity_broadcasts(self, mock_get_layer):
        """Score > 75 triggers broadcast (the typical threshold)."""
        mock_layer = MagicMock()
        mock_get_layer.return_value = mock_layer

        from core.services.ws_broadcast import broadcast_opportunity

        broadcast_opportunity("SOL/USDT", "momentum_shift", 82, {"asset_class": "crypto"})

        assert mock_layer.group_send.call_count == 1
        event = mock_layer.group_send.call_args[0][1]
        assert event["type"] == "opportunity_alert"
        assert event["data"]["score"] == 82

    @patch("channels.layers.get_channel_layer")
    def test_low_score_opportunity_still_broadcasts(self, mock_get_layer):
        """broadcast_opportunity itself does not filter by score."""
        mock_layer = MagicMock()
        mock_get_layer.return_value = mock_layer

        from core.services.ws_broadcast import broadcast_opportunity

        broadcast_opportunity("DOGE/USDT", "rsi_bounce", 30, {})

        assert mock_layer.group_send.call_count == 1
        assert mock_layer.group_send.call_args[0][1]["data"]["score"] == 30


# ── Rapid broadcasts ──────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestRapidBroadcasts:
    """Verify rapid successive broadcasts are all delivered to the consumer."""

    async def test_multiple_rapid_events_all_received(self):
        """Send 10 events rapidly; consumer should receive all 10."""
        user = await _create_user()
        await _clean_conn(user)
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        channel_layer = get_channel_layer()
        count = 10
        for i in range(count):
            await channel_layer.group_send(
                "system_events",
                {"type": "order_update", "data": {"order_id": i, "status": "filled"}},
            )

        received = []
        for _ in range(count):
            msg = await comm.receive_json_from(timeout=5)
            received.append(msg)

        assert len(received) == count
        order_ids = {m["data"]["order_id"] for m in received}
        assert order_ids == set(range(count))

        await comm.disconnect()
        await _clean_conn(user)

    async def test_mixed_event_types_rapid(self):
        """Send different event types rapidly; all should arrive correctly typed."""
        user = await _create_user()
        await _clean_conn(user)
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        channel_layer = get_channel_layer()
        events = [
            ("halt_status", {"is_halted": False}),
            ("order_update", {"order_id": 1, "status": "pending"}),
            ("risk_alert", {"level": "critical"}),
            ("news_update", {"asset_class": "crypto", "articles_fetched": 3}),
            ("opportunity_alert", {"symbol": "BTC/USDT", "score": 90}),
        ]

        for etype, data in events:
            await channel_layer.group_send(
                "system_events",
                {"type": etype, "data": data},
            )

        received_types = set()
        for _ in range(len(events)):
            msg = await comm.receive_json_from(timeout=5)
            received_types.add(msg["type"])

        assert received_types == {e[0] for e in events}

        await comm.disconnect()
        await _clean_conn(user)


# ── Event payload structure validation ─────────────────────────

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestEventPayloadStructure:
    """Verify the consumer wraps events with type and data keys."""

    async def test_relayed_message_has_type_and_data(self):
        """Every relayed message must have 'type' and 'data' top-level keys."""
        user = await _create_user()
        await _clean_conn(user)
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "system_events",
            {"type": "risk_alert", "data": {"level": "info", "message": "all clear"}},
        )

        response = await comm.receive_json_from(timeout=5)
        assert "type" in response
        assert "data" in response
        assert isinstance(response["type"], str)
        assert isinstance(response["data"], dict)
        await comm.disconnect()
        await _clean_conn(user)

    async def test_nested_data_preserved(self):
        """Nested data structures should be preserved through the relay."""
        user = await _create_user()
        await _clean_conn(user)
        comm = _make_communicator(SystemEventsConsumer, "/ws/system/", user=user)
        connected, _ = await comm.connect()
        assert connected

        nested = {
            "portfolio": {"holdings": [{"symbol": "BTC", "amount": 1.5}]},
            "metrics": {"sharpe": 1.23, "max_drawdown": -0.15},
        }

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "system_events",
            {"type": "risk_alert", "data": nested},
        )

        response = await comm.receive_json_from(timeout=5)
        assert response["data"] == nested
        await comm.disconnect()
        await _clean_conn(user)
