"""Tests for MarketStatusView API endpoint — P12-7."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

ET = ZoneInfo("America/New_York")


def _et(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=ET)


@pytest.fixture
def auth_client(db, client):
    from django.contrib.auth.models import User

    User.objects.create_user(username="testuser", password="testpass123")
    client.login(username="testuser", password="testpass123")
    return client


@pytest.mark.django_db
class TestMarketStatusAPI:
    def test_crypto_always_open(self, auth_client):
        resp = auth_client.get("/api/market/status/?asset_class=crypto")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_open"] is True
        assert data["session"] == "crypto_24_7"

    def test_equity_during_trading_hours(self, auth_client):
        # Wed 12:00 PM ET — market open
        mock_now = _et(2026, 2, 25, 12, 0)
        with patch("common.market_hours.sessions.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            resp = auth_client.get("/api/market/status/?asset_class=equity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_open"] is True

    def test_equity_after_close(self, auth_client):
        # Wed 5:00 PM ET — market closed
        mock_now = _et(2026, 2, 25, 17, 0)
        with patch("common.market_hours.sessions.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            resp = auth_client.get("/api/market/status/?asset_class=equity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_open"] is False
        assert data["next_open"] is not None

    def test_equity_weekend(self, auth_client):
        # Sat Feb 28 2026
        mock_now = _et(2026, 2, 28, 12, 0)
        with patch("common.market_hours.sessions.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            resp = auth_client.get("/api/market/status/?asset_class=equity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_open"] is False

    def test_forex_weekday(self, auth_client):
        # Tue 12:00 PM ET
        mock_now = _et(2026, 2, 24, 12, 0)
        with patch("common.market_hours.sessions.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            resp = auth_client.get("/api/market/status/?asset_class=forex")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_open"] is True

    def test_forex_weekend(self, auth_client):
        # Sat Feb 28 2026
        mock_now = _et(2026, 2, 28, 12, 0)
        with patch("common.market_hours.sessions.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            resp = auth_client.get("/api/market/status/?asset_class=forex")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_open"] is False

    def test_invalid_asset_class_returns_400(self, auth_client):
        resp = auth_client.get("/api/market/status/?asset_class=commodities")
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_default_asset_class_is_crypto(self, auth_client):
        resp = auth_client.get("/api/market/status/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_open"] is True
        assert data["session"] == "crypto_24_7"
