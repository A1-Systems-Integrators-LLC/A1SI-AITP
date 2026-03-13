"""Comprehensive tests for Dashboard KPI aggregation (S17).

Covers:
- KPI aggregation across all sections (portfolio, trading, risk, platform, paper_trading)
- Partial failure isolation — one section fails, others still return data
- Asset class query param filtering
- Empty/no-data graceful defaults
- Paper trading widget in KPIs
- Framework status reporting
- Health check (simple + detailed)
- Dashboard API authentication
- Response structure validation
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone as dj_tz

from analysis.models import BackgroundJob
from core.services.dashboard import DashboardService
from portfolio.models import Holding, Portfolio
from risk.models import RiskState
from trading.models import Order, OrderStatus, TradingMode

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def user(db):
    return User.objects.create_user("dashuser", password="testpass123")


@pytest.fixture
def portfolio(db):
    return Portfolio.objects.create(name="ComprehensiveTest", exchange_id="kraken")


@pytest.fixture
def holdings(portfolio):
    return [
        Holding.objects.create(
            portfolio=portfolio,
            symbol="BTC/USDT",
            amount=0.5,
            avg_buy_price=60000,
        ),
        Holding.objects.create(
            portfolio=portfolio,
            symbol="ETH/USDT",
            amount=5.0,
            avg_buy_price=3000,
        ),
        Holding.objects.create(
            portfolio=portfolio,
            symbol="SOL/USDT",
            amount=50.0,
            avg_buy_price=120,
        ),
    ]


@pytest.fixture
def open_orders(portfolio):
    now = dj_tz.now()
    return [
        Order.objects.create(
            exchange_id="kraken",
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            amount=0.1,
            price=55000,
            status=OrderStatus.OPEN,
            mode=TradingMode.PAPER,
            portfolio_id=portfolio.id,
            timestamp=now,
        ),
        Order.objects.create(
            exchange_id="kraken",
            symbol="ETH/USDT",
            side="buy",
            order_type="limit",
            amount=1.0,
            price=2800,
            status=OrderStatus.SUBMITTED,
            mode=TradingMode.PAPER,
            portfolio_id=portfolio.id,
            timestamp=now,
        ),
    ]


@pytest.fixture
def filled_orders(portfolio):
    now = dj_tz.now()
    return [
        Order.objects.create(
            exchange_id="kraken",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount=1.0,
            filled=1.0,
            avg_fill_price=50000,
            status=OrderStatus.FILLED,
            mode=TradingMode.PAPER,
            portfolio_id=portfolio.id,
            timestamp=now,
        ),
        Order.objects.create(
            exchange_id="kraken",
            symbol="BTC/USDT",
            side="sell",
            order_type="market",
            amount=1.0,
            filled=1.0,
            avg_fill_price=55000,
            status=OrderStatus.FILLED,
            mode=TradingMode.PAPER,
            portfolio_id=portfolio.id,
            timestamp=now,
        ),
        Order.objects.create(
            exchange_id="kraken",
            symbol="ETH/USDT",
            side="buy",
            order_type="market",
            amount=10.0,
            filled=10.0,
            avg_fill_price=3000,
            status=OrderStatus.FILLED,
            mode=TradingMode.PAPER,
            portfolio_id=portfolio.id,
            timestamp=now,
        ),
    ]


@pytest.fixture
def risk_state(portfolio):
    return RiskState.objects.create(
        portfolio_id=portfolio.id,
        total_equity=9500,
        peak_equity=10000,
        daily_pnl=-200,
        is_halted=False,
    )


@pytest.fixture
def risk_state_halted(portfolio):
    return RiskState.objects.create(
        portfolio_id=portfolio.id,
        total_equity=7500,
        peak_equity=10000,
        daily_pnl=-500,
        is_halted=True,
        halt_reason="Max drawdown exceeded",
    )


@pytest.fixture
def background_jobs(db):
    return [
        BackgroundJob.objects.create(job_type="backtest", status="pending"),
        BackgroundJob.objects.create(job_type="data_download", status="running"),
        BackgroundJob.objects.create(job_type="screen", status="completed"),
    ]


# ── 1. KPI Aggregation — All Sections Present ────────────────


@pytest.mark.django_db
class TestKPIAggregationAllSections:
    def test_all_five_sections_present(self):
        """get_kpis() returns portfolio, trading, risk, platform, paper_trading."""
        kpis = DashboardService.get_kpis()
        for section in ("portfolio", "trading", "risk", "platform", "paper_trading"):
            assert section in kpis, f"Missing KPI section: {section}"

    def test_generated_at_is_valid_iso(self):
        """generated_at is a parseable ISO 8601 timestamp."""
        kpis = DashboardService.get_kpis()
        ts = kpis["generated_at"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.year >= 2026

    def test_portfolio_section_keys(self, portfolio, holdings):
        """Portfolio section includes count, total_value, total_cost, unrealized_pnl, pnl_pct."""
        kpis = DashboardService.get_kpis()
        p = kpis["portfolio"]
        for key in ("count", "total_value", "total_cost", "unrealized_pnl", "pnl_pct"):
            assert key in p, f"Missing portfolio key: {key}"

    def test_trading_section_keys(self, portfolio, filled_orders):
        """Trading section has required keys."""
        kpis = DashboardService.get_kpis()
        t = kpis["trading"]
        for key in ("total_trades", "win_rate", "total_pnl", "profit_factor", "open_orders"):
            assert key in t, f"Missing trading key: {key}"

    def test_risk_section_keys(self, portfolio, risk_state):
        """Risk section includes equity, drawdown, daily_pnl, is_halted, open_positions."""
        kpis = DashboardService.get_kpis()
        r = kpis["risk"]
        for key in ("equity", "drawdown", "daily_pnl", "is_halted", "open_positions"):
            assert key in r, f"Missing risk key: {key}"

    def test_platform_section_keys(self):
        """Platform section includes data_files, active_jobs, framework_count."""
        kpis = DashboardService.get_kpis()
        pl = kpis["platform"]
        for key in ("data_files", "active_jobs", "framework_count"):
            assert key in pl, f"Missing platform key: {key}"

    def test_paper_trading_section_keys(self):
        """Paper trading section includes all expected keys."""
        kpis = DashboardService.get_kpis()
        pt = kpis["paper_trading"]
        for key in (
            "instances_running",
            "total_pnl",
            "total_pnl_pct",
            "open_trades",
            "closed_trades",
            "win_rate",
            "instances",
        ):
            assert key in pt, f"Missing paper_trading key: {key}"


# ── 2. Partial Failure — Isolation ────────────────────────────


@pytest.mark.django_db
class TestPartialFailureIsolation:
    def test_portfolio_failure_does_not_break_other_sections(self, portfolio):
        """If portfolio analytics raises, trading/risk/platform still return data."""
        with patch(
            "portfolio.services.analytics.PortfolioAnalyticsService.get_portfolio_summary",
            side_effect=RuntimeError("DB lock"),
        ):
            kpis = DashboardService.get_kpis()
            # Portfolio should gracefully default
            assert kpis["portfolio"]["count"] == 0
            assert kpis["portfolio"]["total_value"] == 0.0
            # Other sections must still be present and not empty dicts
            assert "trading" in kpis
            assert "risk" in kpis
            assert "platform" in kpis
            assert kpis["platform"]["framework_count"] >= 0

    def test_trading_failure_does_not_break_other_sections(self, portfolio):
        """If TradingPerformanceService.get_summary raises, others survive."""
        with patch(
            "trading.services.performance.TradingPerformanceService.get_summary",
            side_effect=ValueError("corrupt data"),
        ):
            kpis = DashboardService.get_kpis()
            assert kpis["trading"]["total_trades"] == 0
            assert kpis["trading"]["win_rate"] == 0.0
            assert kpis["trading"]["open_orders"] == 0
            assert "portfolio" in kpis
            assert "risk" in kpis

    def test_risk_failure_does_not_break_other_sections(self, portfolio):
        """If RiskManagementService.get_status raises, others survive."""
        with patch(
            "risk.services.risk.RiskManagementService.get_status",
            side_effect=Exception("risk engine offline"),
        ):
            kpis = DashboardService.get_kpis()
            assert kpis["risk"]["equity"] == 0.0
            assert kpis["risk"]["is_halted"] is False
            assert "portfolio" in kpis
            assert "trading" in kpis

    def test_platform_failure_does_not_break_other_sections(self):
        """If filesystem/job query fails, others survive."""
        with patch(
            "core.services.dashboard.get_processed_dir",
            side_effect=OSError("permission denied"),
        ):
            kpis = DashboardService.get_kpis()
            assert kpis["platform"]["data_files"] == 0
            assert kpis["platform"]["active_jobs"] == 0
            assert "portfolio" in kpis

    def test_paper_trading_failure_does_not_break_other_sections(self):
        """If paper trading services fail to import, others survive."""
        with patch(
            "trading.views._get_paper_trading_services",
            side_effect=ImportError("freqtrade not available"),
        ):
            kpis = DashboardService.get_kpis()
            assert kpis["paper_trading"]["instances_running"] == 0
            assert "portfolio" in kpis
            assert "trading" in kpis


# ── 3. Asset Class Filter ────────────────────────────────────


@pytest.mark.django_db
class TestAssetClassFilter:
    def test_crypto_filter(self, portfolio, filled_orders):
        """asset_class='crypto' passes through without error."""
        kpis = DashboardService.get_kpis(asset_class="crypto")
        assert kpis["trading"]["total_trades"] >= 0

    def test_equity_filter(self, portfolio):
        """asset_class='equity' returns zero trades when no equity orders exist."""
        kpis = DashboardService.get_kpis(asset_class="equity")
        assert kpis["trading"]["total_trades"] == 0

    def test_forex_filter(self, portfolio):
        """asset_class='forex' returns zero trades when no forex orders exist."""
        kpis = DashboardService.get_kpis(asset_class="forex")
        assert kpis["trading"]["total_trades"] == 0

    def test_none_filter_returns_all(self, portfolio, filled_orders):
        """No asset_class filter returns all trades."""
        kpis = DashboardService.get_kpis(asset_class=None)
        assert kpis["trading"]["total_trades"] == 3


# ── 4. Empty Data — Graceful Defaults ─────────────────────────


@pytest.mark.django_db
class TestEmptyDataDefaults:
    def test_no_portfolios(self):
        """With no portfolios, all sections return zero/default values."""
        kpis = DashboardService.get_kpis()
        assert kpis["portfolio"]["count"] == 0
        assert kpis["portfolio"]["total_value"] == 0.0
        assert kpis["portfolio"]["total_cost"] == 0.0
        assert kpis["portfolio"]["unrealized_pnl"] == 0.0
        assert kpis["portfolio"]["pnl_pct"] == 0.0

    def test_no_orders(self, portfolio):
        """With portfolio but no orders, trading shows zeros."""
        kpis = DashboardService.get_kpis()
        assert kpis["trading"]["total_trades"] == 0
        assert kpis["trading"]["win_rate"] == 0.0
        assert kpis["trading"]["total_pnl"] == 0.0
        assert kpis["trading"]["open_orders"] == 0

    def test_no_risk_state(self, portfolio):
        """With portfolio but no risk state, risk returns defaults."""
        kpis = DashboardService.get_kpis()
        r = kpis["risk"]
        # RiskManagementService.get_status creates state via get_or_create
        assert r["is_halted"] is False
        assert isinstance(r["equity"], (int, float))

    def test_no_background_jobs(self):
        """With no background jobs, platform active_jobs is 0."""
        kpis = DashboardService.get_kpis()
        assert kpis["platform"]["active_jobs"] == 0


# ── 5. Paper Trading Widget ──────────────────────────────────


@pytest.mark.django_db
class TestPaperTradingWidget:
    def test_paper_trading_with_running_instance(self):
        """Running instance is counted and aggregated."""
        mock_svc = MagicMock()
        mock_svc.get_status.return_value = {"running": True, "strategy": "CryptoInvestorV1"}

        async def mock_profit():
            return {
                "profit_all_coin": 100.0,
                "profit_all_percent": 10.0,
                "trade_count": 5,
                "closed_trade_count": 3,
                "winning_trades": 2,
                "losing_trades": 1,
            }

        mock_svc.get_profit = mock_profit

        with patch("trading.views._get_paper_trading_services", return_value={"civ1": mock_svc}):
            pt = DashboardService._get_paper_trading_kpis()
            assert pt["instances_running"] == 1
            assert pt["total_pnl"] == 100.0
            assert pt["total_pnl_pct"] == 10.0
            assert pt["open_trades"] == 2  # 5 - 3
            assert pt["closed_trades"] == 3
            assert pt["win_rate"] == pytest.approx(66.7, abs=0.1)  # 2/3 * 100
            assert len(pt["instances"]) == 1
            assert pt["instances"][0]["name"] == "civ1"
            assert pt["instances"][0]["strategy"] == "CryptoInvestorV1"

    def test_paper_trading_instance_reports_not_running(self):
        """Stopped instance is listed but not counted as running."""
        mock_svc = MagicMock()
        mock_svc.get_status.return_value = {"running": False, "strategy": "BMR"}

        async def mock_profit():
            return {
                "profit_all_coin": 0,
                "profit_all_percent": 0,
                "trade_count": 0,
                "closed_trade_count": 0,
                "winning_trades": 0,
                "losing_trades": 0,
            }

        mock_svc.get_profit = mock_profit

        with patch("trading.views._get_paper_trading_services", return_value={"bmr": mock_svc}):
            pt = DashboardService._get_paper_trading_kpis()
            assert pt["instances_running"] == 0
            assert len(pt["instances"]) == 1
            assert pt["instances"][0]["running"] is False

    def test_paper_trading_in_full_kpis(self):
        """paper_trading section appears in full get_kpis() output."""
        with patch("trading.views._get_paper_trading_services", return_value={}):
            kpis = DashboardService.get_kpis()
            assert "paper_trading" in kpis
            assert kpis["paper_trading"]["instances_running"] == 0
            assert isinstance(kpis["paper_trading"]["instances"], list)


# ── 6. Framework Status ──────────────────────────────────────


@pytest.mark.django_db
class TestFrameworkStatus:
    def test_framework_list_returns_five(self):
        """_get_framework_status returns exactly 5 framework entries."""
        from core.views import _get_framework_status

        frameworks = _get_framework_status()
        assert len(frameworks) == 5

    def test_framework_names(self):
        """All 5 expected framework names are present."""
        from core.views import _get_framework_status

        frameworks = _get_framework_status()
        names = {fw["name"] for fw in frameworks}
        expected = {"VectorBT", "Freqtrade", "NautilusTrader", "HFT Backtest", "CCXT"}
        assert names == expected

    def test_framework_dict_structure(self):
        """Each framework dict has name, installed, version, status, status_label, details."""
        from core.views import _get_framework_status

        frameworks = _get_framework_status()
        for fw in frameworks:
            for key in ("name", "installed", "version", "status", "status_label", "details"):
                assert key in fw, f"Framework {fw.get('name', '?')} missing key: {key}"
            assert isinstance(fw["installed"], bool)
            assert fw["status"] in ("running", "idle", "not_installed")

    def test_platform_kpi_counts_installed_frameworks(self):
        """Platform KPI framework_count matches installed frameworks."""
        kpis = DashboardService.get_kpis()
        from core.views import _get_framework_status

        expected_count = sum(1 for fw in _get_framework_status() if fw["installed"])
        assert kpis["platform"]["framework_count"] == expected_count


# ── 7. Health Check ───────────────────────────────────────────


@pytest.mark.django_db
class TestHealthCheck:
    def test_simple_health_returns_ok(self, client):
        """GET /api/health/ returns {"status": "ok"}."""
        resp = client.get("/api/health/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_simple_health_no_auth_required(self, client):
        """Health check is accessible without authentication."""
        resp = client.get("/api/health/")
        assert resp.status_code == 200

    def test_detailed_health_returns_checks(self, client):
        """GET /api/health/?detailed=true returns subsystem checks."""
        resp = client.get("/api/health/?detailed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "checks" in data

    def test_detailed_health_includes_database(self, client):
        """Detailed health includes database check."""
        resp = client.get("/api/health/?detailed=true")
        checks = resp.json()["checks"]
        assert "database" in checks
        assert checks["database"]["status"] == "ok"

    def test_detailed_health_includes_disk(self, client):
        """Detailed health includes disk check with free_gb and writable."""
        resp = client.get("/api/health/?detailed=true")
        checks = resp.json()["checks"]
        assert "disk" in checks
        disk = checks["disk"]
        assert "free_gb" in disk
        assert "writable" in disk

    def test_detailed_health_includes_memory(self, client):
        """Detailed health includes memory check with rss_mb."""
        resp = client.get("/api/health/?detailed=true")
        checks = resp.json()["checks"]
        assert "memory" in checks
        assert "rss_mb" in checks["memory"]

    def test_detailed_health_includes_job_queue(self, client):
        """Detailed health includes job_queue check."""
        resp = client.get("/api/health/?detailed=true")
        checks = resp.json()["checks"]
        assert "job_queue" in checks

    def test_detailed_health_includes_wal(self, client):
        """Detailed health includes WAL size check."""
        resp = client.get("/api/health/?detailed=true")
        checks = resp.json()["checks"]
        assert "wal" in checks

    def test_detailed_health_all_subsystems(self, client):
        """All 7 subsystem keys are present in detailed health."""
        resp = client.get("/api/health/?detailed=true")
        checks = resp.json()["checks"]
        expected = {
            "database",
            "disk",
            "memory",
            "scheduler",
            "circuit_breakers",
            "channel_layer",
            "job_queue",
            "wal",
        }
        assert expected.issubset(set(checks.keys()))


# ── 8. Dashboard API Auth ─────────────────────────────────────


@pytest.mark.django_db
class TestDashboardAPIAuth:
    def test_kpi_requires_auth(self, client):
        """GET /api/dashboard/kpis/ without auth returns 401 or 403."""
        resp = client.get("/api/dashboard/kpis/")
        assert resp.status_code in (401, 403)

    def test_platform_status_requires_auth(self, client):
        """GET /api/platform/status/ without auth returns 401 or 403."""
        resp = client.get("/api/platform/status/")
        assert resp.status_code in (401, 403)

    def test_kpi_with_auth_returns_200(self, client, user):
        """GET /api/dashboard/kpis/ with auth returns 200."""
        client.force_login(user)
        resp = client.get("/api/dashboard/kpis/")
        assert resp.status_code == 200

    def test_platform_status_with_auth_returns_200(self, client, user):
        """GET /api/platform/status/ with auth returns 200."""
        client.force_login(user)
        resp = client.get("/api/platform/status/")
        assert resp.status_code == 200


# ── 9. Dashboard Response Structure ───────────────────────────


@pytest.mark.django_db
class TestDashboardResponseStructure:
    def test_kpi_response_top_level_keys(self, client, user):
        """KPI response has exactly the expected top-level keys."""
        client.force_login(user)
        resp = client.get("/api/dashboard/kpis/")
        data = resp.json()
        expected = {"portfolio", "trading", "risk", "platform", "paper_trading", "generated_at"}
        assert set(data.keys()) == expected

    def test_platform_status_response_keys(self, client, user):
        """Platform status response has frameworks, data_files, active_jobs."""
        client.force_login(user)
        resp = client.get("/api/platform/status/")
        data = resp.json()
        assert "frameworks" in data
        assert "data_files" in data
        assert "active_jobs" in data
        assert isinstance(data["frameworks"], list)

    def test_kpi_asset_class_param_via_api(self, client, user):
        """API passes asset_class query param to service."""
        client.force_login(user)
        resp = client.get("/api/dashboard/kpis/?asset_class=equity")
        assert resp.status_code == 200
        data = resp.json()
        # Should have all sections even with filter
        assert "portfolio" in data
        assert "trading" in data

    def test_kpi_numeric_types(self, client, user):
        """All numeric KPI values are int or float, not strings."""
        client.force_login(user)
        resp = client.get("/api/dashboard/kpis/")
        data = resp.json()
        p = data["portfolio"]
        assert isinstance(p["count"], int)
        assert isinstance(p["total_value"], (int, float))
        assert isinstance(p["unrealized_pnl"], (int, float))

        t = data["trading"]
        assert isinstance(t["total_trades"], int)
        assert isinstance(t["win_rate"], (int, float))
        assert isinstance(t["open_orders"], int)

    def test_risk_is_halted_is_boolean(self, client, user):
        """risk.is_halted is a boolean, not a string or int."""
        client.force_login(user)
        resp = client.get("/api/dashboard/kpis/")
        assert isinstance(resp.json()["risk"]["is_halted"], bool)


# ── 10. KPIs with Real Data ──────────────────────────────────


@pytest.mark.django_db
class TestKPIsWithRealData:
    def test_portfolio_count_matches_holdings(self, portfolio, holdings):
        """Portfolio count matches number of holdings."""
        kpis = DashboardService.get_kpis()
        assert kpis["portfolio"]["count"] == 3

    def test_trading_counts_filled_orders(self, portfolio, filled_orders):
        """Trading total_trades counts filled orders."""
        kpis = DashboardService.get_kpis()
        assert kpis["trading"]["total_trades"] == 3

    def test_open_orders_counted(self, portfolio, open_orders):
        """Open and submitted orders are counted in open_orders."""
        kpis = DashboardService.get_kpis()
        assert kpis["trading"]["open_orders"] == 2

    def test_risk_equity_from_state(self, portfolio, risk_state):
        """Risk equity reflects stored RiskState."""
        kpis = DashboardService.get_kpis()
        assert kpis["risk"]["equity"] == 9500

    def test_risk_halted_state(self, portfolio, risk_state_halted):
        """Risk is_halted=True is reflected in KPIs."""
        kpis = DashboardService.get_kpis()
        assert kpis["risk"]["is_halted"] is True

    def test_risk_drawdown_calculated(self, portfolio, risk_state):
        """Drawdown is calculated from equity vs peak."""
        kpis = DashboardService.get_kpis()
        expected = 1.0 - (9500 / 10000)  # 0.05
        assert kpis["risk"]["drawdown"] == pytest.approx(expected, abs=0.01)

    def test_active_jobs_counted(self, portfolio, background_jobs):
        """Platform counts pending+running jobs."""
        kpis = DashboardService.get_kpis()
        assert kpis["platform"]["active_jobs"] == 2  # pending + running
