"""Tests for enhanced framework status with operational details."""

from unittest.mock import MagicMock, patch

import pytest

from core.views import (
    _get_ccxt_details,
    _get_framework_status,
    _get_freqtrade_details,
    _get_hft_details,
    _get_nautilus_details,
    _get_vectorbt_details,
)


class TestFrameworkStatusFields:
    """Verify all frameworks return status, status_label, and details fields."""

    def test_all_frameworks_have_status_field(self):
        frameworks = _get_framework_status()
        for fw in frameworks:
            assert "status" in fw, f"{fw['name']} missing 'status' field"
            assert fw["status"] in ("running", "idle", "not_installed")

    def test_all_frameworks_have_status_label(self):
        frameworks = _get_framework_status()
        for fw in frameworks:
            assert "status_label" in fw, f"{fw['name']} missing 'status_label'"
            assert isinstance(fw["status_label"], str)
            assert len(fw["status_label"]) > 0

    def test_all_frameworks_have_details_field(self):
        frameworks = _get_framework_status()
        for fw in frameworks:
            assert "details" in fw, f"{fw['name']} missing 'details' field"
            assert fw["details"] is None or isinstance(fw["details"], dict)

    def test_no_pandas_or_talib(self):
        frameworks = _get_framework_status()
        names = [fw["name"] for fw in frameworks]
        assert "Pandas" not in names
        assert "TA-Lib" not in names

    def test_exactly_five_frameworks(self):
        frameworks = _get_framework_status()
        assert len(frameworks) == 5
        names = [fw["name"] for fw in frameworks]
        assert set(names) == {"VectorBT", "Freqtrade", "NautilusTrader", "HFT Backtest", "CCXT"}

    def test_no_configured_status(self):
        frameworks = _get_framework_status()
        for fw in frameworks:
            assert fw["status"] != "configured", f"{fw['name']} has deprecated 'configured' status"

    def test_version_is_semver_or_null(self):
        """Version should be a real semver string or None, never 'installed'/'configured'."""
        import re

        semver_re = re.compile(r"^\d+\.\d+")
        frameworks = _get_framework_status()
        for fw in frameworks:
            if fw["version"] is not None:
                assert semver_re.match(fw["version"]), (
                    f"{fw['name']} version '{fw['version']}' is not semver"
                )


class TestFreqtradeDetails:
    """Freqtrade detail helper."""

    @patch("trading.views._get_paper_trading_services")
    def test_freqtrade_running_with_mock_instances(self, mock_services):
        mock_svc = MagicMock()
        mock_svc.get_status.return_value = {
            "running": True,
            "strategy": "CryptoInvestorV1",
            "started_at": "2026-03-04T10:00:00+00:00",
        }

        async def _open_trades():
            return [{"trade_id": 1}]

        mock_svc.get_open_trades = _open_trades
        mock_services.return_value = {"civ1": mock_svc}

        result = _get_freqtrade_details()
        assert result is not None
        assert result["_status"] == "running"
        assert result["instances_running"] == 1
        assert "CryptoInvestorV1" in result["strategies"]
        assert result["open_trades"] == 1
        assert result["_status_label"] == "1 instance \u00b7 1 open trade"

    @patch("trading.views._get_paper_trading_services")
    def test_freqtrade_idle_status_label(self, mock_services):
        mock_svc = MagicMock()
        mock_svc.get_status.return_value = {"running": False}
        mock_services.return_value = {"civ1": mock_svc}

        result = _get_freqtrade_details()
        assert result is not None
        assert result["_status"] == "idle"
        assert result["_status_label"] == "No instances running"

    @patch("trading.views._get_paper_trading_services", side_effect=Exception("unreachable"))
    def test_freqtrade_idle_when_unreachable(self, mock_services):
        result = _get_freqtrade_details()
        assert result is None


@pytest.mark.django_db
class TestVectorBTDetails:
    """VectorBT detail helper."""

    def test_vectorbt_details_with_screen_results(self):
        from analysis.models import BackgroundJob, ScreenResult

        job = BackgroundJob.objects.create(
            job_type="vbt_screen",
            status="completed",
        )
        ScreenResult.objects.create(
            job=job,
            symbol="BTC/USDT",
            timeframe="1d",
            strategy_name="sma_crossover",
        )
        ScreenResult.objects.create(
            job=job,
            symbol="ETH/USDT",
            timeframe="1d",
            strategy_name="rsi_oversold",
        )

        result = _get_vectorbt_details()
        assert result is not None
        assert result["screens_available"] == 2
        assert result["total_screens"] == 2
        assert result["last_screen_at"] is not None
        assert result["_status"] == "running"
        assert "2 screens" in result["_status_label"]
        assert "last run" in result["_status_label"]

    def test_vectorbt_empty_returns_idle(self):
        result = _get_vectorbt_details()
        assert result is not None
        assert result["_status"] == "idle"
        assert result["screens_available"] == 0
        assert result["_status_label"] == "No screens run yet"


