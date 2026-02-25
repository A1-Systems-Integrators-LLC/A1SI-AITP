"""Tests for P13-3: refined exception handling in views, analytics, middleware."""

import time
from unittest.mock import MagicMock, patch

import pytest  # noqa: I001

# ── DataQualityListView: ImportError → 503, OSError/ValueError → 500 ──


@pytest.mark.django_db
class TestDataQualityListExceptions:
    @patch("core.platform_bridge.ensure_platform_imports")
    def test_import_error_returns_503(self, mock_imports, authenticated_client):
        with patch.dict("sys.modules", {"common.data_pipeline.pipeline": None}):
            resp = authenticated_client.get("/api/data/quality/")
        assert resp.status_code == 503
        assert "not available" in resp.json()["error"]

    @patch("core.platform_bridge.ensure_platform_imports")
    def test_os_error_returns_500(self, mock_imports, authenticated_client):
        mock_mod = MagicMock()
        mock_mod.validate_all_data.side_effect = OSError("disk read error")
        with patch.dict("sys.modules", {"common.data_pipeline.pipeline": mock_mod}):
            resp = authenticated_client.get("/api/data/quality/")
        assert resp.status_code == 500
        assert "failed" in resp.json()["error"]

    @patch("core.platform_bridge.ensure_platform_imports")
    def test_value_error_returns_500(self, mock_imports, authenticated_client):
        mock_mod = MagicMock()
        mock_mod.validate_all_data.side_effect = ValueError("bad data format")
        with patch.dict("sys.modules", {"common.data_pipeline.pipeline": mock_mod}):
            resp = authenticated_client.get("/api/data/quality/")
        assert resp.status_code == 500
        assert "failed" in resp.json()["error"]


# ── DataQualityDetailView: ImportError → 503, OSError → 500 ──


@pytest.mark.django_db
class TestDataQualityDetailExceptions:
    @patch("core.platform_bridge.ensure_platform_imports")
    def test_import_error_returns_503(self, mock_imports, authenticated_client):
        with patch.dict("sys.modules", {"common.data_pipeline.pipeline": None}):
            resp = authenticated_client.get("/api/data/quality/BTC_USDT/1h/")
        assert resp.status_code == 503
        assert "not available" in resp.json()["error"]

    @patch("core.platform_bridge.ensure_platform_imports")
    def test_os_error_returns_500(self, mock_imports, authenticated_client):
        mock_mod = MagicMock()
        mock_mod.validate_data.side_effect = OSError("permission denied")
        with patch.dict("sys.modules", {"common.data_pipeline.pipeline": mock_mod}):
            resp = authenticated_client.get("/api/data/quality/BTC_USDT/1h/")
        assert resp.status_code == 500
        assert "failed" in resp.json()["error"]


# ── _fetch_prices: ImportError → warning, ConnectionError/TimeoutError → warning ──


@pytest.mark.django_db
class TestFetchPricesExceptions:
    def test_import_error_returns_empty(self):
        from portfolio.models import Holding
        from portfolio.services.analytics import _fetch_prices

        holdings = [MagicMock(spec=Holding, symbol="BTC/USDT")]
        with patch.dict("sys.modules", {"market.services.exchange": None}):
            result = _fetch_prices(holdings, "binance")
        assert result == {}

    def test_connection_error_returns_empty(self):
        from portfolio.models import Holding
        from portfolio.services.analytics import _fetch_prices

        mock_exchange_mod = MagicMock()
        mock_exchange_mod.ExchangeService.side_effect = ConnectionError("refused")
        holdings = [MagicMock(spec=Holding, symbol="BTC/USDT")]
        with patch.dict("sys.modules", {"market.services.exchange": mock_exchange_mod}):
            result = _fetch_prices(holdings, "binance")
        assert result == {}

    def test_timeout_error_returns_empty(self):
        from portfolio.models import Holding
        from portfolio.services.analytics import _fetch_prices

        mock_exchange_mod = MagicMock()
        mock_exchange_mod.ExchangeService.side_effect = TimeoutError("timed out")
        holdings = [MagicMock(spec=Holding, symbol="BTC/USDT")]
        with patch.dict("sys.modules", {"market.services.exchange": mock_exchange_mod}):
            result = _fetch_prices(holdings, "binance")
        assert result == {}


# ── AuditMiddleware: ImportError/RuntimeError → debug, Exception → warning ──


class TestAuditMiddlewareExceptions:
    def test_import_error_does_not_block_response(self):
        from core.middleware import AuditMiddleware

        mw = AuditMiddleware(lambda r: MagicMock(status_code=201))

        request = MagicMock()
        request.method = "POST"
        request.path = "/api/test/"
        request.user.is_authenticated = True
        request.user.username = "admin"
        request.META = {"REMOTE_ADDR": "127.0.0.1"}

        with patch("core.models.AuditLog") as mock_model:
            mock_model.objects.create.side_effect = ImportError("app not ready")
            response = mw(request)
            time.sleep(0.2)

        assert response.status_code == 201

    def test_runtime_error_does_not_block_response(self):
        from core.middleware import AuditMiddleware

        mw = AuditMiddleware(lambda r: MagicMock(status_code=200))

        request = MagicMock()
        request.method = "DELETE"
        request.path = "/api/test/"
        request.user.is_authenticated = False
        request.META = {"REMOTE_ADDR": "127.0.0.1"}

        with patch("core.models.AuditLog") as mock_model:
            mock_model.objects.create.side_effect = RuntimeError("shutting down")
            response = mw(request)
            time.sleep(0.2)

        assert response.status_code == 200

    def test_general_exception_does_not_block_response(self):
        from core.middleware import AuditMiddleware

        mw = AuditMiddleware(lambda r: MagicMock(status_code=201))

        request = MagicMock()
        request.method = "POST"
        request.path = "/api/test/"
        request.user.is_authenticated = True
        request.user.username = "admin"
        request.META = {"REMOTE_ADDR": "10.0.0.1"}

        with patch("core.models.AuditLog") as mock_model:
            mock_model.objects.create.side_effect = Exception("db disk full")
            response = mw(request)
            time.sleep(0.2)

        assert response.status_code == 201

    def test_get_request_not_audited(self):
        from core.middleware import AuditMiddleware

        mw = AuditMiddleware(lambda r: MagicMock(status_code=200))

        request = MagicMock()
        request.method = "GET"
        request.path = "/api/test/"
        request.META = {"REMOTE_ADDR": "127.0.0.1"}

        with patch("core.middleware.AuditMiddleware._log_async") as mock_log:
            mw(request)
            mock_log.assert_not_called()
