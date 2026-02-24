"""Portfolio analytics service tests — summary, allocation, edge cases."""

from unittest.mock import patch

import pytest

from portfolio.models import Holding, Portfolio
from portfolio.services.analytics import PortfolioAnalyticsService


@pytest.mark.django_db
class TestPortfolioSummary:
    def _create_portfolio_with_holdings(self):
        portfolio = Portfolio.objects.create(name="Test", exchange_id="binance")
        Holding.objects.create(
            portfolio=portfolio, symbol="BTC/USDT", amount=1.0, avg_buy_price=50000,
        )
        Holding.objects.create(
            portfolio=portfolio, symbol="ETH/USDT", amount=10.0, avg_buy_price=3000,
        )
        return portfolio

    def test_empty_portfolio_summary(self):
        portfolio = Portfolio.objects.create(name="Empty", exchange_id="binance")
        summary = PortfolioAnalyticsService.get_portfolio_summary(portfolio.id)
        assert summary["total_value"] == 0.0
        assert summary["total_cost"] == 0.0
        assert summary["unrealized_pnl"] == 0.0
        assert summary["pnl_pct"] == 0.0
        assert summary["holding_count"] == 0

    @patch("portfolio.services.analytics._fetch_prices")
    def test_summary_with_prices(self, mock_fetch):
        portfolio = self._create_portfolio_with_holdings()
        mock_fetch.return_value = {"BTC/USDT": 60000, "ETH/USDT": 4000}

        summary = PortfolioAnalyticsService.get_portfolio_summary(portfolio.id)
        assert summary["holding_count"] == 2
        assert summary["total_cost"] == 80000.0  # 50000 + 30000
        assert summary["total_value"] == 100000.0  # 60000 + 40000
        assert summary["unrealized_pnl"] == 20000.0
        assert summary["pnl_pct"] == 25.0

    @patch("portfolio.services.analytics._fetch_prices")
    def test_summary_fallback_to_cost_basis(self, mock_fetch):
        """When prices unavailable, use cost basis (P&L = 0)."""
        portfolio = self._create_portfolio_with_holdings()
        mock_fetch.return_value = {}

        summary = PortfolioAnalyticsService.get_portfolio_summary(portfolio.id)
        assert summary["unrealized_pnl"] == 0.0
        assert summary["pnl_pct"] == 0.0
        assert summary["total_value"] == summary["total_cost"]

    @patch("portfolio.services.analytics._fetch_prices")
    def test_summary_partial_prices(self, mock_fetch):
        """One symbol priced, one falls back to cost."""
        portfolio = self._create_portfolio_with_holdings()
        mock_fetch.return_value = {"BTC/USDT": 55000}

        summary = PortfolioAnalyticsService.get_portfolio_summary(portfolio.id)
        # BTC: 55000, ETH: 30000 (cost)
        assert summary["total_value"] == 85000.0
        assert summary["total_cost"] == 80000.0
        assert summary["unrealized_pnl"] == 5000.0

    def test_summary_not_found(self):
        with pytest.raises(Portfolio.DoesNotExist):
            PortfolioAnalyticsService.get_portfolio_summary(9999)


@pytest.mark.django_db
class TestPortfolioAllocation:
    @patch("portfolio.services.analytics._fetch_prices")
    def test_allocation_weights_sum_to_100(self, mock_fetch):
        portfolio = Portfolio.objects.create(name="Test", exchange_id="binance")
        Holding.objects.create(
            portfolio=portfolio, symbol="BTC/USDT", amount=1, avg_buy_price=50000,
        )
        Holding.objects.create(
            portfolio=portfolio, symbol="ETH/USDT", amount=10, avg_buy_price=3000,
        )
        mock_fetch.return_value = {"BTC/USDT": 50000, "ETH/USDT": 3000}

        allocation = PortfolioAnalyticsService.get_allocation(portfolio.id)
        total_weight = sum(a["weight"] for a in allocation)
        assert abs(total_weight - 100.0) < 0.1

    @patch("portfolio.services.analytics._fetch_prices")
    def test_allocation_pnl_calculation(self, mock_fetch):
        portfolio = Portfolio.objects.create(name="Test", exchange_id="binance")
        Holding.objects.create(
            portfolio=portfolio, symbol="BTC/USDT", amount=1, avg_buy_price=50000,
        )
        mock_fetch.return_value = {"BTC/USDT": 60000}

        allocation = PortfolioAnalyticsService.get_allocation(portfolio.id)
        assert len(allocation) == 1
        assert allocation[0]["pnl"] == 10000.0
        assert allocation[0]["pnl_pct"] == 20.0
        assert allocation[0]["price_stale"] is False

    @patch("portfolio.services.analytics._fetch_prices")
    def test_allocation_stale_price_flag(self, mock_fetch):
        portfolio = Portfolio.objects.create(name="Test", exchange_id="binance")
        Holding.objects.create(
            portfolio=portfolio, symbol="BTC/USDT", amount=1, avg_buy_price=50000,
        )
        mock_fetch.return_value = {}

        allocation = PortfolioAnalyticsService.get_allocation(portfolio.id)
        assert allocation[0]["price_stale"] is True
        assert allocation[0]["current_price"] == 50000  # fallback to avg_buy_price

    def test_allocation_empty_portfolio(self):
        portfolio = Portfolio.objects.create(name="Empty", exchange_id="binance")
        allocation = PortfolioAnalyticsService.get_allocation(portfolio.id)
        assert allocation == []


@pytest.mark.django_db
class TestPortfolioAnalyticsAPI:
    def _create_portfolio_with_holdings(self, client):
        resp = client.post("/api/portfolios/", {"name": "Test"}, format="json")
        pid = resp.json()["id"]
        client.post(
            f"/api/portfolios/{pid}/holdings/",
            {"symbol": "BTC/USDT", "amount": 1.0, "avg_buy_price": 50000},
            format="json",
        )
        return pid

    def test_summary_endpoint(self, authenticated_client):
        pid = self._create_portfolio_with_holdings(authenticated_client)
        resp = authenticated_client.get(f"/api/portfolios/{pid}/summary/")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_value" in data
        assert "unrealized_pnl" in data
        assert "holding_count" in data
        assert data["holding_count"] == 1

    def test_allocation_endpoint(self, authenticated_client):
        pid = self._create_portfolio_with_holdings(authenticated_client)
        resp = authenticated_client.get(f"/api/portfolios/{pid}/allocation/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["symbol"] == "BTC/USDT"

    def test_summary_not_found(self, authenticated_client):
        resp = authenticated_client.get("/api/portfolios/9999/summary/")
        assert resp.status_code == 404

    def test_allocation_not_found(self, authenticated_client):
        resp = authenticated_client.get("/api/portfolios/9999/allocation/")
        assert resp.status_code == 404

    def test_summary_auth_required(self):
        from django.test import Client

        client = Client()
        resp = client.get("/api/portfolios/1/summary/")
        assert resp.status_code == 403
