"""Phase 8 — portfolio 100% coverage: models, views, analytics edge cases."""

from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError

from portfolio.models import Holding, Portfolio


@pytest.mark.django_db
class TestPortfolioModel:
    def test_str(self):
        p = Portfolio.objects.create(name="Test Portfolio")
        assert str(p) == "Test Portfolio"


@pytest.mark.django_db
class TestHoldingModel:
    def test_str(self):
        p = Portfolio.objects.create(name="P")
        h = Holding.objects.create(portfolio=p, symbol="BTC/USDT", amount=1.5)
        assert str(h) == "BTC/USDT x1.5"

    def test_clean_negative_amount(self):
        p = Portfolio.objects.create(name="P")
        h = Holding(portfolio=p, symbol="BTC", amount=-1.0, avg_buy_price=100)
        with pytest.raises(ValidationError) as exc:
            h.clean()
        assert "amount" in exc.value.message_dict

    def test_clean_negative_avg_buy_price(self):
        p = Portfolio.objects.create(name="P")
        h = Holding(portfolio=p, symbol="BTC", amount=1.0, avg_buy_price=-50)
        with pytest.raises(ValidationError) as exc:
            h.clean()
        assert "avg_buy_price" in exc.value.message_dict

    def test_clean_both_negative(self):
        p = Portfolio.objects.create(name="P")
        h = Holding(portfolio=p, symbol="BTC", amount=-1.0, avg_buy_price=-50)
        with pytest.raises(ValidationError) as exc:
            h.clean()
        assert "amount" in exc.value.message_dict
        assert "avg_buy_price" in exc.value.message_dict

    def test_clean_valid(self):
        p = Portfolio.objects.create(name="P")
        h = Holding(portfolio=p, symbol="BTC", amount=1.0, avg_buy_price=100)
        h.clean()  # no exception


