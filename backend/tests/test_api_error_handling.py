"""P7-1: Tests for granular API error handling, cancel-all audit log, zero-price guard."""

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status

from risk.models import AlertLog
from trading.services.performance import TradingPerformanceService


def _async_raiser(exc):
    """Return an async function that raises the given exception."""
    async def _fn(*args, **kwargs):
        raise exc
    return _fn


@pytest.mark.django_db
class TestTickerErrorHandling:
    def test_ticker_timeout_returns_408(self, authenticated_client):
        from ccxt.base.errors import RequestTimeout

        mock_router_cls = MagicMock()
        mock_router_cls.return_value.fetch_ticker = _async_raiser(RequestTimeout("timed out"))
        with patch("market.services.data_router.DataServiceRouter", mock_router_cls):
            resp = authenticated_client.get("/api/market/ticker/BTC/USDT/")
        assert resp.status_code == status.HTTP_408_REQUEST_TIMEOUT
        assert "timed out" in resp.json()["error"].lower()

    def test_ticker_list_network_error_returns_503(self, authenticated_client):
        from ccxt.base.errors import NetworkError

        mock_router_cls = MagicMock()
        mock_router_cls.return_value.fetch_tickers = _async_raiser(NetworkError("refused"))
        with patch("market.services.data_router.DataServiceRouter", mock_router_cls):
            url = "/api/market/tickers/?symbols=BTC/USDT&asset_class=equity"
            resp = authenticated_client.get(url)
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "unavailable" in resp.json()["error"].lower()


@pytest.mark.django_db
class TestOHLCVErrorHandling:
    def test_ohlcv_timeout_returns_408(self, authenticated_client):
        from ccxt.base.errors import RequestTimeout

        mock_router_cls = MagicMock()
        mock_router_cls.return_value.fetch_ohlcv = _async_raiser(RequestTimeout("timeout"))
        with patch("market.services.data_router.DataServiceRouter", mock_router_cls):
            resp = authenticated_client.get("/api/market/ohlcv/BTC/USDT/")
        assert resp.status_code == status.HTTP_408_REQUEST_TIMEOUT
        assert "timed out" in resp.json()["error"].lower()

    def test_ohlcv_generic_error_returns_500(self, authenticated_client):
        mock_router_cls = MagicMock()
        mock_router_cls.return_value.fetch_ohlcv = _async_raiser(ValueError("unexpected"))
        with patch("market.services.data_router.DataServiceRouter", mock_router_cls):
            resp = authenticated_client.get("/api/market/ohlcv/BTC/USDT/")
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "error" in resp.json()


@pytest.mark.django_db
class TestCancelAllAuditLog:
    def test_cancel_all_creates_audit_log(self, authenticated_client):
        from portfolio.models import Portfolio

        portfolio = Portfolio.objects.create(name="Test", exchange_id="binance")
        with patch(
            "trading.views.async_to_sync",
            return_value=lambda *a, **kw: 3,
        ):
            resp = authenticated_client.post(
                "/api/trading/cancel-all/",
                {"portfolio_id": portfolio.id},
                format="json",
            )
        assert resp.status_code == status.HTTP_200_OK
        log = AlertLog.objects.filter(event_type="cancel_all_orders").first()
        assert log is not None
        assert log.severity == "warning"

    def test_cancel_all_audit_log_contains_username(self, authenticated_client):
        from portfolio.models import Portfolio

        portfolio = Portfolio.objects.create(name="Test", exchange_id="binance")
        with patch(
            "trading.views.async_to_sync",
            return_value=lambda *a, **kw: 0,
        ):
            authenticated_client.post(
                "/api/trading/cancel-all/",
                {"portfolio_id": portfolio.id},
                format="json",
            )
        log = AlertLog.objects.filter(event_type="cancel_all_orders").first()
        assert "testuser" in log.message


@pytest.mark.django_db
class TestPerformanceZeroPriceGuard:
    def test_performance_skips_zero_price_orders(self):
        class FakeOrder:
            def __init__(self, oid, symbol, side, price, avg_fill_price, amount, filled):
                self.id = oid
                self.symbol = symbol
                self.side = side
                self.price = price
                self.avg_fill_price = avg_fill_price
                self.amount = amount
                self.filled = filled

        orders = [
            FakeOrder(1, "BTC/USDT", "buy", 50000.0, 50000.0, 1.0, 1.0),
            FakeOrder(2, "BTC/USDT", "sell", 0.0, 0.0, 1.0, 1.0),  # zero price — skipped
            FakeOrder(3, "ETH/USDT", "buy", 0, None, 0.5, 0.5),  # zero price — skipped
        ]

        result = TradingPerformanceService._compute_metrics(orders)
        assert result["total_trades"] == 3
        # Zero-price sell skipped, so BTC has buy cost but no sell revenue → negative P&L
        assert result["total_pnl"] == -50000.0

    def test_performance_empty_orders_returns_defaults(self):
        result = TradingPerformanceService._compute_metrics([])
        assert result["total_trades"] == 0
        assert result["win_rate"] == 0.0
        assert result["total_pnl"] == 0.0
        assert result["best_trade"] == 0.0
        assert result["worst_trade"] == 0.0
