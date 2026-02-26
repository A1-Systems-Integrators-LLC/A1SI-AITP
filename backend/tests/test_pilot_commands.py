"""Tests for pilot_preflight and pilot_status management commands."""

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from core.management.commands.pilot_preflight import (
    _check_data_freshness,
    _check_database,
    _check_disk_space,
    _check_exchange_config,
    _check_frameworks,
    _check_kill_switch,
    _check_notifications,
    _check_portfolio,
    _check_risk_limits,
    _check_scheduler,
)
from core.management.commands.pilot_status import (
    _compute_overall,
    _data_quality_section,
    _paper_trading_section,
    _regime_section,
    _risk_section,
    _system_health_section,
)

# ---------------------------------------------------------------------------
# TestPilotPreflight
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPilotPreflight:
    """Tests for the pilot_preflight management command."""

    def _create_portfolio(self, pk=1):
        from portfolio.models import Portfolio

        return Portfolio.objects.create(id=pk, name="Test Portfolio")

    def _create_risk_state(self, portfolio_id=1, is_halted=False, halt_reason=""):
        from risk.models import RiskState

        return RiskState.objects.create(
            portfolio_id=portfolio_id,
            is_halted=is_halted,
            halt_reason=halt_reason,
        )

    def _create_risk_limits(self, portfolio_id=1, **overrides):
        from risk.models import RiskLimits

        defaults = {
            "portfolio_id": portfolio_id,
            "max_portfolio_drawdown": 0.15,
            "max_daily_loss": 0.05,
            "max_leverage": 1.0,
        }
        defaults.update(overrides)
        return RiskLimits.objects.create(**defaults)

    def _create_scheduled_tasks(self):
        from core.models import ScheduledTask

        for task_id in ["risk_monitoring", "order_sync", "data_refresh_crypto"]:
            ScheduledTask.objects.create(
                id=task_id,
                name=task_id,
                task_type="interval",
                status=ScheduledTask.ACTIVE,
                interval_seconds=60,
            )

    def _setup_all_pass(self):
        """Set up DB state for an all-pass scenario."""
        self._create_portfolio()
        self._create_risk_state()
        self._create_risk_limits()
        self._create_scheduled_tasks()

    # -- Full command tests --

    @patch("core.management.commands.pilot_preflight._check_frameworks")
    @patch("core.management.commands.pilot_preflight._check_data_freshness")
    @patch("core.management.commands.pilot_preflight._check_disk_space")
    def test_all_pass_go(self, mock_disk, mock_data, mock_fw):
        """All checks pass -> GO, exit 0."""
        self._setup_all_pass()
        mock_fw.return_value = {"name": "Framework Validation", "status": "pass", "detail": "4/4"}
        mock_data.return_value = {"name": "Data Freshness", "status": "pass", "detail": "10 files"}
        mock_disk.return_value = {"name": "Disk Space", "status": "pass", "detail": "50 GB"}

        out = StringIO()
        call_command("pilot_preflight", stdout=out)
        output = out.getvalue()
        assert "GO" in output

    @patch("core.management.commands.pilot_preflight._check_frameworks")
    @patch("core.management.commands.pilot_preflight._check_data_freshness")
    @patch("core.management.commands.pilot_preflight._check_disk_space")
    def test_fail_exits_nonzero(self, mock_disk, mock_data, mock_fw):
        """Any fail -> NO-GO, exit 1."""
        self._setup_all_pass()
        mock_fw.return_value = {
            "name": "Framework Validation", "status": "fail", "detail": "CCXT missing",
        }
        mock_data.return_value = {"name": "Data Freshness", "status": "pass", "detail": "ok"}
        mock_disk.return_value = {"name": "Disk Space", "status": "pass", "detail": "50 GB"}

        out = StringIO()
        with pytest.raises(SystemExit) as exc_info:
            call_command("pilot_preflight", stdout=out)
        assert exc_info.value.code == 1

    @patch("core.management.commands.pilot_preflight._check_frameworks")
    @patch("core.management.commands.pilot_preflight._check_data_freshness")
    @patch("core.management.commands.pilot_preflight._check_disk_space")
    def test_json_output_format(self, mock_disk, mock_data, mock_fw):
        """--json flag produces valid JSON with expected structure."""
        self._setup_all_pass()
        mock_fw.return_value = {"name": "Framework Validation", "status": "pass", "detail": "4/4"}
        mock_data.return_value = {"name": "Data Freshness", "status": "pass", "detail": "ok"}
        mock_disk.return_value = {"name": "Disk Space", "status": "pass", "detail": "50 GB"}

        out = StringIO()
        call_command("pilot_preflight", "--json", stdout=out)
        data = json.loads(out.getvalue())
        assert "checks" in data
        assert "summary" in data
        assert data["summary"]["go"] is True
        assert len(data["checks"]) == 10

    @patch("core.management.commands.pilot_preflight._check_frameworks")
    @patch("core.management.commands.pilot_preflight._check_data_freshness")
    @patch("core.management.commands.pilot_preflight._check_disk_space")
    def test_custom_portfolio_id(self, mock_disk, mock_data, mock_fw):
        """--portfolio-id passes to portfolio-dependent checks."""
        self._create_portfolio(pk=42)
        self._create_risk_state(portfolio_id=42)
        self._create_risk_limits(portfolio_id=42)
        self._create_scheduled_tasks()
        mock_fw.return_value = {"name": "Framework Validation", "status": "pass", "detail": "ok"}
        mock_data.return_value = {"name": "Data Freshness", "status": "pass", "detail": "ok"}
        mock_disk.return_value = {"name": "Disk Space", "status": "pass", "detail": "50 GB"}

        out = StringIO()
        call_command("pilot_preflight", "--portfolio-id", "42", stdout=out)
        output = out.getvalue()
        assert "GO" in output

    # -- Individual check tests --

    def test_fail_on_missing_portfolio(self):
        result = _check_portfolio(999)
        assert result["status"] == "fail"
        assert "999" in result["detail"]

    def test_pass_portfolio(self):
        self._create_portfolio()
        result = _check_portfolio(1)
        assert result["status"] == "pass"

    def test_fail_on_missing_risk_limits(self):
        result = _check_risk_limits(999)
        assert result["status"] == "fail"

    def test_pass_risk_limits(self):
        self._create_risk_limits()
        result = _check_risk_limits(1)
        assert result["status"] == "pass"

    def test_warn_extreme_limits(self):
        self._create_risk_limits(max_portfolio_drawdown=0.60, max_daily_loss=0.25)
        result = _check_risk_limits(1)
        assert result["status"] == "warn"
        assert "Extreme" in result["detail"]

    def test_fail_on_no_risk_state(self):
        result = _check_kill_switch(999)
        assert result["status"] == "fail"

    def test_warn_on_halted(self):
        self._create_risk_state(is_halted=True, halt_reason="manual halt")
        result = _check_kill_switch(1)
        assert result["status"] == "warn"
        assert "halted" in result["detail"].lower()

    def test_pass_kill_switch(self):
        self._create_risk_state()
        result = _check_kill_switch(1)
        assert result["status"] == "pass"

    def test_database_integrity(self):
        result = _check_database()
        assert result["status"] == "pass"
        assert "integrity=ok" in result["detail"]

    @patch("core.management.commands.pilot_preflight.shutil.disk_usage")
    def test_fail_on_low_disk(self, mock_usage):
        mock_usage.return_value = MagicMock(free=500 * 1024**2)  # 500 MB
        result = _check_disk_space()
        assert result["status"] == "fail"

    @patch("core.management.commands.pilot_preflight.shutil.disk_usage")
    def test_warn_on_medium_disk(self, mock_usage):
        mock_usage.return_value = MagicMock(free=3 * 1024**3)  # 3 GB
        result = _check_disk_space()
        assert result["status"] == "warn"

    @patch("core.management.commands.pilot_preflight.shutil.disk_usage")
    def test_pass_on_plenty_disk(self, mock_usage):
        mock_usage.return_value = MagicMock(free=50 * 1024**3)  # 50 GB
        result = _check_disk_space()
        assert result["status"] == "pass"

    def test_warn_on_scheduler_down(self):
        self._create_scheduled_tasks()
        with patch("core.services.scheduler.get_scheduler") as mock_sched:
            mock_sched.return_value.running = False
            result = _check_scheduler()
        assert result["status"] == "warn"
        assert "not running" in result["detail"].lower()

    def test_fail_on_missing_scheduler_tasks(self):
        # No tasks in DB
        result = _check_scheduler()
        assert result["status"] == "fail"
        assert "Missing" in result["detail"]

    def test_warn_on_no_telegram(self):
        with patch("core.management.commands.pilot_preflight.settings") as mock_settings:
            mock_settings.TELEGRAM_BOT_TOKEN = ""
            mock_settings.TELEGRAM_CHAT_ID = ""
            result = _check_notifications()
        assert result["status"] == "warn"

    def test_pass_telegram_configured(self):
        with patch("core.management.commands.pilot_preflight.settings") as mock_settings:
            mock_settings.TELEGRAM_BOT_TOKEN = "123:ABC"
            mock_settings.TELEGRAM_CHAT_ID = "456"
            result = _check_notifications()
        assert result["status"] == "pass"

    def test_framework_all_installed(self):
        frameworks = [
            {"name": "VectorBT", "installed": True, "version": "0.25"},
            {"name": "Freqtrade", "installed": True, "version": "2024.1"},
            {"name": "NautilusTrader", "installed": True, "version": "1.180"},
            {"name": "HFT Backtest", "installed": True, "version": "configured"},
            {"name": "CCXT", "installed": True, "version": "4.0"},
        ]
        with patch("core.views._get_framework_status", return_value=frameworks):
            result = _check_frameworks()
        assert result["status"] == "pass"

    def test_framework_partial(self):
        frameworks = [
            {"name": "VectorBT", "installed": True, "version": "0.25"},
            {"name": "Freqtrade", "installed": False, "version": None},
            {"name": "NautilusTrader", "installed": True, "version": "1.180"},
            {"name": "HFT Backtest", "installed": False, "version": None},
            {"name": "CCXT", "installed": True, "version": "4.0"},
        ]
        with patch("core.views._get_framework_status", return_value=frameworks):
            result = _check_frameworks()
        assert result["status"] == "warn"
        assert "Freqtrade" in result["detail"]

    def test_framework_ccxt_missing(self):
        frameworks = [
            {"name": "VectorBT", "installed": True, "version": "0.25"},
            {"name": "Freqtrade", "installed": True, "version": "2024.1"},
            {"name": "NautilusTrader", "installed": True, "version": "1.180"},
            {"name": "HFT Backtest", "installed": True, "version": "configured"},
            {"name": "CCXT", "installed": False, "version": None},
        ]
        with patch("core.views._get_framework_status", return_value=frameworks):
            result = _check_frameworks()
        assert result["status"] == "fail"
        assert "CCXT" in result["detail"]

    def test_exchange_config_no_configs(self):
        result = _check_exchange_config()
        assert result["status"] == "warn"

    def test_exchange_config_open_breaker(self):
        from market.models import ExchangeConfig

        ExchangeConfig.objects.create(
            name="Test", exchange_id="binance", api_key="k", api_secret="s", is_active=True,
        )
        with patch(
            "market.services.circuit_breaker.get_all_breakers",
            return_value=[{"exchange_id": "binance", "state": "open"}],
        ):
            result = _check_exchange_config()
        assert result["status"] == "fail"
        assert "binance" in result["detail"]

    def test_data_freshness_stale_fail(self):
        """More than 50% stale -> fail."""
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        mock_report = MagicMock()
        mock_report.is_stale = True
        mock_path = "common.data_pipeline.pipeline.validate_all_data"
        with patch(mock_path, return_value=[mock_report] * 3):
            result = _check_data_freshness()
        assert result["status"] == "fail"

    def test_data_freshness_partial_warn(self):
        """Less than 50% stale -> warn."""
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        fresh = MagicMock()
        fresh.is_stale = False
        stale = MagicMock()
        stale.is_stale = True
        mock_path = "common.data_pipeline.pipeline.validate_all_data"
        with patch(mock_path, return_value=[fresh, fresh, stale]):
            result = _check_data_freshness()
        assert result["status"] == "warn"

    def test_data_freshness_no_files(self):
        """No data files -> fail."""
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        with patch("common.data_pipeline.pipeline.validate_all_data", return_value=[]):
            result = _check_data_freshness()
        assert result["status"] == "fail"
        assert "No data" in result["detail"]

    def test_exit_code_on_go(self):
        """Full pass produces exit 0 (no SystemExit)."""
        self._setup_all_pass()
        out = StringIO()
        with (
            patch("core.management.commands.pilot_preflight._check_frameworks",
                  return_value={"name": "FW", "status": "pass", "detail": "ok"}),
            patch("core.management.commands.pilot_preflight._check_data_freshness",
                  return_value={"name": "DF", "status": "pass", "detail": "ok"}),
            patch("core.management.commands.pilot_preflight._check_disk_space",
                  return_value={"name": "DS", "status": "pass", "detail": "ok"}),
        ):
            call_command("pilot_preflight", stdout=out)
        # If we get here, no SystemExit was raised — exit 0


