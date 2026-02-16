"""Trading API tests."""

import pytest


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
        assert data["status"] == "created"

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
