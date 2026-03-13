"""Extended RiskManagementService tests — position sizing, VaR, heat check, halt/resume (P12-7)."""

from unittest.mock import patch

import pytest

from risk.models import RiskLimits, RiskState
from risk.services.risk import RiskManagementService


@pytest.fixture
def portfolio_state(db):
    """Create a portfolio with state and limits for testing."""
    state = RiskState.objects.create(
        portfolio_id=99,
        total_equity=100_000.0,
        peak_equity=100_000.0,
        daily_start_equity=100_000.0,
        daily_pnl=0.0,
        total_pnl=0.0,
        open_positions={},
        is_halted=False,
    )
    limits = RiskLimits.objects.create(
        portfolio_id=99,
        max_portfolio_drawdown=0.10,
        max_single_trade_risk=0.02,
        max_daily_loss=0.05,
        max_open_positions=10,
        max_position_size_pct=0.25,
    )
    return state, limits


@pytest.mark.django_db
class TestCalculatePositionSize:
    def test_normal_position_sizing(self, portfolio_state):
        result = RiskManagementService.calculate_position_size(
            portfolio_id=99,
            entry_price=50000.0,
            stop_loss_price=49000.0,
        )
        assert "size" in result
        assert "risk_amount" in result
        assert "position_value" in result
        assert result["size"] > 0
        assert result["risk_amount"] > 0

    def test_position_size_with_custom_risk(self, portfolio_state):
        result = RiskManagementService.calculate_position_size(
            portfolio_id=99,
            entry_price=50000.0,
            stop_loss_price=49000.0,
            risk_per_trade=0.01,
        )
        # 1% of 100k = 1000 risk
        assert result["risk_amount"] == 1000.0
        assert result["size"] > 0

    def test_position_size_with_drawdown(self, portfolio_state):
        state, _ = portfolio_state
        state.total_equity = 90_000.0  # 10% drawdown
        state.save()
        result = RiskManagementService.calculate_position_size(
            portfolio_id=99,
            entry_price=50000.0,
            stop_loss_price=49000.0,
        )
        assert result["size"] > 0
        # Smaller than full equity size
        assert result["risk_amount"] < 2000.0


@pytest.mark.django_db
class TestResetDaily:
    def test_reset_daily_clears_daily_loss(self, portfolio_state):
        state, _ = portfolio_state
        state.daily_pnl = -2000.0
        state.save()

        with patch.object(RiskManagementService, "send_notification"):
            result = RiskManagementService.reset_daily(99)

        assert result["daily_pnl"] == 0.0


@pytest.mark.django_db
class TestGetVar:
    def test_get_var_returns_structure(self, portfolio_state):
        result = RiskManagementService.get_var(99)
        assert "var_95" in result
        assert "var_99" in result
        assert "cvar_95" in result
        assert "cvar_99" in result
        assert "method" in result
        assert result["method"] == "parametric"


@pytest.mark.django_db
class TestGetHeatCheck:
    def test_heat_check_under_limit(self, portfolio_state):
        result = RiskManagementService.get_heat_check(99)
        # With 0 open positions, should be healthy
        assert "healthy" in result
        assert result["healthy"] is True

    def test_heat_check_with_positions(self, portfolio_state):
        state, _ = portfolio_state
        state.open_positions = {"BTC/USDT": {"size": 1.0, "entry": 50000, "value": 50000}}
        state.save()
        result = RiskManagementService.get_heat_check(99)
        assert result["open_positions"] == 1


@pytest.mark.django_db
class TestPeriodicRiskCheck:
    def test_periodic_check_80pct_warning(self, portfolio_state):
        state, limits = portfolio_state
        # Set drawdown at 8.5% with 10% limit = 85% of limit
        state.total_equity = 91_500.0
        state.peak_equity = 100_000.0
        state.save()

        with patch.object(RiskManagementService, "send_notification"):
            result = RiskManagementService.periodic_risk_check(99)

        assert result["status"] == "warning"
        assert "warning" in result

    def test_periodic_check_ok_within_limits(self, portfolio_state):
        with patch.object(RiskManagementService, "send_notification"):
            result = RiskManagementService.periodic_risk_check(99)

        assert result["status"] == "ok"
        assert result["portfolio_id"] == 99
