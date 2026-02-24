"""Data quality API tests."""

from dataclasses import dataclass
from unittest.mock import patch

import pytest


@dataclass
class MockQualityReport:
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    exchange: str = "binance"
    rows: int = 1000
    date_range: tuple = ("2025-01-01", "2025-12-31")
    gaps: list = None
    nan_columns: dict = None
    outliers: list = None
    ohlc_violations: list = None
    is_stale: bool = False
    stale_hours: float = 0.5
    passed: bool = True
    issues_summary: list = None

    def __post_init__(self):
        if self.gaps is None:
            self.gaps = []
        if self.nan_columns is None:
            self.nan_columns = {}
        if self.outliers is None:
            self.outliers = []
        if self.ohlc_violations is None:
            self.ohlc_violations = []
        if self.issues_summary is None:
            self.issues_summary = []


@pytest.mark.django_db
class TestDataQualityListAPI:
    @patch("core.platform_bridge.ensure_platform_imports")
    @patch("common.data_pipeline.pipeline.validate_all_data")
    def test_quality_list(self, mock_validate, mock_imports, authenticated_client):
        mock_validate.return_value = [
            MockQualityReport(symbol="BTC/USDT", passed=True),
            MockQualityReport(symbol="ETH/USDT", passed=False, issues_summary=["stale data"]),
        ]
        resp = authenticated_client.get("/api/data/quality/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["passed"] == 1
        assert data["failed"] == 1
        assert len(data["reports"]) == 2

    @patch("core.platform_bridge.ensure_platform_imports")
    @patch("common.data_pipeline.pipeline.validate_all_data")
    def test_quality_list_empty(self, mock_validate, mock_imports, authenticated_client):
        mock_validate.return_value = []
        resp = authenticated_client.get("/api/data/quality/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["reports"] == []

    def test_quality_list_auth_required(self):
        from django.test import Client

        client = Client()
        resp = client.get("/api/data/quality/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestDataQualityDetailAPI:
    @patch("core.platform_bridge.ensure_platform_imports")
    @patch("common.data_pipeline.pipeline.validate_data")
    def test_quality_detail(self, mock_validate, mock_imports, authenticated_client):
        mock_validate.return_value = MockQualityReport(
            symbol="BTC/USDT", timeframe="1h", passed=True, rows=5000,
        )
        resp = authenticated_client.get("/api/data/quality/BTC_USDT/1h/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "BTC/USDT"
        assert data["rows"] == 5000
        assert data["passed"] is True

    @patch("core.platform_bridge.ensure_platform_imports")
    @patch("common.data_pipeline.pipeline.validate_data")
    def test_quality_detail_not_found(self, mock_validate, mock_imports, authenticated_client):
        mock_validate.side_effect = FileNotFoundError("file not found")
        resp = authenticated_client.get("/api/data/quality/XYZ_USDT/1h/")
        assert resp.status_code == 404

    @patch("core.platform_bridge.ensure_platform_imports")
    @patch("common.data_pipeline.pipeline.validate_data")
    def test_quality_detail_with_exchange(self, mock_validate, mock_imports, authenticated_client):
        mock_validate.return_value = MockQualityReport(exchange="kraken")
        resp = authenticated_client.get("/api/data/quality/BTC_USDT/1h/?exchange=kraken")
        assert resp.status_code == 200
        mock_validate.assert_called_with("BTC/USDT", "1h", "kraken")
