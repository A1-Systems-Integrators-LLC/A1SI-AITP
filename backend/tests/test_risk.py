"""Risk management API tests."""

import sys
from pathlib import Path

# Ensure common modules are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest


@pytest.mark.django_db
class TestRisk:
    def test_get_status(self, authenticated_client):
        resp = authenticated_client.get("/api/risk/1/status/")
        assert resp.status_code == 200
        data = resp.json()
        assert "equity" in data
        assert "is_halted" in data
        assert data["equity"] == 10000.0

    def test_get_limits(self, authenticated_client):
        resp = authenticated_client.get("/api/risk/1/limits/")
        assert resp.status_code == 200
        data = resp.json()
        assert "max_portfolio_drawdown" in data

    def test_update_limits(self, authenticated_client):
        resp = authenticated_client.put(
            "/api/risk/1/limits/",
            {"max_daily_loss": 0.10},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["max_daily_loss"] == 0.10

    def test_halt_resume(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/risk/1/halt/",
            {"reason": "Test halt"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["is_halted"] is True

        resp = authenticated_client.post("/api/risk/1/resume/")
        assert resp.status_code == 200
        assert resp.json()["is_halted"] is False
