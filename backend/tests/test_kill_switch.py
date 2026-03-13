"""Tests for kill switch (halt/resume) endpoints and service-level cancellation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from risk.services.risk import RiskManagementService
from trading.models import Order, OrderStatus, TradingMode


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestHaltWithCancellation:
    async def test_halt_cancels_open_live_orders(self):
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

        mock_exchange = AsyncMock()
        mock_exchange.cancel_order = AsyncMock()
        mock_service = MagicMock()
        mock_service._get_exchange = AsyncMock(return_value=mock_exchange)
        mock_service.close = AsyncMock()

        with (
            patch("trading.services.live_trading.ExchangeService", return_value=mock_service),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=MagicMock(group_send=AsyncMock()),
            ),
            patch(
                "risk.services.risk.get_channel_layer",
                return_value=MagicMock(group_send=AsyncMock()),
            ),
        ):
            result = await RiskManagementService.halt_trading_with_cancellation(
                portfolio_id=1, reason="test halt",
            )

        assert result["is_halted"] is True
        assert result["cancelled_orders"] == 2

        btc = await sync_to_async(Order.objects.get)(symbol="BTC/USDT")
        assert btc.status == OrderStatus.CANCELLED

    async def test_halt_broadcasts_ws(self):
        mock_channel_layer = MagicMock(group_send=AsyncMock())

        with (
            patch("risk.services.risk.get_channel_layer", return_value=mock_channel_layer),
            patch(
                "trading.services.live_trading.get_channel_layer",
                return_value=mock_channel_layer,
            ),
        ):
            await RiskManagementService.halt_trading_with_cancellation(
                portfolio_id=1, reason="ws test",
            )

        # Verify broadcast was called with halt_status
        calls = mock_channel_layer.group_send.call_args_list
        halt_calls = [c for c in calls if c[0][1].get("type") == "halt_status"]
        assert len(halt_calls) > 0
        assert halt_calls[0][0][1]["data"]["is_halted"] is True

    async def test_resume_broadcasts_ws(self):
        # First halt
        from risk.models import RiskState

        await sync_to_async(RiskState.objects.create)(
            portfolio_id=1, is_halted=True, halt_reason="test",
        )

        mock_channel_layer = MagicMock(group_send=AsyncMock())
        with patch("risk.services.risk.get_channel_layer", return_value=mock_channel_layer):
            result = await RiskManagementService.resume_trading_with_broadcast(portfolio_id=1)

        assert result["is_halted"] is False
        calls = mock_channel_layer.group_send.call_args_list
        halt_calls = [c for c in calls if c[0][1].get("type") == "halt_status"]
        assert len(halt_calls) > 0
        assert halt_calls[0][0][1]["data"]["is_halted"] is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestOrderRejectionDuringHalt:
    async def test_order_submission_rejected_during_halt(self):
        from risk.models import RiskState

        await sync_to_async(RiskState.objects.create)(
            portfolio_id=1, is_halted=True, halt_reason="emergency",
        )

        from trading.services.live_trading import LiveTradingService

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

        with patch(
            "trading.services.live_trading.get_channel_layer",
            return_value=MagicMock(group_send=AsyncMock()),
        ):
            result = await LiveTradingService.submit_order(order)

        assert result.status == OrderStatus.REJECTED
        assert "halted" in result.reject_reason.lower()


@pytest.mark.django_db
class TestHaltResumeSync:
    """Test the sync halt/resume methods still work (backward compatibility)."""

    def test_halt_trading_sync(self):
        result = RiskManagementService.halt_trading(1, "sync test")
        assert result["is_halted"] is True

    def test_resume_trading_sync(self):
        RiskManagementService.halt_trading(1, "test")
        result = RiskManagementService.resume_trading(1)
        assert result["is_halted"] is False

    def test_halted_trade_rejected(self, authenticated_client):
        # Use sync halt method directly
        RiskManagementService.halt_trading(1, "emergency")
        resp = authenticated_client.post(
            "/api/risk/1/check-trade/",
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "size": 0.01,
                "entry_price": 97000,
                "stop_loss_price": 92150,
            },
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["approved"] is False
        assert "halted" in data["reason"].lower()

    def test_halt_status_visible(self, authenticated_client):
        RiskManagementService.halt_trading(1, "visible check")
        resp = authenticated_client.get("/api/risk/1/status/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_halted"] is True
