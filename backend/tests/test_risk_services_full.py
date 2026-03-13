"""Full coverage tests for backend/risk/services/risk.py (RiskManagementService).

Covers: get_status, get_limits, update_limits (no-change), update_equity, check_trade
(approved/rejected + notification failure), calculate_position_size, reset_daily,
get_var, get_heat_check, record_metrics, periodic_risk_check (all branches),
halt/resume (sync + async), send_notification (direct + rate-limited + failure),
get_alerts (all filters), get_trade_log, get_metric_history.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()


# ══════════════════════════════════════════════════════
# get_status
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGetStatus:
    def test_fresh_portfolio_defaults(self):
        from risk.services.risk import RiskManagementService
        result = RiskManagementService.get_status(9001)
        assert result["equity"] == 10000.0
        assert result["is_halted"] is False
        assert result["open_positions"] == 0

    def test_drawdown_computed(self):
        from risk.models import RiskState
        from risk.services.risk import RiskManagementService
        state, _ = RiskState.objects.get_or_create(portfolio_id=9002)
        state.total_equity = 8000.0
        state.peak_equity = 10000.0
        state.save()
        result = RiskManagementService.get_status(9002)
        assert result["drawdown"] == 0.2

    def test_zero_peak_no_division_error(self):
        from risk.models import RiskState
        from risk.services.risk import RiskManagementService
        state, _ = RiskState.objects.get_or_create(portfolio_id=9003)
        state.peak_equity = 0.0
        state.save()
        result = RiskManagementService.get_status(9003)
        # peak=0 → uses 1 as denominator
        assert "drawdown" in result


# ══════════════════════════════════════════════════════
# update_equity
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestUpdateEquity:
    def test_equity_update_persists(self):
        from risk.services.risk import RiskManagementService
        result = RiskManagementService.update_equity(9010, 12000.0)
        assert result["equity"] == 12000.0
        # Verify persistence
        result2 = RiskManagementService.get_status(9010)
        assert result2["equity"] == 12000.0

    def test_peak_equity_tracked(self):
        from risk.models import RiskState
        from risk.services.risk import RiskManagementService
        RiskManagementService.update_equity(9011, 15000.0)
        RiskManagementService.update_equity(9011, 13000.0)
        state = RiskState.objects.get(portfolio_id=9011)
        assert state.peak_equity == 15000.0
        assert state.total_equity == 13000.0


# ══════════════════════════════════════════════════════
# check_trade
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCheckTrade:
    def test_approved_trade_logged(self):
        from risk.models import TradeCheckLog
        from risk.services.risk import RiskManagementService
        approved, reason = RiskManagementService.check_trade(
            9020, "BTC/USDT", "buy", 0.001, 50000.0, 49000.0
        )
        assert approved is True
        log = TradeCheckLog.objects.filter(portfolio_id=9020).first()
        assert log is not None
        assert log.approved is True

    def test_rejected_trade_when_halted(self):
        from risk.models import RiskState
        from risk.services.risk import RiskManagementService
        state, _ = RiskState.objects.get_or_create(portfolio_id=9021)
        state.is_halted = True
        state.halt_reason = "test halt"
        state.save()
        with patch.object(RiskManagementService, "send_notification"):
            approved, reason = RiskManagementService.check_trade(
                9021, "BTC/USDT", "buy", 0.001, 50000.0, 49000.0
            )
        assert approved is False
        assert "halted" in reason.lower() or "halt" in reason.lower()

    def test_notification_failure_isolated(self):
        """Notification failure during rejection should not break check_trade."""
        from risk.models import RiskState
        from risk.services.risk import RiskManagementService
        state, _ = RiskState.objects.get_or_create(portfolio_id=9022)
        state.is_halted = True
        state.halt_reason = "test"
        state.save()
        with patch.object(
            RiskManagementService, "send_notification", side_effect=Exception("telegram down")
        ):
            approved, reason = RiskManagementService.check_trade(
                9022, "BTC/USDT", "buy", 0.001, 50000.0, 49000.0
            )
        assert approved is False  # Still returns result despite notification failure

    def test_no_stop_loss(self):
        from risk.services.risk import RiskManagementService
        approved, reason = RiskManagementService.check_trade(
            9023, "BTC/USDT", "buy", 0.001, 50000.0
        )
        assert isinstance(approved, bool)


# ══════════════════════════════════════════════════════
# calculate_position_size
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCalculatePositionSize:
    def test_returns_expected_keys(self):
        from risk.services.risk import RiskManagementService
        result = RiskManagementService.calculate_position_size(9030, 50000.0, 49000.0)
        assert "size" in result
        assert "risk_amount" in result
        assert "position_value" in result

    def test_custom_risk_per_trade(self):
        from risk.services.risk import RiskManagementService
        result = RiskManagementService.calculate_position_size(
            9031, 50000.0, 49000.0, risk_per_trade=0.005
        )
        assert result["risk_amount"] == round(10000.0 * 0.005, 2)


# ══════════════════════════════════════════════════════
# reset_daily
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestResetDaily:
    def test_resets_daily_pnl(self):
        from risk.models import RiskState
        from risk.services.risk import RiskManagementService
        # Set some daily PnL
        state, _ = RiskState.objects.get_or_create(portfolio_id=9040)
        state.daily_pnl = -500.0
        state.save()
        with patch.object(RiskManagementService, "send_notification"):
            result = RiskManagementService.reset_daily(9040)
        assert result["daily_pnl"] == 0.0

    def test_notification_failure_isolated(self):
        from risk.services.risk import RiskManagementService
        with patch.object(
            RiskManagementService, "send_notification", side_effect=Exception("fail")
        ):
            # Should not raise
            result = RiskManagementService.reset_daily(9041)
        assert isinstance(result, dict)


# ══════════════════════════════════════════════════════
# record_metrics
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRecordMetrics:
    def test_creates_metric_history(self):
        from risk.models import RiskMetricHistory
        from risk.services.risk import RiskManagementService
        metric = RiskManagementService.record_metrics(9050)
        assert isinstance(metric, RiskMetricHistory)
        assert metric.portfolio_id == 9050
        assert metric.equity == 10000.0

    def test_drawdown_recorded(self):
        from risk.models import RiskState
        from risk.services.risk import RiskManagementService
        state, _ = RiskState.objects.get_or_create(portfolio_id=9051)
        state.total_equity = 9000.0
        state.peak_equity = 10000.0
        state.save()
        metric = RiskManagementService.record_metrics(9051)
        assert metric.drawdown == 0.1


# ══════════════════════════════════════════════════════
# periodic_risk_check — all branches
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPeriodicRiskCheckBranches:
    def test_already_halted_skips(self):
        from risk.models import RiskState
        from risk.services.risk import RiskManagementService
        state, _ = RiskState.objects.get_or_create(portfolio_id=9060)
        state.is_halted = True
        state.halt_reason = "prev halt"
        state.save()
        result = RiskManagementService.periodic_risk_check(9060)
        assert result["status"] == "halted"

    def test_drawdown_breach_auto_halts(self):
        from risk.models import RiskLimits, RiskState
        from risk.services.risk import RiskManagementService
        state, _ = RiskState.objects.get_or_create(portfolio_id=9061)
        state.total_equity = 7000.0
        state.peak_equity = 10000.0
        state.save()
        limits, _ = RiskLimits.objects.get_or_create(portfolio_id=9061)
        limits.max_portfolio_drawdown = 0.15  # 30% DD exceeds 15%
        limits.save()
        with patch.object(RiskManagementService, "send_notification"):
            result = RiskManagementService.periodic_risk_check(9061)
        assert result["status"] == "auto_halted"
        # Verify state persisted
        state.refresh_from_db()
        assert state.is_halted is True

    def test_daily_loss_breach_auto_halts(self):
        from risk.models import RiskLimits, RiskState
        from risk.services.risk import RiskManagementService
        state, _ = RiskState.objects.get_or_create(portfolio_id=9062)
        state.total_equity = 10000.0
        state.peak_equity = 10000.0
        state.daily_pnl = -600.0  # 6% daily loss
        state.save()
        limits, _ = RiskLimits.objects.get_or_create(portfolio_id=9062)
        limits.max_daily_loss = 0.05  # 5% limit
        limits.max_portfolio_drawdown = 0.50  # High so DD doesn't trigger first
        limits.save()
        with patch.object(RiskManagementService, "send_notification"):
            result = RiskManagementService.periodic_risk_check(9062)
        assert result["status"] == "auto_halted"
        assert "daily" in result["reason"].lower()

    def test_80pct_warning(self):
        from risk.models import RiskLimits, RiskState
        from risk.services.risk import RiskManagementService
        state, _ = RiskState.objects.get_or_create(portfolio_id=9063)
        state.total_equity = 8800.0  # 12% DD
        state.peak_equity = 10000.0
        state.save()
        limits, _ = RiskLimits.objects.get_or_create(portfolio_id=9063)
        limits.max_portfolio_drawdown = 0.15  # 12% is 80% of 15%
        limits.max_daily_loss = 0.50  # High so daily loss doesn't trigger
        limits.save()
        with patch.object(RiskManagementService, "send_notification"):
            result = RiskManagementService.periodic_risk_check(9063)
        assert result["status"] == "warning"

    def test_healthy_within_limits(self):
        from risk.services.risk import RiskManagementService
        result = RiskManagementService.periodic_risk_check(9064)
        assert result["status"] == "ok"

    def test_metrics_failure_does_not_break_check(self):
        from risk.services.risk import RiskManagementService
        with patch.object(
            RiskManagementService, "record_metrics", side_effect=Exception("db error")
        ):
            result = RiskManagementService.periodic_risk_check(9065)
        assert result["status"] == "ok"

    def test_notification_failure_during_auto_halt_isolated(self):
        from risk.models import RiskLimits, RiskState
        from risk.services.risk import RiskManagementService
        state, _ = RiskState.objects.get_or_create(portfolio_id=9066)
        state.total_equity = 5000.0
        state.peak_equity = 10000.0
        state.save()
        limits, _ = RiskLimits.objects.get_or_create(portfolio_id=9066)
        limits.max_portfolio_drawdown = 0.15
        limits.save()
        with patch.object(
            RiskManagementService, "send_notification", side_effect=Exception("telegram fail")
        ):
            result = RiskManagementService.periodic_risk_check(9066)
        assert result["status"] == "auto_halted"

    def test_zero_equity_no_division_error(self):
        from risk.models import RiskState
        from risk.services.risk import RiskManagementService
        state, _ = RiskState.objects.get_or_create(portfolio_id=9067)
        state.total_equity = 0.0
        state.daily_pnl = -100.0
        state.save()
        result = RiskManagementService.periodic_risk_check(9067)
        assert isinstance(result, dict)


# ══════════════════════════════════════════════════════
# send_notification
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSendNotification:
    def test_creates_alert_log_entries(self):
        from risk.models import AlertLog
        from risk.services.risk import RiskManagementService
        with patch("core.services.notification.NotificationService.send_telegram_sync",
                    return_value=(True, "")):
            RiskManagementService.send_notification(9070, "test_event", "info", "test msg")
        alerts = AlertLog.objects.filter(portfolio_id=9070)
        assert alerts.count() == 2  # log + telegram

    def test_rate_limited_notification(self):
        from risk.services.risk import RiskManagementService
        with patch("core.services.notification.send_telegram_rate_limited",
                    return_value=(True, "")) as mock_rl:
            RiskManagementService.send_notification(
                9071, "test", "warning", "msg",
                telegram_rate_key="key1", telegram_cooldown=3600.0,
            )
        mock_rl.assert_called_once()

    def test_telegram_failure_still_creates_alert(self):
        from risk.models import AlertLog
        from risk.services.risk import RiskManagementService
        with patch("core.services.notification.NotificationService.send_telegram_sync",
                    return_value=(False, "connection refused")):
            RiskManagementService.send_notification(9072, "test", "warning", "msg")
        telegram_alert = AlertLog.objects.filter(
            portfolio_id=9072, channel="telegram"
        ).first()
        assert telegram_alert is not None
        assert telegram_alert.delivered is False
        assert "connection refused" in telegram_alert.error


# ══════════════════════════════════════════════════════
# get_alerts with filters
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGetAlerts:
    def _seed_alerts(self, portfolio_id):
        from risk.models import AlertLog
        AlertLog.objects.create(
            portfolio_id=portfolio_id, event_type="trade_rejected",
            severity="warning", message="rejected", channel="log", delivered=True, error="",
        )
        AlertLog.objects.create(
            portfolio_id=portfolio_id, event_type="risk_warning",
            severity="critical", message="danger", channel="log", delivered=True, error="",
        )
        AlertLog.objects.create(
            portfolio_id=portfolio_id, event_type="daily_reset",
            severity="info", message="reset", channel="log", delivered=True, error="",
        )

    def test_unfiltered(self):
        from risk.services.risk import RiskManagementService
        self._seed_alerts(9080)
        result = RiskManagementService.get_alerts(9080)
        assert len(result) == 3

    def test_filter_severity(self):
        from risk.services.risk import RiskManagementService
        self._seed_alerts(9081)
        result = RiskManagementService.get_alerts(9081, severity="critical")
        assert len(result) == 1
        assert result[0].severity == "critical"

    def test_filter_event_type(self):
        from risk.services.risk import RiskManagementService
        self._seed_alerts(9082)
        result = RiskManagementService.get_alerts(9082, event_type="trade")
        assert len(result) == 1

    def test_filter_date_range(self):
        from risk.services.risk import RiskManagementService
        self._seed_alerts(9083)
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        result = RiskManagementService.get_alerts(9083, created_after=past, created_before=future)
        assert len(result) == 3

    def test_limit(self):
        from risk.services.risk import RiskManagementService
        self._seed_alerts(9084)
        result = RiskManagementService.get_alerts(9084, limit=1)
        assert len(result) == 1


# ══════════════════════════════════════════════════════
# get_trade_log
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGetTradeLog:
    def test_returns_trade_check_logs(self):
        from risk.models import TradeCheckLog
        from risk.services.risk import RiskManagementService
        TradeCheckLog.objects.create(
            portfolio_id=9090, symbol="ETH/USDT", side="buy", size=0.5,
            entry_price=3000.0, approved=True, reason="ok",
            equity_at_check=10000.0, drawdown_at_check=0.0, open_positions_at_check=0,
        )
        result = RiskManagementService.get_trade_log(9090)
        assert len(result) == 1

    def test_limit_applied(self):
        from risk.models import TradeCheckLog
        from risk.services.risk import RiskManagementService
        for i in range(5):
            TradeCheckLog.objects.create(
                portfolio_id=9091, symbol=f"SYM{i}", side="buy", size=0.1,
                entry_price=100.0, approved=True, reason="ok",
                equity_at_check=10000.0, drawdown_at_check=0.0, open_positions_at_check=0,
            )
        result = RiskManagementService.get_trade_log(9091, limit=2)
        assert len(result) == 2


# ══════════════════════════════════════════════════════
# get_metric_history
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGetMetricHistory:
    def test_returns_recent_metrics(self):
        from risk.services.risk import RiskManagementService
        RiskManagementService.record_metrics(9100)
        result = RiskManagementService.get_metric_history(9100, hours=1)
        assert len(result) >= 1

    def test_old_metrics_excluded(self):
        from risk.models import RiskMetricHistory
        from risk.services.risk import RiskManagementService
        # Create an old metric
        m = RiskMetricHistory.objects.create(
            portfolio_id=9101, var_95=0.0, var_99=0.0, cvar_95=0.0, cvar_99=0.0,
            method="parametric", drawdown=0.0, equity=10000.0, open_positions_count=0,
        )
        # Backdate it
        RiskMetricHistory.objects.filter(pk=m.pk).update(
            recorded_at=datetime.now(timezone.utc) - timedelta(hours=200)
        )
        result = RiskManagementService.get_metric_history(9101, hours=1)
        assert len(result) == 0


# ══════════════════════════════════════════════════════
# halt/resume sync
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestHaltResume:
    def test_halt_creates_alert_log(self):
        from risk.models import AlertLog
        from risk.services.risk import RiskManagementService
        result = RiskManagementService.halt_trading(9110, "test reason")
        assert result["is_halted"] is True
        assert AlertLog.objects.filter(
            portfolio_id=9110, event_type="kill_switch_halt"
        ).exists()

    def test_resume_creates_alert_log(self):
        from risk.models import AlertLog
        from risk.services.risk import RiskManagementService
        RiskManagementService.halt_trading(9111, "halt first")
        result = RiskManagementService.resume_trading(9111)
        assert result["is_halted"] is False
        assert AlertLog.objects.filter(
            portfolio_id=9111, event_type="kill_switch_resume"
        ).exists()


# ══════════════════════════════════════════════════════
# halt_trading_with_cancellation (async)
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
@pytest.mark.asyncio
class TestHaltWithCancellationAsync:
    async def test_cancels_orders_and_broadcasts(self):
        from risk.services.risk import RiskManagementService
        with patch(
            "trading.services.live_trading.LiveTradingService.cancel_all_open_orders",
            new_callable=AsyncMock, return_value=3,
        ), patch("risk.services.risk.get_channel_layer") as mock_cl:
            mock_layer = MagicMock()
            mock_layer.group_send = AsyncMock()
            mock_cl.return_value = mock_layer
            with patch.object(RiskManagementService, "send_notification"):
                result = await RiskManagementService.halt_trading_with_cancellation(
                    9120, "emergency"
                )
        assert result["cancelled_orders"] == 3
        assert result["is_halted"] is True
        mock_layer.group_send.assert_called_once()

    async def test_notification_failure_isolated(self):
        from risk.services.risk import RiskManagementService
        with patch(
            "trading.services.live_trading.LiveTradingService.cancel_all_open_orders",
            new_callable=AsyncMock, return_value=0,
        ), patch("risk.services.risk.get_channel_layer", return_value=None):
            with patch.object(
                RiskManagementService, "send_notification", side_effect=Exception("fail")
            ):
                result = await RiskManagementService.halt_trading_with_cancellation(
                    9121, "reason"
                )
        assert result["is_halted"] is True


# ══════════════════════════════════════════════════════
# resume_trading_with_broadcast (async)
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
@pytest.mark.asyncio
class TestResumeWithBroadcastAsync:
    async def test_resumes_and_broadcasts(self):
        from asgiref.sync import sync_to_async
        from risk.services.risk import RiskManagementService
        # Halt first
        await sync_to_async(RiskManagementService.halt_trading)(9130, "halt first")
        with patch("risk.services.risk.get_channel_layer") as mock_cl:
            mock_layer = MagicMock()
            mock_layer.group_send = AsyncMock()
            mock_cl.return_value = mock_layer
            with patch.object(RiskManagementService, "send_notification"):
                result = await RiskManagementService.resume_trading_with_broadcast(9130)
        assert result["is_halted"] is False
        mock_layer.group_send.assert_called_once()

    async def test_notification_failure_isolated(self):
        from asgiref.sync import sync_to_async
        from risk.services.risk import RiskManagementService
        await sync_to_async(RiskManagementService.halt_trading)(9131, "halt")
        with patch("risk.services.risk.get_channel_layer", return_value=None):
            with patch.object(
                RiskManagementService, "send_notification", side_effect=Exception("fail")
            ):
                result = await RiskManagementService.resume_trading_with_broadcast(9131)
        assert result["is_halted"] is False


# ══════════════════════════════════════════════════════
# update_limits — no-change edge case
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestUpdateLimitsEdgeCases:
    def test_no_change_no_audit_record(self):
        from risk.models import RiskLimitChange
        from risk.services.risk import RiskManagementService
        limits = RiskManagementService.get_limits(9140)
        current_dd = limits.max_portfolio_drawdown
        # Update with same value
        RiskManagementService.update_limits(
            9140, {"max_portfolio_drawdown": current_dd}, changed_by="test"
        )
        changes = RiskLimitChange.objects.filter(portfolio_id=9140)
        assert changes.count() == 0

    def test_none_value_skipped(self):
        from risk.models import RiskLimitChange
        from risk.services.risk import RiskManagementService
        RiskManagementService.update_limits(
            9141, {"max_daily_loss": None}, changed_by="test"
        )
        changes = RiskLimitChange.objects.filter(portfolio_id=9141)
        assert changes.count() == 0

    def test_nonexistent_field_ignored(self):
        from risk.services.risk import RiskManagementService
        # Should not raise
        limits = RiskManagementService.update_limits(
            9142, {"nonexistent_field": 999}
        )
        assert limits is not None


# ══════════════════════════════════════════════════════
# get_var
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGetVar:
    def test_returns_expected_keys(self):
        from risk.services.risk import RiskManagementService
        result = RiskManagementService.get_var(9150)
        for key in ("var_95", "var_99", "cvar_95", "cvar_99", "method", "window_days"):
            assert key in result

    def test_historical_method(self):
        from risk.services.risk import RiskManagementService
        result = RiskManagementService.get_var(9151, method="historical")
        assert result["method"] == "historical"


# ══════════════════════════════════════════════════════
# get_heat_check
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGetHeatCheck:
    def test_returns_dict(self):
        from risk.services.risk import RiskManagementService
        result = RiskManagementService.get_heat_check(9160)
        assert isinstance(result, dict)
        assert "drawdown" in result
