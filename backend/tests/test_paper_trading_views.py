"""P7-6: HTTP-level tests for paper trading view endpoints + GZip middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rest_framework import status


def _mock_paper_service():
    """Create a mock PaperTradingService with all methods."""
    service = MagicMock()
    service.get_status.return_value = {"running": False, "strategy": None}
    service.start.return_value = {"running": True, "strategy": "CryptoInvestorV1"}
    service.stop.return_value = {"running": False, "stopped": True}
    service.get_open_trades = AsyncMock(return_value=[])
    service.get_trade_history = AsyncMock(return_value=[])
    service.get_profit = AsyncMock(return_value={"total_profit": 0.0})
    service.get_performance = AsyncMock(return_value={"win_rate": 0.0, "trades": 0})
    service.get_balance = AsyncMock(return_value={"USDT": 10000.0})
    service.get_log_entries.return_value = []
    return service


@pytest.fixture(autouse=True)
def _patch_paper_service():
    """Patch _get_paper_trading_service globally for all tests in this module."""
    service = _mock_paper_service()
    with patch("trading.views._get_paper_trading_service", return_value=service):
        yield service


@pytest.mark.django_db
class TestPaperTradingStatusView:
    def test_status_returns_json(self, authenticated_client):
        resp = authenticated_client.get("/api/paper-trading/status/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "running" in data

    def test_status_requires_auth(self, api_client):
        resp = api_client.get("/api/paper-trading/status/")
        assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


@pytest.mark.django_db
class TestPaperTradingStartView:
    def test_start_returns_json(self, authenticated_client):
        resp = authenticated_client.post("/api/paper-trading/start/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "running" in data

    def test_start_requires_auth(self, api_client):
        resp = api_client.post("/api/paper-trading/start/")
        assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


@pytest.mark.django_db
class TestPaperTradingStopView:
    def test_stop_returns_json(self, authenticated_client):
        resp = authenticated_client.post("/api/paper-trading/stop/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "running" in data

    def test_stop_requires_auth(self, api_client):
        resp = api_client.post("/api/paper-trading/stop/")
        assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


@pytest.mark.django_db
class TestPaperTradingTradesView:
    def test_trades_returns_json(self, authenticated_client):
        resp = authenticated_client.get("/api/paper-trading/trades/")
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.json(), list)

    def test_trades_requires_auth(self, api_client):
        resp = api_client.get("/api/paper-trading/trades/")
        assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


@pytest.mark.django_db
class TestPaperTradingHistoryView:
    def test_history_returns_json(self, authenticated_client):
        resp = authenticated_client.get("/api/paper-trading/history/")
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.json(), list)

    def test_history_accepts_limit_param(self, authenticated_client):
        resp = authenticated_client.get("/api/paper-trading/history/?limit=10")
        assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestPaperTradingProfitView:
    def test_profit_returns_json(self, authenticated_client):
        resp = authenticated_client.get("/api/paper-trading/profit/")
        assert resp.status_code == status.HTTP_200_OK
        assert "total_profit" in resp.json()


@pytest.mark.django_db
class TestPaperTradingPerformanceView:
    def test_performance_returns_json(self, authenticated_client):
        resp = authenticated_client.get("/api/paper-trading/performance/")
        assert resp.status_code == status.HTTP_200_OK
        assert "win_rate" in resp.json()


@pytest.mark.django_db
class TestPaperTradingBalanceView:
    def test_balance_returns_json(self, authenticated_client):
        resp = authenticated_client.get("/api/paper-trading/balance/")
        assert resp.status_code == status.HTTP_200_OK
        assert "USDT" in resp.json()


@pytest.mark.django_db
class TestPaperTradingLogView:
    def test_log_returns_json(self, authenticated_client):
        resp = authenticated_client.get("/api/paper-trading/log/")
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.json(), list)

    def test_log_accepts_limit_param(self, authenticated_client):
        resp = authenticated_client.get("/api/paper-trading/log/?limit=10")
        assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestGZipMiddleware:
    def test_gzip_middleware_active(self, authenticated_client):
        from django.conf import settings

        assert "django.middleware.gzip.GZipMiddleware" in settings.MIDDLEWARE
        assert settings.MIDDLEWARE.index("django.middleware.gzip.GZipMiddleware") == 0