@pytest.mark.django_db
class TestNautilusDetails:
    """NautilusTrader detail helper — result-based status detection."""

    def test_nautilus_empty_returns_idle_with_configured_label(self):
        result = _get_nautilus_details()
        assert result is not None
        assert result["_status"] == "idle"
        assert result["_status_label"] == "7 strategies configured"
        assert result["strategies_configured"] == 7
        assert result["total_backtests"] == 0
        assert result["asset_classes"] == ["crypto", "equity", "forex"]

    def test_nautilus_running_with_recent_results(self):
        from analysis.models import BackgroundJob, BacktestResult

        job = BackgroundJob.objects.create(job_type="backtest", status="completed")
        BacktestResult.objects.create(
            job=job,
            framework="nautilus",
            strategy_name="NautilusTrendFollowing",
            symbol="BTC/USDT",
            timeframe="1h",
        )
        BacktestResult.objects.create(
            job=job,
            framework="nautilus",
            strategy_name="NautilusMeanReversion",
            symbol="ETH/USDT",
            timeframe="1h",
        )

        result = _get_nautilus_details()
        assert result is not None
        assert result["_status"] == "running"
        assert result["strategies_run"] == 2
        assert result["total_backtests"] == 2
        assert result["last_run_at"] is not None
        assert "2 strategies" in result["_status_label"]
        assert "last run" in result["_status_label"]

    def test_nautilus_idle_with_old_results(self):
        from datetime import timedelta

        from django.utils import timezone

        from analysis.models import BackgroundJob, BacktestResult

        job = BackgroundJob.objects.create(job_type="backtest", status="completed")
        bt = BacktestResult.objects.create(
            job=job,
            framework="nautilus",
            strategy_name="NautilusTrendFollowing",
            symbol="BTC/USDT",
            timeframe="1h",
        )
        # Backdate to 2 days ago
        BacktestResult.objects.filter(pk=bt.pk).update(
            created_at=timezone.now() - timedelta(days=2),
        )

        result = _get_nautilus_details()
        assert result is not None
        assert result["_status"] == "idle"
        assert result["total_backtests"] == 1
        assert "1 strategies" in result["_status_label"]
        assert "1 results" in result["_status_label"]

    def test_nautilus_ignores_other_framework_results(self):
        from analysis.models import BackgroundJob, BacktestResult

        job = BackgroundJob.objects.create(job_type="backtest", status="completed")
        BacktestResult.objects.create(
            job=job,
            framework="freqtrade",
            strategy_name="CryptoInvestorV1",
            symbol="BTC/USDT",
            timeframe="1h",
        )

        result = _get_nautilus_details()
        assert result is not None
        assert result["_status"] == "idle"
        assert result["total_backtests"] == 0


@pytest.mark.django_db
class TestHFTDetails:
    """HFT Backtest detail helper — result-based status detection."""

    def test_hft_empty_returns_idle_with_configured_label(self):
        result = _get_hft_details()
        assert result is not None
        assert result["_status"] == "idle"
        assert result["_status_label"] == "4 strategies configured"
        assert result["strategies_configured"] == 4
        assert result["total_backtests"] == 0

    def test_hft_running_with_recent_results(self):
        from analysis.models import BackgroundJob, BacktestResult

        job = BackgroundJob.objects.create(job_type="backtest", status="completed")
        BacktestResult.objects.create(
            job=job,
            framework="hftbacktest",
            strategy_name="MarketMaker",
            symbol="BTC/USDT",
            timeframe="1h",
        )
        BacktestResult.objects.create(
            job=job,
            framework="hftbacktest",
            strategy_name="MomentumScalper",
            symbol="BTC/USDT",
            timeframe="1h",
        )

        result = _get_hft_details()
        assert result is not None
        assert result["_status"] == "running"
        assert result["strategies_run"] == 2
        assert result["total_backtests"] == 2
        assert "2 strategies" in result["_status_label"]
        assert "last run" in result["_status_label"]

    def test_hft_idle_with_old_results(self):
        from datetime import timedelta

        from django.utils import timezone

        from analysis.models import BackgroundJob, BacktestResult

        job = BackgroundJob.objects.create(job_type="backtest", status="completed")
        bt = BacktestResult.objects.create(
            job=job,
            framework="hftbacktest",
            strategy_name="GridTrader",
            symbol="BTC/USDT",
            timeframe="1h",
        )
        BacktestResult.objects.filter(pk=bt.pk).update(
            created_at=timezone.now() - timedelta(days=2),
        )

        result = _get_hft_details()
        assert result is not None
        assert result["_status"] == "idle"
        assert result["total_backtests"] == 1


class TestCCXTDetails:
    """CCXT detail helper."""

    @patch("market.services.exchange.ExchangeService")
    def test_ccxt_details_exchange_connected(self, mock_exchange_service):
        mock_svc = MagicMock()
        mock_exchange = MagicMock()

        async def _get_exchange():
            return mock_exchange

        async def _load_markets():
            return {}

        async def _close():
            pass

        mock_svc._get_exchange = _get_exchange
        mock_exchange.load_markets = _load_markets
        mock_svc.close = _close
        mock_exchange_service.return_value = mock_svc

        result = _get_ccxt_details()
        assert result is not None
        assert result["_status"] == "running"
        assert result["exchange"] == "kraken"
        assert result["connected"] is True
        assert isinstance(result["latency_ms"], float)
        assert "kraken" in result["_status_label"]
        assert "ms" in result["_status_label"]
