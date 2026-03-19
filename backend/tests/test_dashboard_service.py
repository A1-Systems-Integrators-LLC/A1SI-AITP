"""Tests for DashboardService — KPI aggregation service."""

from unittest.mock import MagicMock, patch

import pytest

from core.services.dashboard import DashboardService


@pytest.mark.django_db
class TestDashboardServiceGetKpis:
    def test_returns_all_sections_empty_db(self):
        kpis = DashboardService.get_kpis()
        assert "portfolio" in kpis
        assert "trading" in kpis
        assert "risk" in kpis
        assert "platform" in kpis
        assert "paper_trading" in kpis
        assert "generated_at" in kpis

    def test_empty_portfolio_defaults(self):
        kpis = DashboardService.get_kpis()
        assert kpis["portfolio"]["count"] == 0
        assert kpis["portfolio"]["total_value"] == 0.0
        assert kpis["portfolio"]["unrealized_pnl"] == 0.0

    def test_empty_trading_defaults(self):
        kpis = DashboardService.get_kpis()
        assert kpis["trading"]["total_trades"] == 0
        assert kpis["trading"]["open_orders"] == 0

    def test_empty_risk_defaults(self):
        kpis = DashboardService.get_kpis()
        assert kpis["risk"]["equity"] == 0.0
        assert kpis["risk"]["is_halted"] is False

    def test_asset_class_filter_passed_through(self):
        """asset_class param doesn't crash even with no data."""
        kpis = DashboardService.get_kpis(asset_class="crypto")
        assert kpis["portfolio"]["count"] == 0
        assert kpis["trading"]["total_trades"] == 0


@pytest.mark.django_db
class TestDashboardServicePartialFailures:
    def test_portfolio_failure_returns_defaults(self):
        with patch(
            "core.services.dashboard.DashboardService._get_portfolio_kpis",
            side_effect=Exception("db down"),
        ):
            # The top-level get_kpis calls _get_portfolio_kpis directly,
            # but _get_portfolio_kpis has its own try/except, so we need
            # to patch deeper.
            pass

        # Test via the internal method's own exception handling
        with patch(
            "portfolio.services.analytics.PortfolioAnalyticsService.get_portfolio_summary",
            side_effect=Exception("analytics exploded"),
        ):
            from portfolio.models import Portfolio

            Portfolio.objects.create(name="Test", exchange_id="binance")
            kpis = DashboardService.get_kpis()
            assert kpis["portfolio"]["count"] == 0
            assert kpis["portfolio"]["total_value"] == 0.0
            # Other sections still work
            assert "trading" in kpis
            assert "risk" in kpis

    def test_trading_failure_returns_defaults(self):
        with patch(
            "trading.services.performance.TradingPerformanceService.get_summary",
            side_effect=Exception("performance down"),
        ):
            from portfolio.models import Portfolio

            Portfolio.objects.create(name="Test2", exchange_id="binance")
            kpis = DashboardService.get_kpis()
            assert kpis["trading"]["total_trades"] == 0
            assert kpis["trading"]["win_rate"] == 0.0
            assert "portfolio" in kpis

    def test_risk_failure_returns_defaults(self):
        with patch(
            "risk.services.risk.RiskManagementService.get_status",
            side_effect=Exception("risk service down"),
        ):
            from portfolio.models import Portfolio

            Portfolio.objects.create(name="Test3", exchange_id="binance")
            kpis = DashboardService.get_kpis()
            assert kpis["risk"]["equity"] == 0.0
            assert kpis["risk"]["is_halted"] is False

    def test_platform_failure_returns_defaults(self):
        with patch(
            "core.services.dashboard.get_processed_dir",
            side_effect=Exception("filesystem error"),
        ):
            kpis = DashboardService.get_kpis()
            assert kpis["platform"]["data_files"] == 0
            assert kpis["platform"]["active_jobs"] == 0


