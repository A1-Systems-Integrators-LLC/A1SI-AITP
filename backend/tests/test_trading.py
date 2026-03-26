"""Trading API tests."""

import pytest

from trading.models import Order, OrderFillEvent, OrderStatus, TradingMode


@pytest.mark.django_db
class TestTrading:
    def test_list_orders_empty(self, authenticated_client):
        resp = authenticated_client.get("/api/trading/orders/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_order(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/trading/orders/",
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "order_type": "market",
                "amount": 0.1,
                "price": 50000,
                "exchange_id": "binance",
            },
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["symbol"] == "BTC/USDT"
        assert data["side"] == "buy"
        assert data["status"] == "pending"

    def test_create_order_with_mode(self, authenticated_client):
        from risk.services.risk import RiskManagementService
        RiskManagementService.update_equity(2, 10000.0)
        resp = authenticated_client.post(
            "/api/trading/orders/",
            {
                "symbol": "ETH/USDT",
                "side": "buy",
                "amount": 1.0,
                "mode": "live",
                "portfolio_id": 2,
            },
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["mode"] == "live"
        assert data["portfolio_id"] == 2

    def test_get_order(self, authenticated_client):
        create_resp = authenticated_client.post(
            "/api/trading/orders/",
            {"symbol": "ETH/USDT", "side": "sell", "amount": 1.0},
            format="json",
        )
        oid = create_resp.json()["id"]

        resp = authenticated_client.get(f"/api/trading/orders/{oid}/")
        assert resp.status_code == 200
        assert resp.json()["symbol"] == "ETH/USDT"

    def test_get_order_not_found(self, authenticated_client):
        resp = authenticated_client.get("/api/trading/orders/9999/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestOrderStateMachine:
    def _make_order(self, **kwargs):
        from django.utils import timezone as tz

        defaults = {
            "exchange_id": "binance",
            "symbol": "BTC/USDT",
            "side": "buy",
            "order_type": "market",
            "amount": 0.1,
            "timestamp": tz.now(),
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def test_pending_to_submitted(self):
        order = self._make_order()
        assert order.status == OrderStatus.PENDING
        order.transition_to(OrderStatus.SUBMITTED, exchange_order_id="EX123")
        order.refresh_from_db()
        assert order.status == OrderStatus.SUBMITTED
        assert order.exchange_order_id == "EX123"
        assert order.submitted_at is not None

    def test_submitted_to_filled(self):
        order = self._make_order()
        order.transition_to(OrderStatus.SUBMITTED)
        order.transition_to(OrderStatus.FILLED, avg_fill_price=50000.0, filled=0.1)
        order.refresh_from_db()
        assert order.status == OrderStatus.FILLED
        assert order.filled_at is not None
        assert order.avg_fill_price == 50000.0

    def test_submitted_to_open_to_partial_to_filled(self):
        order = self._make_order()
        order.transition_to(OrderStatus.SUBMITTED)
        order.transition_to(OrderStatus.OPEN)
        order.transition_to(OrderStatus.PARTIAL_FILL, filled=0.05)
        order.transition_to(OrderStatus.FILLED, filled=0.1)
        order.refresh_from_db()
        assert order.status == OrderStatus.FILLED

    def test_pending_to_rejected(self):
        order = self._make_order()
        order.transition_to(OrderStatus.REJECTED, reject_reason="Risk check failed")
        order.refresh_from_db()
        assert order.status == OrderStatus.REJECTED
        assert order.reject_reason == "Risk check failed"

    def test_open_to_cancelled(self):
        order = self._make_order()
        order.transition_to(OrderStatus.SUBMITTED)
        order.transition_to(OrderStatus.OPEN)
        order.transition_to(OrderStatus.CANCELLED)
        order.refresh_from_db()
        assert order.status == OrderStatus.CANCELLED
        assert order.cancelled_at is not None

    def test_invalid_transition_raises(self):
        order = self._make_order()
        order.transition_to(OrderStatus.SUBMITTED)
        order.transition_to(OrderStatus.FILLED)
        with pytest.raises(ValueError, match="Invalid transition"):
            order.transition_to(OrderStatus.OPEN)

    def test_terminal_states_cannot_transition(self):
        for terminal in [
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.ERROR,
        ]:
            order = self._make_order()
            order.transition_to(
                OrderStatus.REJECTED if terminal == OrderStatus.REJECTED else OrderStatus.SUBMITTED,
            )
            if terminal not in (OrderStatus.REJECTED,):
                order.transition_to(terminal)
            with pytest.raises(ValueError):
                order.transition_to(OrderStatus.PENDING)

    def test_pending_to_error(self):
        order = self._make_order()
        order.transition_to(OrderStatus.ERROR, error_message="Exchange unreachable")
        order.refresh_from_db()
        assert order.status == OrderStatus.ERROR
        assert order.error_message == "Exchange unreachable"


@pytest.mark.django_db
class TestOrderFillEvent:
    def test_create_fill_event(self):
        from django.utils import timezone as tz

        order = Order.objects.create(
            exchange_id="binance",
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            amount=1.0,
            timestamp=tz.now(),
        )
        fill = OrderFillEvent.objects.create(
            order=order,
            fill_price=50000.0,
            fill_amount=0.5,
            fee=0.001,
            fee_currency="BTC",
        )
        assert fill.order_id == order.id
        assert fill.fill_price == 50000.0
        assert order.fill_events.count() == 1

    def test_multiple_fills(self):
        from django.utils import timezone as tz

        order = Order.objects.create(
            exchange_id="binance",
            symbol="ETH/USDT",
            side="buy",
            order_type="limit",
            amount=10.0,
            timestamp=tz.now(),
        )
        OrderFillEvent.objects.create(order=order, fill_price=3000.0, fill_amount=5.0)
        OrderFillEvent.objects.create(order=order, fill_price=3010.0, fill_amount=5.0)
        assert order.fill_events.count() == 2


@pytest.mark.django_db
class TestTradingMode:
    def test_default_mode_is_paper(self):
        from django.utils import timezone as tz

        order = Order.objects.create(
            exchange_id="binance",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount=0.1,
            timestamp=tz.now(),
        )
        assert order.mode == TradingMode.PAPER

    def test_live_mode(self):
        from django.utils import timezone as tz

        order = Order.objects.create(
            exchange_id="binance",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount=0.1,
            mode=TradingMode.LIVE,
            timestamp=tz.now(),
        )
        assert order.mode == TradingMode.LIVE
