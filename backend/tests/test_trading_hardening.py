"""Trading hardening tests — cancel-all, exchange health."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from portfolio.models import Portfolio
from trading.models import Order, OrderStatus, TradingMode


@pytest.mark.django_db
class TestCancelAllOrders:
    def _setup_orders(self):
        portfolio = Portfolio.objects.create(name="Test", exchange_id="binance")
        Order.objects.create(
            exchange_id="binance",
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            amount=1.0,
            price=50000,
            mode=TradingMode.LIVE,
            status=OrderStatus.OPEN,
            portfolio_id=portfolio.id,
            timestamp=datetime.now(timezone.utc),
        )
        Order.objects.create(
            exchange_id="binance",
            symbol="ETH/USDT",
            side="buy",
            order_type="limit",
            amount=10.0,
            price=3000,
            mode=TradingMode.LIVE,
            status=OrderStatus.SUBMITTED,
            portfolio_id=portfolio.id,
            timestamp=datetime.now(timezone.utc),
        )
        return portfolio

    @patch(
        "trading.services.live_trading.LiveTradingService.cancel_all_open_orders",
        new_callable=AsyncMock,
    )
    def test_cancel_all_with_orders(self, mock_cancel, authenticated_client):
        portfolio = self._setup_orders()
        mock_cancel.return_value = 2

        resp = authenticated_client.post(
            "/api/trading/cancel-all/",
            {"portfolio_id": portfolio.id},
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["cancelled_count"] == 2
        assert data["portfolio_id"] == portfolio.id

    @patch(
        "trading.services.live_trading.LiveTradingService.cancel_all_open_orders",
        new_callable=AsyncMock,
    )
    def test_cancel_all_empty(self, mock_cancel, authenticated_client):
        portfolio = Portfolio.objects.create(name="Empty", exchange_id="binance")
        mock_cancel.return_value = 0

        resp = authenticated_client.post(
            "/api/trading/cancel-all/",
            {"portfolio_id": portfolio.id},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["cancelled_count"] == 0

    def test_cancel_all_portfolio_not_found(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/trading/cancel-all/",
            {"portfolio_id": 9999},
            format="json",
        )
        assert resp.status_code == 404

    def test_cancel_all_auth_required(self):
        from django.test import Client

        client = Client()
        resp = client.post("/api/trading/cancel-all/", {"portfolio_id": 1})
        assert resp.status_code == 403

    def test_cancel_all_missing_portfolio_id(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/trading/cancel-all/",
            {},
            format="json",
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestExchangeHealth:
    @patch("market.services.exchange.ExchangeService")
    def test_exchange_health_connected(self, mock_service_cls, authenticated_client):
        mock_instance = MagicMock()
        mock_exchange = AsyncMock()
        mock_exchange.load_markets = AsyncMock()
        mock_instance._get_exchange = AsyncMock(return_value=mock_exchange)
        mock_instance.close = AsyncMock()
        mock_service_cls.return_value = mock_instance

        resp = authenticated_client.get("/api/trading/exchange-health/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["exchange_id"] == "binance"
        assert "latency_ms" in data
        assert "last_checked" in data

    @patch("market.services.exchange.ExchangeService")
    def test_exchange_health_error(self, mock_service_cls, authenticated_client):
        mock_instance = MagicMock()
        mock_instance._get_exchange = AsyncMock(
            side_effect=Exception("Connection failed"),
        )
        mock_instance.close = AsyncMock()
        mock_service_cls.return_value = mock_instance

        resp = authenticated_client.get("/api/trading/exchange-health/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False

    def test_exchange_health_auth_required(self):
        from django.test import Client

        client = Client()
        resp = client.get("/api/trading/exchange-health/")
        assert resp.status_code == 403
