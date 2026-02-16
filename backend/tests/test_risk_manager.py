"""
Tests for common.risk.risk_manager — Sprint 1, Item 1.1
=========================================================
Covers: RiskManager, ReturnTracker, VaR/CVaR, correlation checks,
portfolio heat check, position sizing, drawdown limits.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure project root is on sys.path for common.* imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.risk.risk_manager import (
    PortfolioState,
    ReturnTracker,
    RiskLimits,
    RiskManager,
    VaRResult,
)


# ── ReturnTracker Tests ──────────────────────────────────────────


class TestReturnTracker:
    def test_record_price_builds_returns(self):
        tracker = ReturnTracker()
        prices = [100, 105, 110, 108, 112]
        for p in prices:
            tracker.record_price("BTC/USDT", p)

        returns = tracker.get_returns("BTC/USDT")
        assert len(returns) == 4  # n-1 returns from n prices
        assert returns[0] == pytest.approx(0.05, abs=1e-6)  # 100->105

    def test_empty_returns_for_unknown_symbol(self):
        tracker = ReturnTracker()
        returns = tracker.get_returns("UNKNOWN")
        assert len(returns) == 0

    def test_correlation_matrix_requires_two_symbols(self):
        tracker = ReturnTracker()
        for p in [100, 105, 110, 108, 112]:
            tracker.record_price("BTC/USDT", p)

        corr = tracker.get_correlation_matrix()
        assert corr.empty  # only 1 symbol, need >= 2

    def test_correlation_matrix_two_symbols(self):
        tracker = ReturnTracker()
        np.random.seed(42)
        # Create correlated series
        base = np.cumsum(np.random.randn(30)) + 100
        noise = np.random.randn(30) * 0.5
        correlated = base + noise

        for b, c in zip(base, correlated):
            tracker.record_price("BTC/USDT", float(b))
            tracker.record_price("ETH/USDT", float(c))

        corr = tracker.get_correlation_matrix()
        assert not corr.empty
        assert "BTC/USDT" in corr.columns
        assert "ETH/USDT" in corr.columns
        # Highly correlated series
        assert corr.loc["BTC/USDT", "ETH/USDT"] > 0.5

    def test_correlation_requires_min_observations(self):
        tracker = ReturnTracker()
        # Only 5 prices = 4 returns, below the 20-minimum
        for p in [100, 105, 110, 108, 112]:
            tracker.record_price("BTC/USDT", p)
            tracker.record_price("ETH/USDT", p * 1.1)

        corr = tracker.get_correlation_matrix()
        assert corr.empty  # < 20 observations

    def test_tracked_symbols(self):
        tracker = ReturnTracker()
        tracker.record_price("BTC/USDT", 100)
        tracker.record_price("ETH/USDT", 200)
        assert set(tracker.tracked_symbols) == {"BTC/USDT", "ETH/USDT"}


class TestVaR:
    def _build_tracker_with_data(self, n=100):
        """Helper: build a tracker with enough data for VaR."""
        tracker = ReturnTracker()
        np.random.seed(42)
        btc_prices = np.cumsum(np.random.randn(n) * 0.01) + 50000
        eth_prices = np.cumsum(np.random.randn(n) * 0.015) + 3000

        for b, e in zip(btc_prices, eth_prices):
            tracker.record_price("BTC/USDT", float(b))
            tracker.record_price("ETH/USDT", float(e))
        return tracker

    def test_parametric_var(self):
        tracker = self._build_tracker_with_data()
        result = tracker.compute_var(
            {"BTC/USDT": 0.6, "ETH/USDT": 0.4},
            portfolio_value=10000,
            method="parametric",
        )
        assert isinstance(result, VaRResult)
        assert result.var_95 > 0
        assert result.var_99 > result.var_95  # 99% VaR > 95% VaR
        assert result.cvar_95 >= result.var_95  # CVaR >= VaR
        assert result.cvar_99 >= result.var_99
        assert result.method == "parametric"

    def test_historical_var(self):
        tracker = self._build_tracker_with_data()
        result = tracker.compute_var(
            {"BTC/USDT": 0.6, "ETH/USDT": 0.4},
            portfolio_value=10000,
            method="historical",
        )
        assert result.var_95 > 0
        assert result.var_99 >= result.var_95
        assert result.method == "historical"

    def test_var_empty_with_no_data(self):
        tracker = ReturnTracker()
        result = tracker.compute_var({"BTC/USDT": 1.0}, 10000)
        assert result.var_95 == 0.0
        assert result.var_99 == 0.0


# ── RiskManager Tests ────────────────────────────────────────────


class TestRiskManager:
    def test_basic_trade_approval(self):
        rm = RiskManager()
        # 0.01 BTC @ 50000 = $500 = 5% of $10k equity (under 20% limit)
        approved, reason = rm.check_new_trade("BTC/USDT", "buy", 0.01, 50000)
        assert approved is True
        assert reason == "approved"

    def test_halt_rejects_trades(self):
        rm = RiskManager()
        rm.state.is_halted = True
        rm.state.halt_reason = "Test halt"
        approved, reason = rm.check_new_trade("BTC/USDT", "buy", 0.1, 50000)
        assert approved is False
        assert "halted" in reason.lower()

    def test_max_positions_rejects(self):
        rm = RiskManager(RiskLimits(max_open_positions=2))
        rm.register_trade("BTC/USDT", "buy", 0.1, 50000)
        rm.register_trade("ETH/USDT", "buy", 1.0, 3000)
        approved, reason = rm.check_new_trade("SOL/USDT", "buy", 10, 100)
        assert approved is False
        assert "max open positions" in reason.lower()

    def test_duplicate_position_rejects(self):
        rm = RiskManager()
        rm.register_trade("BTC/USDT", "buy", 0.1, 50000)
        approved, reason = rm.check_new_trade("BTC/USDT", "buy", 0.1, 51000)
        assert approved is False
        assert "already have" in reason.lower()

    def test_oversized_position_rejects(self):
        rm = RiskManager(RiskLimits(max_position_size_pct=0.10))
        # 0.5 BTC @ 50000 = $25,000 = 250% of $10,000 equity
        approved, reason = rm.check_new_trade("BTC/USDT", "buy", 0.5, 50000)
        assert approved is False
        assert "too large" in reason.lower()

    def test_position_sizing(self):
        rm = RiskManager()  # 2% risk, $10,000 equity
        # Entry 50000, stop 49000 → $1000 risk per unit
        size = rm.calculate_position_size(50000, 49000)
        # Risk amount = $200 (2% of 10k), price risk = $1000
        # Uncapped size = 200 / 1000 = 0.2 BTC
        # But max position = 20% of $10k / $50k = 0.04 BTC
        assert size == pytest.approx(0.04, abs=0.001)

    def test_position_sizing_zero_risk(self):
        rm = RiskManager()
        size = rm.calculate_position_size(50000, 50000)
        assert size == 0.0

    def test_drawdown_halts_trading(self):
        rm = RiskManager(RiskLimits(max_portfolio_drawdown=0.10))
        rm.state.peak_equity = 10000
        result = rm.update_equity(8900)  # 11% drawdown
        assert result is False
        assert rm.state.is_halted is True

    def test_daily_loss_halts_trading(self):
        rm = RiskManager(RiskLimits(max_daily_loss=0.05))
        rm.state.daily_start_equity = 10000
        result = rm.update_equity(9400)  # 6% daily loss
        assert result is False
        assert rm.state.is_halted is True

    def test_reset_daily_clears_daily_halt(self):
        rm = RiskManager()
        rm.state.is_halted = True
        rm.state.halt_reason = "Daily loss limit breached: -6%"
        rm.reset_daily()
        assert rm.state.is_halted is False

    def test_close_trade_pnl(self):
        rm = RiskManager()
        rm.register_trade("BTC/USDT", "buy", 0.1, 50000)
        pnl = rm.close_trade("BTC/USDT", 55000)
        assert pnl == pytest.approx(500.0)  # 0.1 * (55000-50000)
        assert rm.state.total_pnl == pytest.approx(500.0)

    def test_close_trade_short_pnl(self):
        rm = RiskManager()
        rm.register_trade("BTC/USDT", "sell", 0.1, 50000)
        pnl = rm.close_trade("BTC/USDT", 48000)
        assert pnl == pytest.approx(200.0)  # 0.1 * (50000-48000)


class TestRiskRewardEnforcement:
    def test_risk_reward_rejects_wide_stop(self):
        """Stop at 12% → needs 18% profit for 1.5 R:R → rejected (>15%)."""
        # Use high max_single_trade_risk so stop-loss-wide check passes,
        # but R:R check still rejects (12% * 1.5 = 18% > 15%)
        rm = RiskManager(RiskLimits(max_single_trade_risk=0.10))
        approved, reason = rm.check_new_trade(
            "BTC/USDT", "buy", 0.01, 50000, stop_loss_price=44000
        )
        assert approved is False
        assert "risk/reward" in reason.lower()

    def test_risk_reward_allows_normal_stop(self):
        """Stop at 5% → needs 7.5% profit for 1.5 R:R → allowed (<15%)."""
        rm = RiskManager()
        # Entry 50000, stop at 47500 = 5% risk (passes max_single_trade_risk*2=4% check too)
        # But 5% > 4%, so this would be caught by stop-loss-wide check first.
        # Use 3% stop instead: entry 50000, stop at 48500
        # 3% * 1.5 = 4.5% required < 15% → approved
        approved, reason = rm.check_new_trade(
            "BTC/USDT", "buy", 0.01, 50000, stop_loss_price=48500
        )
        assert approved is True
        assert reason == "approved"

    def test_risk_reward_skipped_without_stop(self):
        """No stop_loss_price → R:R check skipped entirely."""
        rm = RiskManager()
        approved, reason = rm.check_new_trade(
            "BTC/USDT", "buy", 0.01, 50000, stop_loss_price=None
        )
        assert approved is True
        assert reason == "approved"


class TestRegimeModifier:
    def test_regime_modifier_reduces_size(self):
        rm = RiskManager()
        full_size = rm.calculate_position_size(50000, 49000)
        half_size = rm.calculate_position_size(50000, 49000, regime_modifier=0.5)
        assert half_size == pytest.approx(full_size * 0.5, rel=1e-6)

    def test_regime_modifier_none_no_change(self):
        rm = RiskManager()
        size_none = rm.calculate_position_size(50000, 49000, regime_modifier=None)
        size_default = rm.calculate_position_size(50000, 49000)
        assert size_none == pytest.approx(size_default, rel=1e-6)

    def test_regime_modifier_zero_returns_zero(self):
        rm = RiskManager()
        size = rm.calculate_position_size(50000, 49000, regime_modifier=0.0)
        assert size == 0.0

    def test_regime_modifier_one_no_change(self):
        rm = RiskManager()
        size_one = rm.calculate_position_size(50000, 49000, regime_modifier=1.0)
        size_default = rm.calculate_position_size(50000, 49000)
        assert size_one == pytest.approx(size_default, rel=1e-6)

    def test_regime_modifier_applied_after_cap(self):
        """Modifier should be applied after max position cap, not before."""
        rm = RiskManager()
        # This will hit the max position cap
        capped_size = rm.calculate_position_size(50000, 49000)
        modified_size = rm.calculate_position_size(50000, 49000, regime_modifier=0.5)
        # Modified size should be exactly 50% of capped size
        assert modified_size == pytest.approx(capped_size * 0.5, rel=1e-6)


class TestCorrelationCheck:
    def _rm_with_correlated_data(self):
        """Build a RiskManager with correlated price data for BTC and ETH."""
        rm = RiskManager(RiskLimits(max_correlation=0.70))
        np.random.seed(42)
        # Generate correlated price series with shared noise
        shared_noise = np.random.randn(50)
        btc_prices = 50000 + np.cumsum(shared_noise * 100)
        # ETH follows BTC closely (same direction) + tiny independent noise
        eth_prices = 3000 + np.cumsum(shared_noise * 6 + np.random.randn(50) * 0.3)
        # SOL is fully independent
        sol_prices = 100 + np.cumsum(np.random.randn(50) * 2)

        for b, e, s in zip(btc_prices, eth_prices, sol_prices):
            rm.return_tracker.record_price("BTC/USDT", float(b))
            rm.return_tracker.record_price("ETH/USDT", float(e))
            rm.return_tracker.record_price("SOL/USDT", float(s))
        return rm

    def test_high_correlation_blocks_trade(self):
        rm = self._rm_with_correlated_data()
        rm.register_trade("BTC/USDT", "buy", 0.01, 50000)
        # 0.1 ETH @ 3000 = $300 = 3% of equity (under position limit)
        approved, reason = rm.check_new_trade("ETH/USDT", "buy", 0.1, 3000)
        assert approved is False
        assert "correlation" in reason.lower()

    def test_low_correlation_allows_trade(self):
        rm = self._rm_with_correlated_data()
        rm.register_trade("BTC/USDT", "buy", 0.01, 50000)
        # 10 SOL @ 100 = $1000 = 10% (under 20% limit)
        approved, reason = rm.check_new_trade("SOL/USDT", "buy", 10, 100)
        assert approved is True

    def test_no_data_allows_trade_with_warning(self):
        rm = RiskManager(RiskLimits(max_correlation=0.70))
        rm.register_trade("BTC/USDT", "buy", 0.01, 50000)
        # No return data recorded — should allow with insufficient data
        # 0.1 ETH @ 3000 = $300 = 3% of equity
        approved, reason = rm.check_new_trade("ETH/USDT", "buy", 0.1, 3000)
        assert approved is True


class TestPortfolioHeatCheck:
    def test_healthy_portfolio(self):
        rm = RiskManager()
        heat = rm.portfolio_heat_check()
        assert heat["healthy"] is True
        assert heat["open_positions"] == 0

    def test_heat_check_with_positions(self):
        rm = RiskManager()
        np.random.seed(42)
        for p in np.cumsum(np.random.randn(30)) + 50000:
            rm.return_tracker.record_price("BTC/USDT", float(p))

        rm.register_trade("BTC/USDT", "buy", 0.1, 50000)
        heat = rm.portfolio_heat_check()
        assert heat["open_positions"] == 1
        assert "BTC/USDT" in heat["position_weights"]

    def test_heat_check_flags_halt(self):
        rm = RiskManager()
        rm.state.is_halted = True
        rm.state.halt_reason = "Test"
        heat = rm.portfolio_heat_check()
        assert heat["healthy"] is False
        assert any("HALTED" in issue for issue in heat["issues"])

    def test_get_var_no_positions(self):
        rm = RiskManager()
        var = rm.get_var()
        assert var.var_95 == 0.0
        assert var.var_99 == 0.0


# ── API Endpoint Schema Tests ──────────────────────────────────


class TestVaREndpointSchemas:
    def test_var_parametric_returns_valid_structure(self):
        """Verify VaR endpoint returns valid structure for parametric method."""
        rm = RiskManager()
        np.random.seed(42)
        for p in np.cumsum(np.random.randn(100) * 0.01) + 50000:
            rm.return_tracker.record_price("BTC/USDT", float(p))
        rm.register_trade("BTC/USDT", "buy", 0.1, 50000)

        result = rm.get_var("parametric")
        assert isinstance(result.var_95, float)
        assert isinstance(result.var_99, float)
        assert isinstance(result.cvar_95, float)
        assert isinstance(result.cvar_99, float)
        assert result.method == "parametric"
        assert result.window_days > 0

    def test_var_historical_returns_valid_structure(self):
        """Verify VaR endpoint returns valid structure for historical method."""
        rm = RiskManager()
        np.random.seed(42)
        btc_prices = np.cumsum(np.random.randn(100) * 500) + 50000
        eth_prices = np.cumsum(np.random.randn(100) * 30) + 3000
        for b, e in zip(btc_prices, eth_prices):
            rm.return_tracker.record_price("BTC/USDT", float(b))
            rm.return_tracker.record_price("ETH/USDT", float(e))
        rm.register_trade("BTC/USDT", "buy", 0.1, 50000)
        rm.register_trade("ETH/USDT", "buy", 1.0, 3000)

        result = rm.get_var("historical")
        assert isinstance(result.var_95, float)
        assert isinstance(result.var_99, float)
        assert result.method == "historical"
        assert result.var_95 > 0

    def test_heat_check_returns_complete_structure(self):
        """Verify heat check returns all expected fields."""
        rm = RiskManager()
        np.random.seed(42)
        for p in np.cumsum(np.random.randn(30)) + 50000:
            rm.return_tracker.record_price("BTC/USDT", float(p))
        rm.register_trade("BTC/USDT", "buy", 0.1, 50000)

        heat = rm.portfolio_heat_check()
        required_keys = [
            "healthy", "issues", "drawdown", "daily_pnl",
            "open_positions", "max_correlation", "high_corr_pairs",
            "max_concentration", "position_weights",
            "var_95", "var_99", "cvar_95", "cvar_99", "is_halted",
        ]
        for key in required_keys:
            assert key in heat, f"Missing key: {key}"

    def test_heat_check_healthy_when_no_issues(self):
        """Verify healthy=True when no risk issues present."""
        rm = RiskManager()
        heat = rm.portfolio_heat_check()
        assert heat["healthy"] is True
        assert len(heat["issues"]) == 0
        assert heat["is_halted"] is False


# ── Risk Metric History Schema Tests ──────────────────────────────


class TestRiskMetricHistorySchemas:
    def test_metric_history_model_fields(self):
        """Verify RiskMetricHistory model has all required columns."""
        from app.models.risk import RiskMetricHistory

        mapper = RiskMetricHistory.__mapper__
        column_names = {c.key for c in mapper.column_attrs}
        required = {
            "id", "portfolio_id", "var_95", "var_99", "cvar_95", "cvar_99",
            "method", "drawdown", "equity", "open_positions_count", "recorded_at",
        }
        assert required.issubset(column_names)

    def test_metric_history_table_name(self):
        """Verify the table name is correct."""
        from app.models.risk import RiskMetricHistory

        assert RiskMetricHistory.__tablename__ == "risk_metric_history"

    def test_metric_history_schema_serializes(self):
        """Verify the Pydantic read schema accepts valid data."""
        from app.schemas.risk import RiskMetricHistoryRead

        data = RiskMetricHistoryRead(
            id=1,
            portfolio_id=1,
            var_95=250.50,
            var_99=420.75,
            cvar_95=310.20,
            cvar_99=530.40,
            method="parametric",
            drawdown=0.02,
            equity=10000.0,
            open_positions_count=2,
            recorded_at="2026-02-15T12:00:00Z",
        )
        assert data.var_95 == 250.50
        assert data.method == "parametric"


# ── Trade Check Log Schema Tests ──────────────────────────────────


class TestTradeCheckLogSchemas:
    def test_trade_check_log_model_fields(self):
        """Verify TradeCheckLog model has all required columns."""
        from app.models.risk import TradeCheckLog

        mapper = TradeCheckLog.__mapper__
        column_names = {c.key for c in mapper.column_attrs}
        required = {
            "id", "portfolio_id", "symbol", "side", "size", "entry_price",
            "stop_loss_price", "approved", "reason", "equity_at_check",
            "drawdown_at_check", "open_positions_at_check", "checked_at",
        }
        assert required.issubset(column_names)

    def test_trade_check_log_table_name(self):
        """Verify the table name is correct."""
        from app.models.risk import TradeCheckLog

        assert TradeCheckLog.__tablename__ == "trade_check_log"

    def test_trade_check_log_schema_serializes(self):
        """Verify the Pydantic read schema accepts valid data."""
        from app.schemas.risk import TradeCheckLogRead

        data = TradeCheckLogRead(
            id=1,
            portfolio_id=1,
            symbol="BTC/USDT",
            side="buy",
            size=0.1,
            entry_price=50000.0,
            stop_loss_price=48000.0,
            approved=True,
            reason="approved",
            equity_at_check=10000.0,
            drawdown_at_check=0.02,
            open_positions_at_check=0,
            checked_at="2026-02-15T12:00:00Z",
        )
        assert data.approved is True
        assert data.symbol == "BTC/USDT"

    def test_trade_check_log_schema_nullable_stop_loss(self):
        """Verify stop_loss_price can be None."""
        from app.schemas.risk import TradeCheckLogRead

        data = TradeCheckLogRead(
            id=2,
            portfolio_id=1,
            symbol="ETH/USDT",
            side="buy",
            size=1.0,
            entry_price=3000.0,
            stop_loss_price=None,
            approved=False,
            reason="Max open positions reached (10)",
            equity_at_check=10000.0,
            drawdown_at_check=0.0,
            open_positions_at_check=10,
            checked_at="2026-02-15T12:00:00Z",
        )
        assert data.stop_loss_price is None
        assert data.approved is False
