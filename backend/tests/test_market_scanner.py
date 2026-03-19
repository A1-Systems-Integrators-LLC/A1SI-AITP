"""Tests for MarketScannerService — multi-asset scanning."""

import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Ensure common.* is importable for patch targets
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from market.models import MarketOpportunity
from market.services.market_scanner import _THRESHOLDS, MarketScannerService


def _make_ohlcv(
    n: int = 200, base_price: float = 1.1000, volatility: float = 0.002,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="h")
    close = base_price + np.cumsum(np.random.randn(n) * volatility)
    close = np.maximum(close, 0.0001)
    return pd.DataFrame(
        {
            "open": close * (1 + np.random.uniform(-0.001, 0.001, n)),
            "high": close * (1 + np.random.uniform(0, 0.003, n)),
            "low": close * (1 - np.random.uniform(0, 0.003, n)),
            "close": close,
            "volume": np.random.uniform(100, 1000, n),
        },
        index=dates,
    )


class TestThresholds:
    def test_crypto_thresholds_exist(self):
        assert "crypto" in _THRESHOLDS
        assert _THRESHOLDS["crypto"]["volume_surge_ratio"] == 2.0
        assert _THRESHOLDS["crypto"]["pullback_min_pct"] == 3.0

    def test_forex_thresholds_tighter(self):
        assert "forex" in _THRESHOLDS
        assert _THRESHOLDS["forex"]["volume_surge_ratio"] == 1.5
        assert _THRESHOLDS["forex"]["pullback_min_pct"] == 0.3
        assert _THRESHOLDS["forex"]["pullback_max_pct"] == 1.0
        assert _THRESHOLDS["forex"]["breakout_distance_pct"] == 0.5

    def test_equity_thresholds_exist(self):
        assert "equity" in _THRESHOLDS


class TestVolumeSurge:
    def test_crypto_default_threshold(self):
        volume = pd.Series([100.0] * 168 + [250.0] * 24)
        opp = MarketScannerService._check_volume_surge("BTC/USDT", volume, 50000.0, "1h")
        assert opp is not None
        assert opp["type"] == "volume_surge"

    def test_crypto_below_threshold(self):
        volume = pd.Series([100.0] * 168 + [150.0] * 24)
        opp = MarketScannerService._check_volume_surge("BTC/USDT", volume, 50000.0, "1h")
        assert opp is None

    def test_forex_lower_threshold(self):
        volume = pd.Series([100.0] * 168 + [170.0] * 24)
        opp = MarketScannerService._check_volume_surge(
            "EUR/USD", volume, 1.1000, "1h", surge_ratio=1.5,
        )
        assert opp is not None

    def test_forex_tick_volume_note(self):
        volume = pd.Series([100.0] * 168 + [200.0] * 24)
        opp = MarketScannerService._check_volume_surge(
            "EUR/USD", volume, 1.1000, "1h",
            surge_ratio=1.5, is_tick_volume=True,
        )
        assert opp is not None
        assert opp["details"]["note"] == "tick volume"

    def test_crypto_no_tick_volume_note(self):
        volume = pd.Series([100.0] * 168 + [250.0] * 24)
        opp = MarketScannerService._check_volume_surge(
            "BTC/USDT", volume, 50000.0, "1h",
            surge_ratio=2.0, is_tick_volume=False,
        )
        assert opp is not None
        assert "note" not in opp["details"]


class TestTrendPullback:
    def test_crypto_pullback_range(self):
        close = pd.Series([100.0] * 50)
        close.iloc[-10] = 100.0
        close.iloc[-1] = 96.0  # 4% pullback
        adx_series = pd.Series([30.0] * 50)
        ema_50 = pd.Series([90.0] * 50)
        opp = MarketScannerService._check_trend_pullback(
            "BTC/USDT", close, adx_series, ema_50, 96.0, "1h",
        )
        assert opp is not None

    def test_forex_pullback_range(self):
        close = pd.Series([1.1000] * 50)
        close.iloc[-10] = 1.1000
        close.iloc[-1] = 1.0945  # ~0.5% pullback
        adx_series = pd.Series([30.0] * 50)
        ema_50 = pd.Series([1.0800] * 50)
        opp = MarketScannerService._check_trend_pullback(
            "EUR/USD", close, adx_series, ema_50, 1.0945, "1h",
            pullback_min=0.3, pullback_max=1.0,
        )
        assert opp is not None

    def test_forex_pullback_rejected_by_crypto_thresholds(self):
        close = pd.Series([1.1000] * 50)
        close.iloc[-10] = 1.1000
        close.iloc[-1] = 1.0945
        adx_series = pd.Series([30.0] * 50)
        ema_50 = pd.Series([1.0800] * 50)
        opp = MarketScannerService._check_trend_pullback(
            "EUR/USD", close, adx_series, ema_50, 1.0945, "1h",
            pullback_min=3.0, pullback_max=5.0,
        )
        assert opp is None


