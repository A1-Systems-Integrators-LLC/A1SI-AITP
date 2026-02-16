"""
Tests for Regime Dashboard API — Django version.
Covers: RegimeService (with mocked data), API endpoints.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from market.services.regime import RegimeService

# ── Helpers ──────────────────────────────────────────────────


def _make_synthetic_df(n: int = 500, trend: str = "up") -> pd.DataFrame:
    """Create synthetic OHLCV data for testing."""
    np.random.seed(42)
    if trend == "up":
        close = 100 + np.linspace(0, 50, n) + np.random.randn(n) * 0.5
    elif trend == "down":
        close = 200 - np.linspace(0, 50, n) + np.random.randn(n) * 0.5
    else:
        close = (
            100
            + np.sin(np.linspace(0, 20, n)) * 3
            + np.random.randn(n) * 0.3
        )
    high = close + np.abs(np.random.randn(n) * 0.8)
    low = close - np.abs(np.random.randn(n) * 0.8)
    volume = np.random.uniform(1000, 5000, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=idx,
    )


def _make_service_with_data(trend: str = "ranging") -> RegimeService:
    """Create RegimeService with mocked data loader."""
    service = RegimeService(symbols=["BTC/USDT", "ETH/USDT"])
    df = _make_synthetic_df(trend=trend)

    with patch.object(service, "_load_data", return_value=df):
        service.get_current_regime("BTC/USDT")
        service.get_current_regime("ETH/USDT")

    return service


# ── RegimeService Unit Tests ─────────────────────────────────


class TestRegimeService:
    def test_get_current_regime_returns_dict(self):
        service = RegimeService(symbols=["BTC/USDT"])
        df = _make_synthetic_df(trend="ranging")

        with patch.object(service, "_load_data", return_value=df):
            result = service.get_current_regime("BTC/USDT")

        assert result is not None
        assert result["symbol"] == "BTC/USDT"
        assert "regime" in result
        assert "confidence" in result
        assert "adx_value" in result

    def test_get_current_regime_no_data(self):
        service = RegimeService(symbols=["BTC/USDT"])
        with patch.object(service, "_load_data", return_value=None):
            result = service.get_current_regime("UNKNOWN/PAIR")
        assert result is None

    def test_get_all_current_regimes(self):
        service = RegimeService(symbols=["BTC/USDT", "ETH/USDT"])
        df = _make_synthetic_df(trend="ranging")

        with patch.object(service, "_load_data", return_value=df):
            results = service.get_all_current_regimes()

        assert len(results) == 2
        symbols = {r["symbol"] for r in results}
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols

    def test_get_regime_history(self):
        service = RegimeService(symbols=["BTC/USDT"])
        df = _make_synthetic_df(trend="ranging")

        with patch.object(service, "_load_data", return_value=df):
            service.get_current_regime("BTC/USDT")
            service.get_current_regime("BTC/USDT")
            service.get_current_regime("BTC/USDT")

        history = service.get_regime_history("BTC/USDT")
        assert len(history) == 3
        assert "timestamp" in history[0]
        assert "regime" in history[0]
        assert "confidence" in history[0]

    def test_get_regime_history_with_limit(self):
        service = RegimeService(symbols=["BTC/USDT"])
        df = _make_synthetic_df(trend="ranging")

        with patch.object(service, "_load_data", return_value=df):
            for _ in range(5):
                service.get_current_regime("BTC/USDT")

        history = service.get_regime_history("BTC/USDT", limit=2)
        assert len(history) == 2

    def test_get_recommendation(self):
        service = RegimeService(symbols=["BTC/USDT"])
        df = _make_synthetic_df(trend="ranging")

        with patch.object(service, "_load_data", return_value=df):
            result = service.get_recommendation("BTC/USDT")

        assert result is not None
        assert result["symbol"] == "BTC/USDT"
        assert "primary_strategy" in result
        assert "weights" in result
        assert "position_size_modifier" in result

    def test_get_recommendation_no_data(self):
        service = RegimeService(symbols=["BTC/USDT"])
        with patch.object(service, "_load_data", return_value=None):
            result = service.get_recommendation("UNKNOWN/PAIR")
        assert result is None

    def test_get_all_recommendations(self):
        service = RegimeService(symbols=["BTC/USDT", "ETH/USDT"])
        df = _make_synthetic_df(trend="ranging")

        with patch.object(service, "_load_data", return_value=df):
            results = service.get_all_recommendations()

        assert len(results) == 2


# ── API Endpoint Tests (using Django test client) ───────────


@pytest.mark.django_db
class TestRegimeAPI:
    def test_get_all_regimes(self, authenticated_client):
        service = _make_service_with_data(trend="ranging")
        with patch("market.views._regime_service", service):
            resp = authenticated_client.get("/api/regime/current/")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 2

    def test_get_single_regime(self, authenticated_client):
        service = _make_service_with_data(trend="ranging")
        with patch("market.views._regime_service", service):
            resp = authenticated_client.get("/api/regime/current/BTC/USDT/")
            assert resp.status_code == 200
            data = resp.json()
            assert data["symbol"] == "BTC/USDT"
            assert "regime" in data
            assert "confidence" in data

    def test_position_size_endpoint(self, authenticated_client):
        service = _make_service_with_data(trend="ranging")
        with patch("market.views._regime_service", service):
            resp = authenticated_client.post(
                "/api/regime/position-size/",
                {
                    "symbol": "BTC/USDT",
                    "entry_price": 50000,
                    "stop_loss_price": 49000,
                },
                format="json",
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "position_size" in data
            assert "regime_modifier" in data
            assert "primary_strategy" in data
            assert data["entry_price"] == 50000

    def test_position_size_returns_regime_info(self, authenticated_client):
        service = _make_service_with_data(trend="ranging")
        with patch("market.views._regime_service", service):
            resp = authenticated_client.post(
                "/api/regime/position-size/",
                {
                    "symbol": "BTC/USDT",
                    "entry_price": 100,
                    "stop_loss_price": 90,
                },
                format="json",
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["regime"] != ""
            assert data["regime_modifier"] > 0
            assert data["position_size"] > 0
