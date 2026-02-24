"""P7-2: Tests for model constraints and serializer validation."""

import pytest
from django.db import IntegrityError, transaction
from rest_framework import status

from market.models import MarketData
from portfolio.models import Holding, Portfolio


@pytest.mark.django_db
class TestHoldingUniqueConstraint:
    def test_holding_duplicate_portfolio_symbol_rejected(self):
        portfolio = Portfolio.objects.create(name="Test", exchange_id="binance")
        Holding.objects.create(portfolio=portfolio, symbol="BTC/USDT", amount=1.0)
        with pytest.raises(IntegrityError), transaction.atomic():
            Holding.objects.create(portfolio=portfolio, symbol="BTC/USDT", amount=2.0)

    def test_holding_different_portfolios_same_symbol_ok(self):
        p1 = Portfolio.objects.create(name="P1", exchange_id="binance")
        p2 = Portfolio.objects.create(name="P2", exchange_id="binance")
        Holding.objects.create(portfolio=p1, symbol="BTC/USDT", amount=1.0)
        h2 = Holding.objects.create(portfolio=p2, symbol="BTC/USDT", amount=2.0)
        assert h2.pk is not None

    def test_holding_unique_constraint_returns_409_via_api(self, authenticated_client):
        portfolio = Portfolio.objects.create(name="Test", exchange_id="binance")
        Holding.objects.create(portfolio=portfolio, symbol="BTC/USDT", amount=1.0)
        resp = authenticated_client.post(
            f"/api/portfolios/{portfolio.id}/holdings/",
            {"symbol": "BTC/USDT", "amount": 2.0},
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT
        assert "already exists" in resp.json()["error"]


@pytest.mark.django_db
class TestMarketDataUniqueConstraint:
    def test_marketdata_duplicate_rejected(self):
        from datetime import datetime, timezone

        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        MarketData.objects.create(
            symbol="BTC/USDT", exchange_id="binance", timestamp=ts, price=50000.0,
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            MarketData.objects.create(
                symbol="BTC/USDT", exchange_id="binance", timestamp=ts, price=50001.0,
            )

    def test_marketdata_different_timestamps_ok(self):
        from datetime import datetime, timezone

        ts1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        ts2 = datetime(2025, 1, 2, tzinfo=timezone.utc)
        MarketData.objects.create(
            symbol="BTC/USDT", exchange_id="binance", timestamp=ts1, price=50000.0,
        )
        m2 = MarketData.objects.create(
            symbol="BTC/USDT", exchange_id="binance", timestamp=ts2, price=51000.0,
        )
        assert m2.pk is not None


@pytest.mark.django_db
class TestOrderCreateValidation:
    def test_order_create_invalid_exchange_id_rejected(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/trading/orders/",
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "amount": 1.0,
                "exchange_id": "invalid_exchange",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_order_create_valid_exchange_id_accepted(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/trading/orders/",
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "amount": 1.0,
                "exchange_id": "binance",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED

    def test_order_create_short_symbol_rejected(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/trading/orders/",
            {
                "symbol": "B/U",
                "side": "buy",
                "amount": 1.0,
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPortfolioCreateValidation:
    def test_portfolio_create_invalid_exchange_id_rejected(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/portfolios/",
            {"name": "Test", "exchange_id": "fake_exchange"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_portfolio_create_valid_exchange_id_accepted(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/portfolios/",
            {"name": "Test", "exchange_id": "coinbase"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
