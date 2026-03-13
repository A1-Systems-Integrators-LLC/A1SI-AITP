"""Live trading service tests with mocked ccxt exchange."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from trading.models import Order, OrderFillEvent, OrderStatus, TradingMode
from trading.services.live_trading import LiveTradingService


@pytest.fixture
def live_order(db):
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
def mock_exchange():
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(
        return_value={
            "id": "EX-12345",
            "status": "open",
            "filled": 0,
        },
    )
    exchange.fetch_order = AsyncMock(
        return_value={
            "id": "EX-12345",
            "status": "closed",
            "filled": 0.1,
            "average": 50100.0,
            "fee": {"cost": 0.05, "currency": "USDT"},
        },
    )
    exchange.cancel_order = AsyncMock(return_value={"status": "canceled"})
    exchange.load_markets = AsyncMock()
    return exchange


def _mock_channel_layer():
    return MagicMock(group_send=AsyncMock())


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestLiveTradingSubmit:
    async def test_submit_order_success(self, live_order, mock_exchange):
        mock_service = MagicMock()
        mock_service._get_exchange = AsyncMock(return_value=mock_exchange)
        mock_service.close = AsyncMock()

        with (
            patch("trading.services.live_trading.ExchangeService", return_value=mock_service),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=_mock_channel_layer(),
            ),
            patch(
                "risk.services.risk.RiskManagementService.check_trade",
                return_value=(True, "ok"),
            ),
        ):
            order = await LiveTradingService.submit_order(live_order)

        await sync_to_async(order.refresh_from_db)()
        assert order.status == OrderStatus.SUBMITTED
        assert order.exchange_order_id == "EX-12345"
        assert order.submitted_at is not None

    async def test_submit_order_exchange_error(self, live_order, mock_exchange):
        mock_exchange.create_order = AsyncMock(side_effect=Exception("Connection timeout"))
        mock_service = MagicMock()
        mock_service._get_exchange = AsyncMock(return_value=mock_exchange)
        mock_service.close = AsyncMock()

        with (
            patch("trading.services.live_trading.ExchangeService", return_value=mock_service),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=_mock_channel_layer(),
            ),
            patch(
                "risk.services.risk.RiskManagementService.check_trade",
                return_value=(True, "ok"),
            ),
        ):
            order = await LiveTradingService.submit_order(live_order)

        assert order.status == OrderStatus.ERROR
        assert "Connection timeout" in order.error_message

    async def test_submit_rejected_when_halted(self, live_order):
        from risk.models import RiskState

        await sync_to_async(RiskState.objects.create)(
            portfolio_id=1, is_halted=True, halt_reason="test halt",
        )

        with patch(
            "trading.services.live_trading.get_channel_layer",
            return_value=_mock_channel_layer(),
        ):
            order = await LiveTradingService.submit_order(live_order)

        assert order.status == OrderStatus.REJECTED
        assert "halted" in order.reject_reason.lower()

    async def test_submit_rejected_by_risk_check(self, live_order):
        with (
            patch(
                "risk.services.risk.RiskManagementService.check_trade",
                return_value=(False, "Max drawdown exceeded"),
            ),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=_mock_channel_layer(),
            ),
        ):
            order = await LiveTradingService.submit_order(live_order)

        assert order.status == OrderStatus.REJECTED
        assert "drawdown" in order.reject_reason.lower()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestLiveTradingSync:
    async def test_sync_order_filled(self, live_order, mock_exchange):
        # First set the order to submitted state
        await sync_to_async(live_order.transition_to)(
            OrderStatus.SUBMITTED, exchange_order_id="EX-12345",
        )

        mock_service = MagicMock()
        mock_service._get_exchange = AsyncMock(return_value=mock_exchange)
        mock_service.close = AsyncMock()

        with (
            patch("trading.services.live_trading.ExchangeService", return_value=mock_service),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=_mock_channel_layer(),
            ),
        ):
            order = await LiveTradingService.sync_order(live_order)

        await sync_to_async(order.refresh_from_db)()
        assert order.status == OrderStatus.FILLED
        assert order.filled == 0.1
        assert order.avg_fill_price == 50100.0
        assert order.fee == 0.05

        # Should have created a fill event
        count = await sync_to_async(OrderFillEvent.objects.filter(order=order).count)()
        assert count > 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestLiveTradingCancel:
    async def test_cancel_order(self, live_order, mock_exchange):
        await sync_to_async(live_order.transition_to)(
            OrderStatus.SUBMITTED, exchange_order_id="EX-12345",
        )

        mock_service = MagicMock()
        mock_service._get_exchange = AsyncMock(return_value=mock_exchange)
        mock_service.close = AsyncMock()

        with (
            patch("trading.services.live_trading.ExchangeService", return_value=mock_service),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=_mock_channel_layer(),
            ),
        ):
            order = await LiveTradingService.cancel_order(live_order)

        await sync_to_async(order.refresh_from_db)()
        assert order.status == OrderStatus.CANCELLED

    async def test_cancel_all_open_orders(self, mock_exchange):
        now = timezone.now()
        await sync_to_async(Order.objects.create)(
            exchange_id="binance",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount=0.1,
            mode=TradingMode.LIVE,
            status=OrderStatus.SUBMITTED,
            exchange_order_id="EX-1",
            portfolio_id=1,
            timestamp=now,
        )
        await sync_to_async(Order.objects.create)(
            exchange_id="binance",
            symbol="ETH/USDT",
            side="sell",
            order_type="limit",
            amount=1.0,
            mode=TradingMode.LIVE,
            status=OrderStatus.OPEN,
            exchange_order_id="EX-2",
            portfolio_id=1,
            timestamp=now,
        )
        # This paper order should NOT be cancelled
        await sync_to_async(Order.objects.create)(
            exchange_id="binance",
            symbol="SOL/USDT",
            side="buy",
            order_type="market",
            amount=5.0,
            mode=TradingMode.PAPER,
            status=OrderStatus.SUBMITTED,
            portfolio_id=1,
            timestamp=now,
        )

        mock_service = MagicMock()
        mock_service._get_exchange = AsyncMock(return_value=mock_exchange)
        mock_service.close = AsyncMock()

        with (
            patch("trading.services.live_trading.ExchangeService", return_value=mock_service),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=_mock_channel_layer(),
            ),
        ):
            cancelled = await LiveTradingService.cancel_all_open_orders(portfolio_id=1)

        assert cancelled == 2
        # Paper order should still be submitted
        paper = await sync_to_async(Order.objects.get)(symbol="SOL/USDT")
        assert paper.status == OrderStatus.SUBMITTED


@pytest.mark.django_db
class TestOrderCancelView:
    def test_cancel_paper_order(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/trading/orders/",
            {"symbol": "BTC/USDT", "side": "buy", "amount": 0.1},
            format="json",
        )
        oid = resp.json()["id"]

        cancel_resp = authenticated_client.post(f"/api/trading/orders/{oid}/cancel/")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

    def test_cancel_nonexistent_order(self, authenticated_client):
        resp = authenticated_client.post("/api/trading/orders/9999/cancel/")
        assert resp.status_code == 404

    def test_cancel_already_filled(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/trading/orders/",
            {"symbol": "BTC/USDT", "side": "buy", "amount": 0.1},
            format="json",
        )
        oid = resp.json()["id"]

        # Manually set to filled via state machine
        order = Order.objects.get(id=oid)
        order.transition_to(OrderStatus.SUBMITTED)
        order.transition_to(OrderStatus.FILLED)

        cancel_resp = authenticated_client.post(f"/api/trading/orders/{oid}/cancel/")
        assert cancel_resp.status_code == 400
