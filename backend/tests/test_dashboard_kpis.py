"""Tests for P5-1: Dashboard KPI Endpoint."""

from datetime import datetime
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone as dj_tz

from core.services.dashboard import DashboardService
from portfolio.models import Holding, Portfolio
from risk.models import RiskState
from trading.models import Order, OrderStatus, TradingMode


@pytest.fixture
def user():
    return User.objects.create_user("kpiuser", password="pass")


@pytest.fixture
def portfolio():
    return Portfolio.objects.create(name="Test", exchange_id="binance")


@pytest.fixture
def holdings(portfolio):
    return [
        Holding.objects.create(
            portfolio=portfolio,
            symbol="BTC/USDT",
            amount=1.0,
            avg_buy_price=40000,
        ),
        Holding.objects.create(
            portfolio=portfolio,
            symbol="ETH/USDT",
            amount=10.0,
            avg_buy_price=2500,
        ),
    ]


@pytest.fixture
def filled_orders(portfolio):
    now = dj_tz.now()
    return [
        Order.objects.create(
            exchange_id="binance",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount=1.0,
            filled=1.0,
            avg_fill_price=40000,
            status=OrderStatus.FILLED,
            mode=TradingMode.LIVE,
            portfolio_id=portfolio.id,
            timestamp=now,
        ),
        Order.objects.create(
            exchange_id="binance",
            symbol="BTC/USDT",
            side="sell",
            order_type="market",
            amount=1.0,
            filled=1.0,
            avg_fill_price=45000,
            status=OrderStatus.FILLED,
            mode=TradingMode.LIVE,
            portfolio_id=portfolio.id,
            timestamp=now,
        ),
    ]


@pytest.fixture
def risk_state(portfolio):
    return RiskState.objects.create(
        portfolio_id=portfolio.id,
        total_equity=12000,
        peak_equity=15000,
        daily_pnl=-100,
        is_halted=True,
        halt_reason="Drawdown exceeded",
    )


# ── Service tests ────────────────────────────────────────────


@pytest.mark.django_db
class TestDashboardServiceEmptyState:
    def test_returns_all_sections(self):
        kpis = DashboardService.get_kpis()
        assert "portfolio" in kpis
        assert "trading" in kpis
        assert "risk" in kpis
        assert "platform" in kpis
        assert "generated_at" in kpis

    def test_empty_portfolio(self):
        kpis = DashboardService.get_kpis()
        assert kpis["portfolio"]["count"] == 0
        assert kpis["portfolio"]["total_value"] == 0.0


@pytest.mark.django_db
class TestDashboardServiceWithData:
    def test_with_portfolio_holdings(self, portfolio, holdings):
        kpis = DashboardService.get_kpis()
        assert kpis["portfolio"]["count"] == 2

    def test_with_filled_orders(self, portfolio, filled_orders):
        kpis = DashboardService.get_kpis()
        assert kpis["trading"]["total_trades"] == 2

    def test_with_risk_state(self, portfolio, risk_state):
        kpis = DashboardService.get_kpis()
        assert kpis["risk"]["equity"] == 12000
        assert kpis["risk"]["is_halted"] is True

    def test_asset_class_filter(self, portfolio, filled_orders):
        kpis = DashboardService.get_kpis(asset_class="crypto")
        assert kpis["trading"]["total_trades"] == 2

    def test_partial_failure_graceful(self, portfolio):
        """Test that TradingPerformanceService failure returns defaults."""
        with patch(
            "trading.services.performance.TradingPerformanceService.get_summary",
            side_effect=Exception("analytics down"),
        ):
            kpis = DashboardService.get_kpis()
            assert kpis["trading"]["total_trades"] == 0
            # Other sections should still work
            assert "portfolio" in kpis

    def test_partial_failure_in_sub_service(self, portfolio):
        """Test that individual section failures return defaults."""
        with patch(
            "portfolio.services.analytics.PortfolioAnalyticsService.get_portfolio_summary",
            side_effect=Exception("analytics down"),
        ):
            kpis = DashboardService.get_kpis()
            # Portfolio should gracefully default
            assert kpis["portfolio"]["count"] == 0
            # Other sections should still work
            assert "trading" in kpis

    def test_platform_counts(self, portfolio):
        kpis = DashboardService.get_kpis()
        assert "data_files" in kpis["platform"]
        assert "active_jobs" in kpis["platform"]
        assert "framework_count" in kpis["platform"]


# ── API tests ────────────────────────────────────────────────


@pytest.mark.django_db
class TestDashboardKPIAPI:
    def test_returns_200(self, client, user):
        client.force_login(user)
        resp = client.get("/api/dashboard/kpis/")
        assert resp.status_code == 200

    def test_asset_class_param(self, client, user):
        client.force_login(user)
        resp = client.get("/api/dashboard/kpis/?asset_class=crypto")
        assert resp.status_code == 200

    def test_response_structure(self, client, user):
        client.force_login(user)
        resp = client.get("/api/dashboard/kpis/")
        data = resp.json()
        assert "portfolio" in data
        assert "trading" in data
        assert "risk" in data
        assert "platform" in data
        assert "generated_at" in data

    def test_auth_required(self, client):
        resp = client.get("/api/dashboard/kpis/")
        assert resp.status_code in (401, 403)

    def test_generated_at_format(self, client, user):
        client.force_login(user)
        resp = client.get("/api/dashboard/kpis/")
        data = resp.json()
        # Should be parseable ISO format
        ts = data["generated_at"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.year >= 2026