class TestBreakout:
    def test_crypto_breakout_distance(self):
        close = pd.Series([100.0] * 20)
        close.iloc[-20] = 101.0
        close.iloc[-1] = 100.0  # ~1% distance
        volume = pd.Series([100.0] * 5 + [200.0] * 5)
        sma_20 = pd.Series([99.0] * 20)
        opp = MarketScannerService._check_breakout(
            "BTC/USDT", close, volume, sma_20, 100.0, "1h",
        )
        assert opp is not None

    def test_forex_tighter_breakout(self):
        close = pd.Series([1.1000] * 20)
        close.iloc[-20] = 1.1010
        close.iloc[-1] = 1.1005  # ~0.045% distance (within 0.5%)
        volume = pd.Series([100.0] * 5 + [200.0] * 5)
        sma_20 = pd.Series([1.0990] * 20)
        opp = MarketScannerService._check_breakout(
            "EUR/USD", close, volume, sma_20, 1.1005, "1h",
            distance_pct=0.5,
        )
        assert opp is not None


@pytest.mark.django_db
class TestScanAllIntegration:
    @patch("market.services.market_scanner.MarketScannerService._maybe_alert")
    def test_scan_all_forex(self, mock_alert):
        """scan_all(asset_class='forex') creates forex opportunities."""
        df = _make_ohlcv(200, base_price=1.1000, volatility=0.0005)

        config = {"data": {"forex_watchlist": ["EUR/USD", "GBP/USD"]}}

        with (
            patch("common.data_pipeline.pipeline.load_ohlcv", return_value=df),
            patch("core.platform_bridge.get_platform_config", return_value=config),
            patch("core.platform_bridge.ensure_platform_imports"),
        ):
            scanner = MarketScannerService()
            result = scanner.scan_all(asset_class="forex")

        assert result["status"] == "completed"
        assert result["asset_class"] == "forex"
        for opp in MarketOpportunity.objects.all():
            assert opp.asset_class == "forex"

    @patch("market.services.market_scanner.MarketScannerService._maybe_alert")
    def test_scan_all_crypto_default(self, mock_alert):
        """scan_all() defaults to crypto and uses crypto thresholds."""
        df = _make_ohlcv(200, base_price=50000, volatility=500)

        config = {"data": {"watchlist": ["BTC/USDT"]}}

        with (
            patch("common.data_pipeline.pipeline.load_ohlcv", return_value=df),
            patch("core.platform_bridge.get_platform_config", return_value=config),
            patch("core.platform_bridge.ensure_platform_imports"),
        ):
            scanner = MarketScannerService()
            result = scanner.scan_all(asset_class="crypto")

        assert result["status"] == "completed"
        assert result["asset_class"] == "crypto"
        for opp in MarketOpportunity.objects.all():
            assert opp.asset_class == "crypto"

    def test_scan_all_empty_watchlist(self):
        """Empty watchlist returns skipped."""
        config = {"data": {"forex_watchlist": []}}
        with (
            patch("core.platform_bridge.get_platform_config", return_value=config),
            patch("core.platform_bridge.ensure_platform_imports"),
        ):
            scanner = MarketScannerService()
            result = scanner.scan_all(asset_class="forex")
        assert result["status"] == "skipped"

    def test_scan_all_uses_yfinance_for_forex(self):
        """Forex scans should use yfinance exchange_id."""
        config = {"data": {"forex_watchlist": ["EUR/USD"]}}
        mock_load = MagicMock(return_value=pd.DataFrame())

        with (
            patch("common.data_pipeline.pipeline.load_ohlcv", mock_load),
            patch("core.platform_bridge.get_platform_config", return_value=config),
            patch("core.platform_bridge.ensure_platform_imports"),
        ):
            scanner = MarketScannerService()
            scanner.scan_all(asset_class="forex")

        mock_load.assert_called_once_with("EUR/USD", "1h", exchange_id="yfinance")


