"""P6-2: Tests for transaction.atomic in risk service methods."""

from unittest.mock import patch

import pytest

from risk.models import AlertLog, RiskLimitChange, RiskLimits, RiskState
from risk.services.risk import RiskManagementService


@pytest.mark.django_db
class TestUpdateLimitsAtomic:
    def test_success(self):
        RiskLimits.objects.create(portfolio_id=1)
        result = RiskManagementService.update_limits(
            1, {"max_daily_loss": 0.10}, changed_by="test", reason="test"
        )
        assert result.max_daily_loss == 0.10
        assert RiskLimitChange.objects.filter(portfolio_id=1).count() == 1

    def test_rolls_back_on_error(self):
        RiskLimits.objects.create(portfolio_id=2, max_daily_loss=0.05)
        with (
            patch.object(RiskLimits, "save", side_effect=RuntimeError("DB error")),
            pytest.raises(RuntimeError),
        ):
            RiskManagementService.update_limits(
                2, {"max_daily_loss": 0.20}, changed_by="test"
            )
        # Change record should have been rolled back
        assert RiskLimitChange.objects.filter(portfolio_id=2).count() == 0
        # Original value unchanged
        assert RiskLimits.objects.get(portfolio_id=2).max_daily_loss == 0.05

    def test_multiple_changes_all_or_nothing(self):
        RiskLimits.objects.create(portfolio_id=3, max_daily_loss=0.05, max_leverage=1.0)

        def failing_save(self, *args, **kwargs):
            raise RuntimeError("Simulated failure")

        with (
            patch.object(RiskLimits, "save", failing_save),
            pytest.raises(RuntimeError),
        ):
            RiskManagementService.update_limits(
                3,
                {"max_daily_loss": 0.10, "max_leverage": 2.0},
                changed_by="test",
            )
        assert RiskLimitChange.objects.filter(portfolio_id=3).count() == 0

    def test_no_changes_no_records(self):
        RiskLimits.objects.create(portfolio_id=4, max_daily_loss=0.05)
        RiskManagementService.update_limits(
            4, {"max_daily_loss": 0.05}, changed_by="test"
        )
        assert RiskLimitChange.objects.filter(portfolio_id=4).count() == 0


@pytest.mark.django_db
class TestHaltTradingAtomic:
    def test_success(self):
        RiskState.objects.create(portfolio_id=10)
        result = RiskManagementService.halt_trading(10, "test halt")
        assert result["is_halted"] is True
        state = RiskState.objects.get(portfolio_id=10)
        assert state.is_halted is True
        assert AlertLog.objects.filter(
            portfolio_id=10, event_type="kill_switch_halt"
        ).exists()

    def test_rolls_back_on_error(self):
        RiskState.objects.create(portfolio_id=11, is_halted=False)
        with (
            patch.object(
                AlertLog.objects, "create", side_effect=RuntimeError("DB error")
            ),
            pytest.raises(RuntimeError),
        ):
            RiskManagementService.halt_trading(11, "failing halt")
        # State should not have changed
        state = RiskState.objects.get(portfolio_id=11)
        assert state.is_halted is False

    def test_creates_alert_log(self):
        RiskState.objects.create(portfolio_id=12)
        RiskManagementService.halt_trading(12, "drawdown breach")
        alert = AlertLog.objects.filter(portfolio_id=12).first()
        assert alert is not None
        assert "drawdown breach" in alert.message


@pytest.mark.django_db
class TestResumeTradingAtomic:
    def test_success(self):
        RiskState.objects.create(portfolio_id=20, is_halted=True, halt_reason="test")
        result = RiskManagementService.resume_trading(20)
        assert result["is_halted"] is False
        state = RiskState.objects.get(portfolio_id=20)
        assert state.is_halted is False
        assert AlertLog.objects.filter(
            portfolio_id=20, event_type="kill_switch_resume"
        ).exists()

    def test_rolls_back_on_error(self):
        RiskState.objects.create(portfolio_id=21, is_halted=True, halt_reason="stuck")
        with (
            patch.object(
                AlertLog.objects, "create", side_effect=RuntimeError("DB error")
            ),
            pytest.raises(RuntimeError),
        ):
            RiskManagementService.resume_trading(21)
        state = RiskState.objects.get(portfolio_id=21)
        assert state.is_halted is True

    def test_creates_alert_log(self):
        RiskState.objects.create(portfolio_id=22, is_halted=True)
        RiskManagementService.resume_trading(22)
        alert = AlertLog.objects.filter(
            portfolio_id=22, event_type="kill_switch_resume"
        ).first()
        assert alert is not None
        assert "RESUME" in alert.message
