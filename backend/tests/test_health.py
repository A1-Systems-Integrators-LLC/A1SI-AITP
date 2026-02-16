"""Health endpoint test."""

import pytest


@pytest.mark.django_db
class TestHealth:
    def test_health(self, api_client):
        resp = api_client.get("/api/health/")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
