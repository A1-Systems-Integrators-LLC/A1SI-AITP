"""
Tests for kill switch (halt/resume) endpoints — Django version.
"""

import pytest


@pytest.mark.django_db
class TestHaltEndpoint:
    def test_halt_trading(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/risk/1/halt/",
            {"reason": "manual test halt"},
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_halted"] is True

    def test_resume_trading(self, authenticated_client):
        # First halt
        authenticated_client.post(
            "/api/risk/1/halt/", {"reason": "test"}, format="json"
        )
        # Then resume
        resp = authenticated_client.post("/api/risk/1/resume/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_halted"] is False

    def test_halted_trade_rejected(self, authenticated_client):
        # Halt trading
        authenticated_client.post(
            "/api/risk/1/halt/", {"reason": "emergency"}, format="json"
        )
        # Attempt a trade check
        resp = authenticated_client.post(
            "/api/risk/1/check-trade/",
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "size": 0.01,
                "entry_price": 97000,
                "stop_loss_price": 92150,
            },
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["approved"] is False
        assert "halted" in data["reason"].lower()

    def test_resume_then_trade_approved(self, authenticated_client):
        # Halt then resume
        authenticated_client.post(
            "/api/risk/1/halt/", {"reason": "test"}, format="json"
        )
        authenticated_client.post("/api/risk/1/resume/")
        # Trade should be approved now
        resp = authenticated_client.post(
            "/api/risk/1/check-trade/",
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "size": 0.01,
                "entry_price": 50000,
                "stop_loss_price": 48500,
            },
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["approved"] is True

    def test_halt_status_visible(self, authenticated_client):
        authenticated_client.post(
            "/api/risk/1/halt/", {"reason": "visible check"}, format="json"
        )
        resp = authenticated_client.get("/api/risk/1/status/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_halted"] is True
