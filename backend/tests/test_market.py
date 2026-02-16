"""Market API tests — exchange list (no external API calls)."""

import pytest


@pytest.mark.django_db
class TestMarket:
    def test_list_exchanges(self, authenticated_client):
        resp = authenticated_client.get("/api/exchanges/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["id"] in ["binance", "coinbase", "kraken", "kucoin", "bybit"]

    def test_indicator_list(self, authenticated_client):
        resp = authenticated_client.get("/api/indicators/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert "rsi_14" in data
        assert "sma_50" in data