@pytest.mark.django_db
class TestPortfolioDetailPut:
    def test_put_success(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/portfolios/", {"name": "Original"}, format="json",
        )
        pid = resp.json()["id"]

        resp = authenticated_client.put(
            f"/api/portfolios/{pid}/",
            {"name": "Updated", "exchange_id": "kraken", "description": "new desc"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"
        assert resp.json()["description"] == "new desc"

    def test_put_not_found(self, authenticated_client):
        resp = authenticated_client.put(
            "/api/portfolios/9999/",
            {"name": "X"},
            format="json",
        )
        assert resp.status_code == 404


@pytest.mark.django_db
class TestPortfolioDetailPatch:
    def test_patch_partial(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/portfolios/", {"name": "Original"}, format="json",
        )
        pid = resp.json()["id"]

        resp = authenticated_client.patch(
            f"/api/portfolios/{pid}/",
            {"description": "patched"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "patched"
        assert resp.json()["name"] == "Original"  # unchanged

    def test_patch_not_found(self, authenticated_client):
        resp = authenticated_client.patch(
            "/api/portfolios/9999/",
            {"name": "X"},
            format="json",
        )
        assert resp.status_code == 404


@pytest.mark.django_db
class TestHoldingDetailPut:
    def _setup(self, client):
        resp = client.post("/api/portfolios/", {"name": "P"}, format="json")
        pid = resp.json()["id"]
        resp = client.post(
            f"/api/portfolios/{pid}/holdings/",
            {"symbol": "BTC", "amount": 1.0, "avg_buy_price": 50000},
            format="json",
        )
        hid = resp.json()["id"]
        return pid, hid

    def test_put_holding(self, authenticated_client):
        pid, hid = self._setup(authenticated_client)
        resp = authenticated_client.put(
            f"/api/portfolios/{pid}/holdings/{hid}/",
            {"amount": 2.0, "avg_buy_price": 55000},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["amount"] == 2.0
        assert resp.json()["avg_buy_price"] == 55000

    def test_put_holding_not_found(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/portfolios/", {"name": "P"}, format="json",
        )
        pid = resp.json()["id"]
        resp = authenticated_client.put(
            f"/api/portfolios/{pid}/holdings/9999/",
            {"amount": 1.0},
            format="json",
        )
        assert resp.status_code == 404


@pytest.mark.django_db
class TestHoldingDetailDelete:
    def test_delete_holding(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/portfolios/", {"name": "P"}, format="json",
        )
        pid = resp.json()["id"]
        resp = authenticated_client.post(
            f"/api/portfolios/{pid}/holdings/",
            {"symbol": "ETH", "amount": 5.0, "avg_buy_price": 3000},
            format="json",
        )
        hid = resp.json()["id"]

        resp = authenticated_client.delete(f"/api/portfolios/{pid}/holdings/{hid}/")
        assert resp.status_code == 204

        # Verify gone
        resp = authenticated_client.get(f"/api/portfolios/{pid}/")
        assert len(resp.json()["holdings"]) == 0

    def test_delete_holding_not_found(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/portfolios/", {"name": "P"}, format="json",
        )
        pid = resp.json()["id"]
        resp = authenticated_client.delete(f"/api/portfolios/{pid}/holdings/9999/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestHoldingCreateDuplicate:
    def test_duplicate_symbol_returns_409(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/portfolios/", {"name": "P"}, format="json",
        )
        pid = resp.json()["id"]
        authenticated_client.post(
            f"/api/portfolios/{pid}/holdings/",
            {"symbol": "BTC", "amount": 1.0, "avg_buy_price": 50000},
            format="json",
        )
        # Duplicate
        resp = authenticated_client.post(
            f"/api/portfolios/{pid}/holdings/",
            {"symbol": "BTC", "amount": 2.0, "avg_buy_price": 60000},
            format="json",
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["error"]


@pytest.mark.django_db
class TestFetchPricesExceptions:
    def test_import_error_fallback(self):
        """When ExchangeService can't be imported, _fetch_prices returns empty."""
        import importlib
        import sys

        import portfolio.services.analytics as mod

        p = Portfolio.objects.create(name="P")
        h = Holding.objects.create(portfolio=p, symbol="BTC", amount=1.0, avg_buy_price=50000)

        # Temporarily remove the module so the local import inside _fetch_prices fails
        saved = sys.modules.get("market.services.exchange")
        sys.modules["market.services.exchange"] = None  # type: ignore[assignment]
        try:
            # Reload so the function's local import will hit the None sentinel
            importlib.reload(mod)
            result = mod._fetch_prices([h], "kraken")
            assert result == {}
        finally:
            if saved is not None:
                sys.modules["market.services.exchange"] = saved
            else:
                sys.modules.pop("market.services.exchange", None)
            importlib.reload(mod)

    def test_connection_error_on_service_init(self):
        """ConnectionError during ExchangeService init."""
        from portfolio.services.analytics import _fetch_prices

        p = Portfolio.objects.create(name="P")
        h = Holding.objects.create(portfolio=p, symbol="BTC", amount=1.0, avg_buy_price=50000)

        with patch(
            "market.services.exchange.ExchangeService",
            side_effect=ConnectionError("refused"),
        ):
            result = _fetch_prices([h], "kraken")
        assert result == {}

    def test_timeout_error_on_service_init(self):
        """TimeoutError during ExchangeService init."""
        from portfolio.services.analytics import _fetch_prices

        p = Portfolio.objects.create(name="P")
        h = Holding.objects.create(portfolio=p, symbol="BTC", amount=1.0, avg_buy_price=50000)

        with patch(
            "market.services.exchange.ExchangeService",
            side_effect=TimeoutError("timed out"),
        ):
            result = _fetch_prices([h], "kraken")
        assert result == {}

    def test_os_error_on_service_init(self):
        """OSError during ExchangeService init."""
        from portfolio.services.analytics import _fetch_prices

        p = Portfolio.objects.create(name="P")
        h = Holding.objects.create(portfolio=p, symbol="BTC", amount=1.0, avg_buy_price=50000)

        with patch(
            "market.services.exchange.ExchangeService",
            side_effect=OSError("network down"),
        ):
            result = _fetch_prices([h], "kraken")
        assert result == {}
