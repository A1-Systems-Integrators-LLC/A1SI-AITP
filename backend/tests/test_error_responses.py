"""P6-6: Tests for error_response helper and JSON 404 responses."""

import pytest
from rest_framework import status

from core.error_response import error_response
from market.models import DataSourceConfig, ExchangeConfig


class TestErrorResponseHelper:
    def test_returns_json_body(self):
        resp = error_response("Something went wrong")
        assert resp.data == {"error": "Something went wrong"}

    def test_correct_status_code(self):
        resp = error_response("Not found", 404)
        assert resp.status_code == 404

    def test_default_status_400(self):
        resp = error_response("Bad request")
        assert resp.status_code == 400

    def test_body_structure(self):
        resp = error_response("test", 422)
        assert "error" in resp.data
        assert len(resp.data) == 1

    def test_custom_message(self):
        resp = error_response("Custom error message", 500)
        assert resp.data["error"] == "Custom error message"
        assert resp.status_code == 500


@pytest.mark.django_db
class TestExchangeConfig404JSON:
    def test_get_404_json(self, authenticated_client):
        resp = authenticated_client.get("/api/exchange-configs/99999/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert resp.json() == {"error": "Exchange config not found"}

    def test_put_404_json(self, authenticated_client):
        resp = authenticated_client.put(
            "/api/exchange-configs/99999/",
            {"name": "x"},
            format="json",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert resp.json() == {"error": "Exchange config not found"}

    def test_delete_404_json(self, authenticated_client):
        resp = authenticated_client.delete("/api/exchange-configs/99999/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert resp.json() == {"error": "Exchange config not found"}

    def test_test_connection_404_json(self, authenticated_client):
        resp = authenticated_client.post("/api/exchange-configs/99999/test/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert resp.json() == {"error": "Exchange config not found"}


@pytest.mark.django_db
class TestDataSourceConfig404JSON:
    def test_get_404_json(self, authenticated_client):
        resp = authenticated_client.get("/api/data-sources/99999/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert resp.json() == {"error": "Data source config not found"}

    def test_put_404_json(self, authenticated_client):
        resp = authenticated_client.put(
            "/api/data-sources/99999/",
            {"symbols": ["BTC/USDT"]},
            format="json",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert resp.json() == {"error": "Data source config not found"}

    def test_delete_404_json(self, authenticated_client):
        resp = authenticated_client.delete("/api/data-sources/99999/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert resp.json() == {"error": "Data source config not found"}


@pytest.mark.django_db
class TestPositiveResponses:
    def test_exchange_config_get_200(self, authenticated_client):
        config = ExchangeConfig.objects.create(name="Binance", exchange_id="binance")
        resp = authenticated_client.get(f"/api/exchange-configs/{config.pk}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["name"] == "Binance"

    def test_datasource_config_get_200(self, authenticated_client):
        exc = ExchangeConfig.objects.create(name="Binance", exchange_id="binance")
        ds = DataSourceConfig.objects.create(
            exchange_config=exc,
            symbols=["BTC/USDT"],
            timeframes=["1h"],
        )
        resp = authenticated_client.get(f"/api/data-sources/{ds.pk}/")
        assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestExistingEndpointsStillReturnJSON:
    def test_exchange_config_list_returns_json(self, authenticated_client):
        resp = authenticated_client.get("/api/exchange-configs/")
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.json(), list)