@pytest.mark.django_db
class TestScannerDeduplication:
    """Verify scanner uses update_or_create to prevent duplicate opportunities."""

    def test_duplicate_scan_updates_instead_of_creating(self):
        """Running scan_all twice for the same symbol should not create duplicate records."""
        from django.utils import timezone

        from market.models import MarketOpportunity

        # Create initial opportunity
        now = timezone.now()
        expires = now + timedelta(hours=24)
        MarketOpportunity.objects.create(
            symbol="BTC/USDT",
            opportunity_type="volume_surge",
            asset_class="crypto",
            score=60,
            expires_at=expires,
            acted_on=False,
        )

        # Build mock data that triggers a volume_surge detection
        idx = pd.date_range("2024-01-01", periods=100, freq="h")
        volume = pd.Series([100.0] * 99 + [500.0], index=idx)  # Last bar: 5x surge
        close = pd.Series([100.0] * 100, index=idx)
        high = pd.Series([101.0] * 100, index=idx)
        low = pd.Series([99.0] * 100, index=idx)
        df = pd.DataFrame(
            {"open": close, "high": high, "low": low, "close": close, "volume": volume},
            index=idx,
        )

        config = {"data": {"watchlist": ["BTC/USDT"]}}
        with (
            patch("common.data_pipeline.pipeline.load_ohlcv", return_value=df),
            patch("core.platform_bridge.get_platform_config", return_value=config),
            patch("core.platform_bridge.ensure_platform_imports"),
        ):
            scanner = MarketScannerService()
            scanner.scan_all(asset_class="crypto")

        # Should have at most 1 unexpired volume_surge for BTC/USDT
        volume_surges = MarketOpportunity.objects.filter(
            symbol="BTC/USDT",
            opportunity_type="volume_surge",
            asset_class="crypto",
        )
        assert volume_surges.count() <= 1, (
            f"Expected at most 1 volume_surge for BTC/USDT, got {volume_surges.count()}"
        )


@pytest.mark.django_db
class TestOpportunityAssetClassFilter:
    """Test API filtering by asset_class on opportunities."""

    def test_filter_by_asset_class(self, authenticated_client):
        from django.utils import timezone

        now = timezone.now()
        expires = now + timedelta(hours=24)
        MarketOpportunity.objects.create(
            symbol="BTC/USDT", opportunity_type="breakout", asset_class="crypto",
            score=60, expires_at=expires,
        )
        MarketOpportunity.objects.create(
            symbol="EUR/USD", opportunity_type="breakout", asset_class="forex",
            score=70, expires_at=expires,
        )

        # All
        resp = authenticated_client.get("/api/market/opportunities/")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        # Forex only
        resp = authenticated_client.get("/api/market/opportunities/?asset_class=forex")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "EUR/USD"
        assert data[0]["asset_class"] == "forex"

        # Crypto only
        resp = authenticated_client.get("/api/market/opportunities/?asset_class=crypto")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "BTC/USDT"

    def test_summary_filter_by_asset_class(self, authenticated_client):
        from django.utils import timezone

        now = timezone.now()
        expires = now + timedelta(hours=24)
        MarketOpportunity.objects.create(
            symbol="BTC/USDT", opportunity_type="breakout", asset_class="crypto",
            score=60, expires_at=expires,
        )
        MarketOpportunity.objects.create(
            symbol="EUR/USD", opportunity_type="rsi_bounce", asset_class="forex",
            score=70, expires_at=expires,
        )
        MarketOpportunity.objects.create(
            symbol="GBP/USD", opportunity_type="breakout", asset_class="forex",
            score=80, expires_at=expires,
        )

        resp = authenticated_client.get("/api/market/opportunities/summary/?asset_class=forex")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_active"] == 2