# ---------------------------------------------------------------------------
# TestPilotStatus
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPilotStatus:
    """Tests for the pilot_status management command."""

    def _create_portfolio(self, pk=1):
        from portfolio.models import Portfolio

        return Portfolio.objects.create(id=pk, name="Test Portfolio")

    def _create_risk_state(self, portfolio_id=1, **kwargs):
        from risk.models import RiskState

        defaults = {"portfolio_id": portfolio_id, "is_halted": False, "halt_reason": ""}
        defaults.update(kwargs)
        return RiskState.objects.create(**defaults)

    # -- Section tests --

    def test_no_trades_zeros(self):
        """Paper trading section with no orders returns zero metrics."""
        self._create_portfolio()
        result = _paper_trading_section(1, "2020-01-01T00:00:00Z")
        assert result["total_trades"] == 0
        assert result["total_pnl"] == 0

    def test_paper_trades_metrics(self):
        """Paper trading section counts filled paper orders."""
        from trading.models import Order

        self._create_portfolio()
        Order.objects.create(
            exchange_id="binance", symbol="BTC/USDT", side="buy", order_type="market",
            amount=1.0, price=100.0, filled=1.0, avg_fill_price=100.0,
            status="filled", mode="paper", portfolio_id=1,
            timestamp="2026-02-20T00:00:00Z",
        )
        Order.objects.create(
            exchange_id="binance", symbol="BTC/USDT", side="sell", order_type="market",
            amount=1.0, price=110.0, filled=1.0, avg_fill_price=110.0,
            status="filled", mode="paper", portfolio_id=1,
            timestamp="2026-02-21T00:00:00Z",
        )
        result = _paper_trading_section(1, "2026-02-01T00:00:00Z")
        assert result["total_trades"] == 2
        assert result["total_pnl"] == 10.0

    def test_risk_section(self):
        """Risk section returns expected keys from RiskManagementService."""
        self._create_portfolio()
        self._create_risk_state()
        result = _risk_section(1)
        assert "equity" in result
        assert "drawdown" in result
        assert "is_halted" in result

    def test_system_health_section(self):
        """System health section returns scheduler, alerts, breakers."""
        self._create_portfolio()
        result = _system_health_section(1)
        assert "scheduler_running" in result
        assert "critical_alerts" in result
        assert "open_breakers" in result

    def test_data_quality_section_no_data(self):
        """Data quality graceful on missing pipeline module."""
        with patch(
            "core.platform_bridge.ensure_platform_imports",
            side_effect=ImportError("no module"),
        ):
            result = _data_quality_section()
        assert "error" in result

    def test_data_quality_section_ok(self):
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        report = MagicMock()
        report.is_stale = False
        report.gaps = []
        report.passed = True
        mock_path = "common.data_pipeline.pipeline.validate_all_data"
        with patch(mock_path, return_value=[report, report]):
            result = _data_quality_section()
        assert result["total_files"] == 2
        assert result["stale"] == 0

    def test_regime_section_import_error(self):
        """Regime section handles ImportError gracefully."""
        with patch(
            "core.platform_bridge.ensure_platform_imports",
            side_effect=ImportError("no regime"),
        ):
            result = _regime_section()
        assert result["regime"] == "unavailable"

    # -- Overall status logic --

    def _healthy_health(self, **overrides):
        base = {
            "open_breakers": [],
            "critical_alerts": 0,
            "warning_alerts": 0,
            "scheduler_running": True,
        }
        base.update(overrides)
        return base

    def test_halted_is_critical(self):
        risk = {"is_halted": True, "drawdown": 0.05}
        assert _compute_overall(risk, self._healthy_health()) == "critical"

    def test_open_breakers_critical(self):
        risk = {"is_halted": False, "drawdown": 0.05}
        health = self._healthy_health(open_breakers=["binance"])
        assert _compute_overall(risk, health) == "critical"

    def test_critical_alerts_critical(self):
        risk = {"is_halted": False, "drawdown": 0.05}
        health = self._healthy_health(critical_alerts=3)
        assert _compute_overall(risk, health) == "critical"

    def test_high_drawdown_warning(self):
        risk = {"is_halted": False, "drawdown": 0.12}
        assert _compute_overall(risk, self._healthy_health()) == "warning"

    def test_healthy_overall(self):
        risk = {"is_halted": False, "drawdown": 0.02}
        assert _compute_overall(risk, self._healthy_health()) == "healthy"

    # -- Full command tests --

    @patch("core.management.commands.pilot_status._regime_section")
    @patch("core.management.commands.pilot_status._data_quality_section")
    def test_json_output(self, mock_dq, mock_regime):
        """--json produces valid JSON with expected structure."""
        self._create_portfolio()
        self._create_risk_state()
        mock_dq.return_value = {"total_files": 5, "stale": 0, "gaps": 0, "passed": 5}
        mock_regime.return_value = {"regime": "ranging", "confidence": 0.7}

        out = StringIO()
        call_command("pilot_status", "--json", stdout=out)
        data = json.loads(out.getvalue())
        assert "overall_status" in data
        assert "paper_trading" in data
        assert "risk" in data
        assert "data_quality" in data
        assert "system_health" in data
        assert "regime" in data

    @patch("core.management.commands.pilot_status._regime_section")
    @patch("core.management.commands.pilot_status._data_quality_section")
    def test_custom_days(self, mock_dq, mock_regime):
        """--days parameter adjusts the lookback window."""
        self._create_portfolio()
        self._create_risk_state()
        mock_dq.return_value = {"total_files": 0, "stale": 0, "gaps": 0, "passed": 0}
        mock_regime.return_value = {"regime": "unknown"}

        out = StringIO()
        call_command("pilot_status", "--days", "14", "--json", stdout=out)
        data = json.loads(out.getvalue())
        assert data["days"] == 14

    @patch("core.management.commands.pilot_status._regime_section")
    @patch("core.management.commands.pilot_status._data_quality_section")
    def test_custom_portfolio(self, mock_dq, mock_regime):
        """--portfolio-id passes through to sections."""
        self._create_portfolio(pk=5)
        self._create_risk_state(portfolio_id=5)
        mock_dq.return_value = {"total_files": 0, "stale": 0, "gaps": 0, "passed": 0}
        mock_regime.return_value = {"regime": "unknown"}

        out = StringIO()
        call_command("pilot_status", "--portfolio-id", "5", "--json", stdout=out)
        data = json.loads(out.getvalue())
        assert data["portfolio_id"] == 5

    @patch("core.management.commands.pilot_status._regime_section")
    @patch("core.management.commands.pilot_status._data_quality_section")
    def test_halted_shows_critical(self, mock_dq, mock_regime):
        """Halted risk state produces critical overall status."""
        self._create_portfolio()
        self._create_risk_state(is_halted=True, halt_reason="drawdown breach")
        mock_dq.return_value = {"total_files": 0, "stale": 0, "gaps": 0, "passed": 0}
        mock_regime.return_value = {"regime": "unknown"}

        out = StringIO()
        call_command("pilot_status", "--json", stdout=out)
        data = json.loads(out.getvalue())
        assert data["overall_status"] == "critical"

    @patch("core.management.commands.pilot_status._regime_section")
    @patch("core.management.commands.pilot_status._data_quality_section")
    def test_text_output(self, mock_dq, mock_regime):
        """Default text output includes section headers."""
        self._create_portfolio()
        self._create_risk_state()
        mock_dq.return_value = {"total_files": 5, "stale": 0, "gaps": 0, "passed": 5}
        mock_regime.return_value = {"regime": "ranging", "confidence": 0.8, "adx": 22.5}

        out = StringIO()
        call_command("pilot_status", stdout=out)
        output = out.getvalue()
        assert "Paper Trading" in output
        assert "Risk Metrics" in output
        assert "Data Quality" in output
        assert "System Health" in output
        assert "Market Regime" in output