@pytest.mark.django_db
class TestDashboardServicePaperTradingKpis:
    def test_paper_trading_defaults_when_no_services(self):
        """Paper trading KPIs return zeros when Freqtrade is not running (forex always present)."""
        with patch(
            "trading.views._get_paper_trading_services",
            return_value={},
        ):
            kpis = DashboardService.get_kpis()
            pt = kpis["paper_trading"]
            # Forex signals instance is always present and "running"
            assert pt["instances_running"] == 1
            assert pt["total_pnl"] == 0.0
            assert pt["total_pnl_pct"] == 0.0
            assert pt["open_trades"] == 0
            assert pt["closed_trades"] == 0
            assert pt["win_rate"] == 0.0
            assert isinstance(pt["instances"], list)
            # Forex instance included
            forex_inst = [i for i in pt["instances"] if i["name"] == "forex_signals"]
            assert len(forex_inst) == 1
            assert forex_inst[0]["strategy"] == "ForexSignals"

    def test_paper_trading_structure(self):
        """Paper trading KPIs have all expected keys."""
        pt = DashboardService._get_paper_trading_kpis()
        expected_keys = {
            "instances_running", "total_pnl", "total_pnl_pct",
            "open_trades", "closed_trades", "win_rate", "instances",
        }
        assert set(pt.keys()) == expected_keys

    def test_paper_trading_with_mock_services(self):
        """Paper trading KPIs aggregate data from multiple instances."""
        mock_svc = MagicMock()
        mock_svc.get_status.return_value = {
            "running": True,
            "strategy": "TestStrategy",
        }

        async def mock_profit():
            return {
                "profit_all_coin": 25.50,
                "profit_all_percent": 5.1,
                "trade_count": 3,
                "closed_trade_count": 2,
                "winning_trades": 1,
                "losing_trades": 1,
            }

        mock_svc.get_profit = mock_profit

        with patch(
            "trading.views._get_paper_trading_services",
            return_value={"civ1": mock_svc, "bmr": mock_svc},
        ):
            pt = DashboardService._get_paper_trading_kpis()
            assert pt["instances_running"] == 3  # 2 Freqtrade + 1 forex
            assert pt["total_pnl"] == 51.0  # 25.5 * 2 (forex has 0)
            assert pt["open_trades"] == 2  # (3-2) * 2
            assert pt["closed_trades"] == 4  # 2 * 2
            assert pt["win_rate"] == 50.0  # 2 wins / 4 total

    def test_paper_trading_failure_returns_defaults(self):
        """Paper trading KPIs gracefully handle import failures."""
        with patch(
            "trading.views._get_paper_trading_services",
            side_effect=ImportError("no module"),
        ):
            pt = DashboardService._get_paper_trading_kpis()
            assert pt["instances_running"] == 0
            assert pt["total_pnl"] == 0.0

    def test_paper_trading_instance_failure_isolated(self):
        """One failing instance doesn't break the whole aggregation."""
        good_svc = MagicMock()
        good_svc.get_status.return_value = {"running": True, "strategy": "Good"}

        async def good_profit():
            return {
                "profit_all_coin": 10.0,
                "profit_all_percent": 2.0,
                "trade_count": 1,
                "closed_trade_count": 1,
                "winning_trades": 1,
                "losing_trades": 0,
            }

        good_svc.get_profit = good_profit

        bad_svc = MagicMock()
        bad_svc.get_status.side_effect = Exception("connection refused")

        with patch(
            "trading.views._get_paper_trading_services",
            return_value={"good": good_svc, "bad": bad_svc},
        ):
            pt = DashboardService._get_paper_trading_kpis()
            assert pt["instances_running"] == 2  # 1 good Freqtrade + 1 forex
            assert pt["total_pnl"] == 10.0
            assert len(pt["instances"]) == 3  # good + bad + forex
            assert pt["instances"][0]["running"] is True
            assert pt["instances"][1]["running"] is False
