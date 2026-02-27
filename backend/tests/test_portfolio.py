"""Portfolio API tests — CRUD, holdings, edge cases."""

import pytest


@pytest.mark.django_db
class TestPortfolioCRUD:
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

    def test_create_portfolio_minimal(self, authenticated_client):
        """Only name is required."""
        resp = authenticated_client.post(
            "/api/portfolios/",
            {"name": "Minimal"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Minimal"
        assert resp.json()["exchange_id"] == "kraken"  # default

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

    def test_delete_portfolio_not_found(self, authenticated_client):
        resp = authenticated_client.delete("/api/portfolios/9999/")
        assert resp.status_code == 404

    def test_list_multiple_portfolios(self, authenticated_client):
        authenticated_client.post("/api/portfolios/", {"name": "P1"}, format="json")
        authenticated_client.post("/api/portfolios/", {"name": "P2"}, format="json")
        authenticated_client.post("/api/portfolios/", {"name": "P3"}, format="json")
        resp = authenticated_client.get("/api/portfolios/")
        assert resp.status_code == 200
        assert len(resp.json()) == 3


@pytest.mark.django_db
class TestHoldings:
    def _create_portfolio(self, client, name="Test Portfolio"):
        resp = client.post("/api/portfolios/", {"name": name}, format="json")
        return resp.json()["id"]

    def test_add_holding(self, authenticated_client):
        pid = self._create_portfolio(authenticated_client)
        resp = authenticated_client.post(
            f"/api/portfolios/{pid}/holdings/",
            {"symbol": "BTC", "amount": 0.5, "avg_buy_price": 50000},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["symbol"] == "BTC"
        assert resp.json()["amount"] == 0.5

    def test_add_multiple_holdings(self, authenticated_client):
        pid = self._create_portfolio(authenticated_client)
        authenticated_client.post(
            f"/api/portfolios/{pid}/holdings/",
            {"symbol": "BTC", "amount": 1.0, "avg_buy_price": 50000},
            format="json",
        )
        authenticated_client.post(
            f"/api/portfolios/{pid}/holdings/",
            {"symbol": "ETH", "amount": 10.0, "avg_buy_price": 3000},
            format="json",
        )

        resp = authenticated_client.get(f"/api/portfolios/{pid}/")
        holdings = resp.json()["holdings"]
        assert len(holdings) == 2
        symbols = {h["symbol"] for h in holdings}
        assert symbols == {"BTC", "ETH"}

    def test_add_holding_to_nonexistent_portfolio(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/portfolios/9999/holdings/",
            {"symbol": "BTC", "amount": 1.0, "avg_buy_price": 50000},
            format="json",
        )
        assert resp.status_code == 404

    def test_holdings_appear_in_portfolio_detail(self, authenticated_client):
        pid = self._create_portfolio(authenticated_client)
        authenticated_client.post(
            f"/api/portfolios/{pid}/holdings/",
            {"symbol": "SOL", "amount": 100, "avg_buy_price": 25},
            format="json",
        )
        resp = authenticated_client.get(f"/api/portfolios/{pid}/")
        data = resp.json()
        assert len(data["holdings"]) == 1
        assert data["holdings"][0]["symbol"] == "SOL"
        assert data["holdings"][0]["avg_buy_price"] == 25.0

    def test_delete_portfolio_cascades_holdings(self, authenticated_client):
        pid = self._create_portfolio(authenticated_client)
        authenticated_client.post(
            f"/api/portfolios/{pid}/holdings/",
            {"symbol": "BTC", "amount": 1.0, "avg_buy_price": 50000},
            format="json",
        )
        resp = authenticated_client.delete(f"/api/portfolios/{pid}/")
        assert resp.status_code == 204


@pytest.mark.django_db
class TestPortfolioAuth:
    def test_unauthenticated_list_rejected(self):
        from django.test import Client

        client = Client()
        resp = client.get("/api/portfolios/")
        assert resp.status_code == 403
