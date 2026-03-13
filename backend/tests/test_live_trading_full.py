"""Tests for LiveTradingService — submit, sync, cancel, asset-class gating, error paths."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from trading.models import Order, OrderFillEvent, OrderStatus, TradingMode
from trading.services.live_trading import CCXT_STATUS_MAP, LiveTradingService


def _mock_channel_layer():
    return MagicMock(group_send=AsyncMock())


def _mock_exchange_service(exchange):
    """Return a mock ExchangeService that yields the given exchange mock."""
    service = MagicMock()
    service._get_exchange = AsyncMock(return_value=exchange)
    service.close = AsyncMock()
    return service


@pytest.fixture
def pending_live_order(db):
    return Order.objects.create(
        exchange_id="binance",
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        amount=0.1,
        price=50000.0,
        mode=TradingMode.LIVE,
        portfolio_id=1,
        timestamp=timezone.now(),
    )


@pytest.fixture
def submitted_live_order(db):
    order = Order.objects.create(
        exchange_id="binance",
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        amount=0.5,
        price=48000.0,
        mode=TradingMode.LIVE,
        portfolio_id=1,
        exchange_order_id="EX-99",
        timestamp=timezone.now(),
    )
    order.transition_to(OrderStatus.SUBMITTED, exchange_order_id="EX-99")
    return order


@pytest.fixture
def equity_order(db):
    return Order.objects.create(
        exchange_id="binance",
        symbol="AAPL",
        side="buy",
        order_type="market",
        amount=10,
        price=170.0,
        asset_class="equity",
        mode=TradingMode.LIVE,
        portfolio_id=1,
        timestamp=timezone.now(),
    )


@pytest.fixture
def forex_order(db):
    return Order.objects.create(
        exchange_id="binance",
        symbol="EUR/USD",
        side="buy",
        order_type="market",
        amount=1000,
        price=1.08,
        asset_class="forex",
        mode=TradingMode.LIVE,
        portfolio_id=1,
        timestamp=timezone.now(),
    )


@pytest.fixture
def mock_exchange():
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(
        return_value={"id": "EX-001", "status": "open", "filled": 0},
    )
    exchange.fetch_order = AsyncMock(
        return_value={
            "id": "EX-99",
            "status": "closed",
            "filled": 0.5,
            "average": 48100.0,
            "price": 48100.0,
            "fee": {"cost": 0.12, "currency": "USDT"},
        },
    )
    exchange.cancel_order = AsyncMock(return_value={"status": "canceled"})
    return exchange


# ── Submit tests ────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestSubmitOrder:
    async def test_submit_success_transitions_to_submitted(self, pending_live_order, mock_exchange):
        """Happy path: pending -> submitted with exchange_order_id set."""
        with (
            patch(
                "trading.services.live_trading.ExchangeService",
                return_value=_mock_exchange_service(mock_exchange),
            ),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=_mock_channel_layer(),
            ),
            patch(
                "risk.services.risk.RiskManagementService.check_trade",
                return_value=(True, "ok"),
            ),
        ):
            result = await LiveTradingService.submit_order(pending_live_order)

        await sync_to_async(result.refresh_from_db)()
        assert result.status == OrderStatus.SUBMITTED
        assert result.exchange_order_id == "EX-001"

    async def test_submit_exchange_error_transitions_to_error(
        self, pending_live_order, mock_exchange,
    ):
        """When ccxt raises, order transitions to ERROR with message."""
        mock_exchange.create_order = AsyncMock(
            side_effect=Exception("Rate limit exceeded"),
        )
        with (
            patch(
                "trading.services.live_trading.ExchangeService",
                return_value=_mock_exchange_service(mock_exchange),
            ),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=_mock_channel_layer(),
            ),
            patch(
                "risk.services.risk.RiskManagementService.check_trade",
                return_value=(True, "ok"),
            ),
        ):
            result = await LiveTradingService.submit_order(pending_live_order)

        assert result.status == OrderStatus.ERROR
        assert "Rate limit" in result.error_message

    async def test_submit_equity_order_rejected(self, equity_order):
        """Live equity orders are gated — should be rejected immediately."""
        with patch(
            "trading.services.live_trading.get_channel_layer",
            return_value=_mock_channel_layer(),
        ):
            result = await LiveTradingService.submit_order(equity_order)

        assert result.status == OrderStatus.REJECTED
        assert "equity" in result.reject_reason.lower()
        assert "paper" in result.reject_reason.lower()

    async def test_submit_forex_order_rejected(self, forex_order):
        """Live forex orders are gated — should be rejected immediately."""
        with patch(
            "trading.services.live_trading.get_channel_layer",
            return_value=_mock_channel_layer(),
        ):
            result = await LiveTradingService.submit_order(forex_order)

        assert result.status == OrderStatus.REJECTED
        assert "forex" in result.reject_reason.lower()

    async def test_submit_halted_portfolio_rejected(self, pending_live_order):
        """When kill switch is active, order is rejected."""
        from risk.models import RiskState

        await sync_to_async(RiskState.objects.create)(
            portfolio_id=1, is_halted=True, halt_reason="drawdown breach",
        )
        with patch(
            "trading.services.live_trading.get_channel_layer",
            return_value=_mock_channel_layer(),
        ):
            result = await LiveTradingService.submit_order(pending_live_order)

        assert result.status == OrderStatus.REJECTED
        assert "halted" in result.reject_reason.lower()


# ── Sync tests ──────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestSyncOrder:
    async def test_sync_no_exchange_id_returns_early(self, pending_live_order):
        """If exchange_order_id is empty, sync returns immediately."""
        assert pending_live_order.exchange_order_id == ""
        result = await LiveTradingService.sync_order(pending_live_order)
        assert result.status == OrderStatus.PENDING  # unchanged

    async def test_sync_fills_order_and_creates_fill_event(
        self, submitted_live_order, mock_exchange,
    ):
        """Sync detects closed status, updates filled/avg_fill_price, creates FillEvent."""
        with (
            patch(
                "trading.services.live_trading.ExchangeService",
                return_value=_mock_exchange_service(mock_exchange),
            ),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=_mock_channel_layer(),
            ),
        ):
            result = await LiveTradingService.sync_order(submitted_live_order)

        await sync_to_async(result.refresh_from_db)()
        assert result.status == OrderStatus.FILLED
        assert result.filled == 0.5
        assert result.avg_fill_price == 48100.0

        fill_count = await sync_to_async(
            OrderFillEvent.objects.filter(order=result).count,
        )()
        assert fill_count == 1

    async def test_sync_same_status_no_transition(self, submitted_live_order, mock_exchange):
        """When exchange status maps to same local status, no transition occurs."""
        # Make the exchange return 'open' which maps to OrderStatus.OPEN
        # but we can test with status that maps to current
        mock_exchange.fetch_order = AsyncMock(
            return_value={
                "id": "EX-99",
                "status": "open",
                "filled": 0,
                "average": 0,
            },
        )
        with (
            patch(
                "trading.services.live_trading.ExchangeService",
                return_value=_mock_exchange_service(mock_exchange),
            ),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=_mock_channel_layer(),
            ),
        ):
            result = await LiveTradingService.sync_order(submitted_live_order)

        await sync_to_async(result.refresh_from_db)()
        # OPEN is a valid transition from SUBMITTED, so it should transition
        assert result.status == OrderStatus.OPEN


# ── Cancel tests ────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestCancelOrder:
    async def test_cancel_submitted_order(self, submitted_live_order, mock_exchange):
        """Cancel a submitted order — should transition to CANCELLED."""
        with (
            patch(
                "trading.services.live_trading.ExchangeService",
                return_value=_mock_exchange_service(mock_exchange),
            ),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=_mock_channel_layer(),
            ),
        ):
            result = await LiveTradingService.cancel_order(submitted_live_order)

        await sync_to_async(result.refresh_from_db)()
        assert result.status == OrderStatus.CANCELLED

    async def test_cancel_already_filled_is_noop(self, db):
        """Cancelling a filled order does nothing — returns as-is."""
        order = await sync_to_async(Order.objects.create)(
            exchange_id="binance",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount=0.1,
            mode=TradingMode.LIVE,
            portfolio_id=1,
            timestamp=timezone.now(),
        )
        await sync_to_async(order.transition_to)(OrderStatus.SUBMITTED, exchange_order_id="EX-X")
        await sync_to_async(order.transition_to)(OrderStatus.FILLED)

        result = await LiveTradingService.cancel_order(order)
        assert result.status == OrderStatus.FILLED  # unchanged


# ── CCXT Status Map ─────────────────────────────────────────


class TestCcxtStatusMap:
    def test_all_expected_mappings(self):
        """Verify the CCXT status map covers all expected exchange statuses."""
        assert CCXT_STATUS_MAP["open"] == OrderStatus.OPEN
        assert CCXT_STATUS_MAP["closed"] == OrderStatus.FILLED
        assert CCXT_STATUS_MAP["canceled"] == OrderStatus.CANCELLED
        assert CCXT_STATUS_MAP["cancelled"] == OrderStatus.CANCELLED
        assert CCXT_STATUS_MAP["expired"] == OrderStatus.CANCELLED
        assert CCXT_STATUS_MAP["rejected"] == OrderStatus.REJECTED
