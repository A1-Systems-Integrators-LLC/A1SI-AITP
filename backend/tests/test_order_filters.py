"""Order filter tests."""
from datetime import datetime, timezone

import pytest

from trading.models import Order, OrderStatus


def _create_order(symbol="BTC/USDT", status=OrderStatus.FILLED, mode="paper",
                  asset_class="crypto", portfolio_id=1, **kwargs):
    return Order.objects.create(
        exchange_id="binance",
        symbol=symbol,
        side="buy",
        order_type="market",
        amount=1.0,
        price=100.0,
        status=status,
        mode=mode,
        asset_class=asset_class,
        portfolio_id=portfolio_id,
        timestamp=kwargs.get("timestamp", datetime.now(timezone.utc)),
    )


@pytest.mark.django_db
class TestOrderFilters:
    def setup_method(self):
        self.user = None

    def _login(self, client, django_user_model):
        user = django_user_model.objects.create_user(username="filter_user", password="pass")
        client.force_login(user)
        return user

    def test_filter_by_symbol(self, client, django_user_model):
        self._login(client, django_user_model)
        _create_order(symbol="BTC/USDT")
        _create_order(symbol="ETH/USDT")
        resp = client.get("/api/trading/orders/?symbol=BTC")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "BTC/USDT"

    def test_filter_by_symbol_case_insensitive(self, client, django_user_model):
        self._login(client, django_user_model)
        _create_order(symbol="BTC/USDT")
        resp = client.get("/api/trading/orders/?symbol=btc")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_filter_by_status(self, client, django_user_model):
        self._login(client, django_user_model)
        _create_order(status=OrderStatus.FILLED)
        _create_order(status=OrderStatus.PENDING)
        resp = client.get("/api/trading/orders/?status=filled")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "filled"

    def test_filter_by_status_invalid(self, client, django_user_model):
        self._login(client, django_user_model)
        _create_order(status=OrderStatus.FILLED)
        # Invalid status should be ignored (return all)
        resp = client.get("/api/trading/orders/?status=invalid_status")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_filter_by_date_from(self, client, django_user_model):
        self._login(client, django_user_model)
        _create_order(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        _create_order(timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc))
        resp = client.get("/api/trading/orders/?date_from=2026-01-15T00:00:00Z")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_filter_by_date_to(self, client, django_user_model):
        self._login(client, django_user_model)
        _create_order(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        _create_order(timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc))
        resp = client.get("/api/trading/orders/?date_to=2026-01-15T00:00:00Z")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_filter_by_date_range(self, client, django_user_model):
        self._login(client, django_user_model)
        _create_order(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        _create_order(timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc))
        _create_order(timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc))
        resp = client.get(
            "/api/trading/orders/?date_from=2026-01-15T00:00:00Z&date_to=2026-02-15T00:00:00Z",
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_combined_filters(self, client, django_user_model):
        self._login(client, django_user_model)
        _create_order(symbol="BTC/USDT", status=OrderStatus.FILLED)
        _create_order(symbol="BTC/USDT", status=OrderStatus.PENDING)
        _create_order(symbol="ETH/USDT", status=OrderStatus.FILLED)
        resp = client.get("/api/trading/orders/?symbol=BTC&status=filled")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "BTC/USDT"
        assert data[0]["status"] == "filled"
