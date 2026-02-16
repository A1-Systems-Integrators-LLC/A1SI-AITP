"""Exchange API tests."""

import pytest


@pytest.mark.django_db
class TestExchanges:
    def test_list_exchanges(self, authenticated_client):
        resp = authenticated_client.get("/api/exchanges/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        ids = [e["id"] for e in data]
        assert "binance" in ids
