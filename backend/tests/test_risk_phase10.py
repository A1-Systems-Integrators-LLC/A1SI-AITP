"""Phase 10: 100% coverage for backend/risk/ — models, services/risk.py, views.py."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from django.core.exceptions import ValidationError

# ---------------------------------------------------------------------------
# models.py — __str__ and clean() branches
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRiskModelStr:
    """Cover __str__ methods on all risk models (lines 20, 55, 80, 115-116, 143)."""

    def test_risk_state_str(self):
        from risk.models import RiskState

        state = RiskState.objects.create(portfolio_id=99, total_equity=12345.0)
        assert "99" in str(state)
        assert "12345" in str(state)

    def test_risk_limits_str(self):
        from risk.models import RiskLimits

        limits = RiskLimits.objects.create(portfolio_id=42)
        assert "42" in str(limits)

    def test_risk_metric_history_str(self):
        from risk.models import RiskMetricHistory

        m = RiskMetricHistory.objects.create(portfolio_id=1, var_95=0.0321, equity=10000)
        s = str(m)
        assert "VaR95=0.0321" in s
        assert "portfolio=1" in s

    def test_trade_check_log_str_approved(self):
        from risk.models import TradeCheckLog

        log = TradeCheckLog.objects.create(
            portfolio_id=1,
            symbol="BTC/USDT",
            side="buy",
            size=0.5,
            entry_price=50000,
            approved=True,
            reason="OK",
        )
        s = str(log)
        assert "APPROVED" in s
        assert "BTC/USDT" in s

    def test_trade_check_log_str_rejected(self):
        from risk.models import TradeCheckLog

        log = TradeCheckLog.objects.create(
            portfolio_id=1,
            symbol="ETH/USDT",
            side="sell",
            size=1.0,
            entry_price=3000,
            approved=False,
            reason="Drawdown exceeded",
        )
        assert "REJECTED" in str(log)

    def test_alert_log_str(self):
        from risk.models import AlertLog

        alert = AlertLog.objects.create(
            portfolio_id=1,
            event_type="risk_warning",
            severity="warning",
            message="Drawdown at 80% of limit — be careful with new positions",
        )
        s = str(alert)
        assert "warning" in s
        assert "risk_warning" in s


@pytest.mark.django_db
class TestRiskLimitsCleanValidation:
    """Cover clean() branches for min_risk_reward and max_leverage (lines 46, 50)."""

    def test_negative_min_risk_reward(self):
        from risk.models import RiskLimits

        limits = RiskLimits(portfolio_id=1, min_risk_reward=-0.5)
        with pytest.raises(ValidationError) as exc_info:
            limits.clean()
        assert "min_risk_reward" in exc_info.value.message_dict

    def test_negative_max_leverage(self):
        from risk.models import RiskLimits

        limits = RiskLimits(portfolio_id=1, max_leverage=-1.0)
        with pytest.raises(ValidationError) as exc_info:
            limits.clean()
        assert "max_leverage" in exc_info.value.message_dict

    def test_both_negative(self):
        from risk.models import RiskLimits

        limits = RiskLimits(portfolio_id=1, min_risk_reward=-1, max_leverage=-2)
        with pytest.raises(ValidationError) as exc_info:
            limits.clean()
        errors = exc_info.value.message_dict
        assert "min_risk_reward" in errors
        assert "max_leverage" in errors


# ---------------------------------------------------------------------------
# services/risk.py — notification exception paths in periodic_risk_check
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPeriodicRiskCheckNotificationFailures:
    """Cover lines 310-311, 328-329 in risk.py."""

    def test_daily_loss_halt_notification_failure(self):
        """Line 310-311: send_notification raises during daily loss auto-halt."""
        from risk.models import RiskLimits, RiskState
        from risk.services.risk import RiskManagementService

        # Set up state with daily loss exceeding limit
        RiskState.objects.create(
            portfolio_id=50,
            total_equity=9000,
            peak_equity=10000,
            daily_start_equity=10000,
            daily_pnl=-600,  # 6.67% of equity, exceeds 5% default
        )
        RiskLimits.objects.create(portfolio_id=50, max_daily_loss=0.05)

        call_count = 0
        original_send = RiskManagementService.send_notification

        def fail_on_daily_halt(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Let record_metrics AlertLog pass, but fail the auto-halt notification
            if any("auto_halt" in str(a) for a in args) or any(
                "auto_halt" in str(v) for v in kwargs.values()
            ):
                raise RuntimeError("Telegram down")
            return original_send(*args, **kwargs)

        with patch.object(
            RiskManagementService, "send_notification", side_effect=fail_on_daily_halt,
        ):
            result = RiskManagementService.periodic_risk_check(50)

        assert result["status"] == "auto_halted"
        assert "Daily loss" in result["reason"]

    def test_risk_warning_notification_failure(self):
        """Lines 328-329: send_notification raises during 80% drawdown warning."""
        from risk.models import RiskLimits, RiskState
        from risk.services.risk import RiskManagementService

        # Set drawdown at 13% (>80% of 15% limit but <15% — triggers warning, not halt)
        equity = 8700
        peak = 10000
        RiskState.objects.create(
            portfolio_id=51,
            total_equity=equity,
            peak_equity=peak,
            daily_start_equity=equity,
            daily_pnl=0,
        )
        RiskLimits.objects.create(portfolio_id=51, max_portfolio_drawdown=0.15)

        def fail_on_warning(*args, **kwargs):
            if any("risk_warning" in str(a) for a in args) or any(
                "risk_warning" in str(v) for v in kwargs.values()
            ):
                raise RuntimeError("Telegram down")

        with patch.object(
            RiskManagementService, "send_notification", side_effect=fail_on_warning,
        ):
            result = RiskManagementService.periodic_risk_check(51)

        assert result["status"] == "warning"
        assert "warning" in result


# ---------------------------------------------------------------------------
# views.py — all uncovered view endpoints
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRiskViewsPhase10:
    """Cover all uncovered risk view lines."""

    def test_equity_update(self, authenticated_client):
        """Lines 68-71: EquityUpdateView.post."""
        resp = authenticated_client.post(
            "/api/risk/1/equity/", {"equity": 11000.0}, format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["equity"] == 11000.0

    def test_position_size(self, authenticated_client):
        """Lines 107-110: PositionSizeView.post."""
        resp = authenticated_client.post(
            "/api/risk/1/position-size/",
            {"entry_price": 50000, "stop_loss_price": 48000},
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "size" in data
        assert "risk_amount" in data
        assert "position_value" in data

    def test_position_size_with_custom_risk(self, authenticated_client):
        """Lines 107-110: PositionSizeView.post with risk_per_trade."""
        resp = authenticated_client.post(
            "/api/risk/1/position-size/",
            {"entry_price": 50000, "stop_loss_price": 48000, "risk_per_trade": 0.01},
            format="json",
        )
        assert resp.status_code == 200

    def test_reset_daily(self, authenticated_client):
        """Line 123: ResetDailyView.post."""
        resp = authenticated_client.post("/api/risk/1/reset-daily/")
        assert resp.status_code == 200
        assert "equity" in resp.json()

    def test_var_view(self, authenticated_client):
        """Lines 129-130: VaRView.get."""
        resp = authenticated_client.get("/api/risk/1/var/")
        assert resp.status_code == 200
        data = resp.json()
        assert "var_95" in data
        assert "method" in data

    def test_var_view_with_method(self, authenticated_client):
        """Lines 129-130: VaRView.get with method param."""
        resp = authenticated_client.get("/api/risk/1/var/?method=historical")
        assert resp.status_code == 200

    def test_heat_check(self, authenticated_client):
        """Line 136: HeatCheckView.get."""
        resp = authenticated_client.get("/api/risk/1/heat-check/")
        assert resp.status_code == 200

    def test_metric_history(self, authenticated_client):
        """Lines 142-144: MetricHistoryView.get."""
        resp = authenticated_client.get("/api/risk/1/metric-history/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_metric_history_with_hours(self, authenticated_client):
        """Lines 142-144: MetricHistoryView.get with hours param."""
        resp = authenticated_client.get("/api/risk/1/metric-history/?hours=24")
        assert resp.status_code == 200

    def test_record_metrics(self, authenticated_client):
        """Lines 150-152: RecordMetricsView.post."""
        resp = authenticated_client.post("/api/risk/1/record-metrics/")
        assert resp.status_code == 200
        data = resp.json()
        assert "var_95" in data

    def test_halt_trading_view(self, authenticated_client):
        """Lines 162-170: HaltTradingView.post (mocks async halt)."""
        mock_result = {
            "is_halted": True,
            "halt_reason": "Test halt",
            "cancelled_orders": 0,
            "message": "Trading halted: Test halt (0 orders cancelled)",
        }
        with patch(
            "risk.views.RiskManagementService.halt_trading_with_cancellation",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = authenticated_client.post(
                "/api/risk/1/halt/", {"reason": "Test halt"}, format="json",
            )
        assert resp.status_code == 200
        assert resp.json()["is_halted"] is True

    def test_resume_trading_view(self, authenticated_client):
        """Lines 176-179: ResumeTradingView.post (mocks async resume)."""
        mock_result = {
            "is_halted": False,
            "halt_reason": "",
            "message": "Trading resumed",
        }
        with patch(
            "risk.views.RiskManagementService.resume_trading_with_broadcast",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = authenticated_client.post("/api/risk/1/resume/")
        assert resp.status_code == 200
        assert resp.json()["is_halted"] is False

    def test_alert_list(self, authenticated_client):
        """Lines 199-208: AlertListView.get."""
        from risk.models import AlertLog

        AlertLog.objects.create(
            portfolio_id=1,
            event_type="test_alert",
            severity="info",
            message="Test alert",
        )
        resp = authenticated_client.get("/api/risk/1/alerts/")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_alert_list_with_filters(self, authenticated_client):
        """Lines 199-208: AlertListView.get with all filter params."""
        from risk.models import AlertLog

        AlertLog.objects.create(
            portfolio_id=1,
            event_type="risk_warning",
            severity="warning",
            message="Drawdown warning",
        )
        resp = authenticated_client.get(
            "/api/risk/1/alerts/?severity=warning&event_type=risk"
            "&created_after=2020-01-01T00:00:00Z&created_before=2030-01-01T00:00:00Z"
            "&limit=10",
        )
        assert resp.status_code == 200

    def test_trade_log(self, authenticated_client):
        """Lines 214-216: TradeLogView.get."""
        from risk.models import TradeCheckLog

        TradeCheckLog.objects.create(
            portfolio_id=1,
            symbol="BTC/USDT",
            side="buy",
            size=0.1,
            entry_price=50000,
            approved=True,
            reason="OK",
        )
        resp = authenticated_client.get("/api/risk/1/trade-log/")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_trade_log_with_limit(self, authenticated_client):
        """Lines 214-216: TradeLogView.get with limit param."""
        resp = authenticated_client.get("/api/risk/1/trade-log/?limit=5")
        assert resp.status_code == 200
