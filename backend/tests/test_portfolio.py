"""Portfolio API tests."""

import pytest


@pytest.mark.django_db
class TestPortfolio:
    def test_list_empty(self, authenticated_client):
        resp = authenticated_client.get("/api/portfolios/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_portfolio(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/portfolios/",
            {"name": "My Portfolio", "exchange_id": "binance", "description": "Test"},
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Portfolio"
        assert data["exchange_id"] == "binance"
        assert data["holdings"] == []
        assert "id" in data

    def test_get_portfolio(self, authenticated_client):
        create_resp = authenticated_client.post(
            "/api/portfolios/",
            {"name": "Test"},
            format="json",
        )
        pid = create_resp.json()["id"]

        resp = authenticated_client.get(f"/api/portfolios/{pid}/")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test"

    def test_get_portfolio_not_found(self, authenticated_client):
        resp = authenticated_client.get("/api/portfolios/9999/")
        assert resp.status_code == 404

    def test_delete_portfolio(self, authenticated_client):
        create_resp = authenticated_client.post(
            "/api/portfolios/",
            {"name": "To Delete"},
            format="json",
        )
        pid = create_resp.json()["id"]

        resp = authenticated_client.delete(f"/api/portfolios/{pid}/")
        assert resp.status_code == 204

        resp = authenticated_client.get(f"/api/portfolios/{pid}/")
        assert resp.status_code == 404

    def test_add_holding(self, authenticated_client):
        create_resp = authenticated_client.post(
            "/api/portfolios/",
            {"name": "With Holdings"},
            format="json",
        )
        pid = create_resp.json()["id"]

        resp = authenticated_client.post(
            f"/api/portfolios/{pid}/holdings/",
            {"symbol": "BTC", "amount": 0.5, "avg_buy_price": 50000},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["symbol"] == "BTC"
        assert resp.json()["amount"] == 0.5
