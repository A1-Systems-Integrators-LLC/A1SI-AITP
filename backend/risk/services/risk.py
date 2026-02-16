"""
Risk management service — wraps common.risk.risk_manager with Django ORM persistence.
"""

import logging
from datetime import datetime, timedelta, timezone

from core.platform_bridge import ensure_platform_imports
from core.services.notification import NotificationService
from risk.models import AlertLog, RiskLimits, RiskMetricHistory, RiskState, TradeCheckLog

logger = logging.getLogger("risk_service")


class RiskManagementService:
    """Stateless service — all methods are classmethods using Django ORM."""

    @staticmethod
    def _get_or_create_state(portfolio_id: int) -> RiskState:
        state, _ = RiskState.objects.get_or_create(portfolio_id=portfolio_id)
        return state

    @staticmethod
    def _get_or_create_limits(portfolio_id: int) -> RiskLimits:
        limits, _ = RiskLimits.objects.get_or_create(portfolio_id=portfolio_id)
        return limits

    @staticmethod
    def _build_risk_manager(limits_config: RiskLimits, state: RiskState):
        ensure_platform_imports()
        from common.risk.risk_manager import PortfolioState, RiskManager
        from common.risk.risk_manager import RiskLimits as RMLimits

        limits = RMLimits(
            max_portfolio_drawdown=limits_config.max_portfolio_drawdown,
            max_single_trade_risk=limits_config.max_single_trade_risk,
            max_daily_loss=limits_config.max_daily_loss,
            max_open_positions=limits_config.max_open_positions,
            max_position_size_pct=limits_config.max_position_size_pct,
            max_correlation=limits_config.max_correlation,
            min_risk_reward=limits_config.min_risk_reward,
            max_leverage=limits_config.max_leverage,
        )
        rm = RiskManager(limits=limits)
        rm.state = PortfolioState(
            total_equity=state.total_equity,
            peak_equity=state.peak_equity,
            daily_start_equity=state.daily_start_equity,
            open_positions=state.open_positions or {},
            daily_pnl=state.daily_pnl,
            total_pnl=state.total_pnl,
            is_halted=state.is_halted,
            halt_reason=state.halt_reason,
        )
        return rm

    @staticmethod
    def _persist_state(rm, state: RiskState) -> None:
        state.total_equity = rm.state.total_equity
        state.peak_equity = rm.state.peak_equity
        state.daily_start_equity = rm.state.daily_start_equity
        state.open_positions = rm.state.open_positions
        state.daily_pnl = rm.state.daily_pnl
        state.total_pnl = rm.state.total_pnl
        state.is_halted = rm.state.is_halted
        state.halt_reason = rm.state.halt_reason
        state.save()

    @staticmethod
    def get_status(portfolio_id: int) -> dict:
        state = RiskManagementService._get_or_create_state(portfolio_id)
        peak = state.peak_equity if state.peak_equity > 0 else 1
        drawdown = 1.0 - (state.total_equity / peak)
        return {
            "equity": state.total_equity,
            "peak_equity": state.peak_equity,
            "drawdown": round(drawdown, 4),
            "daily_pnl": state.daily_pnl,
            "total_pnl": state.total_pnl,
            "open_positions": len(state.open_positions or {}),
            "is_halted": state.is_halted,
            "halt_reason": state.halt_reason,
        }

    @staticmethod
    def get_limits(portfolio_id: int) -> RiskLimits:
        return RiskManagementService._get_or_create_limits(portfolio_id)

    @staticmethod
    def update_limits(portfolio_id: int, updates: dict) -> RiskLimits:
        limits = RiskManagementService._get_or_create_limits(portfolio_id)
        for key, value in updates.items():
            if value is not None and hasattr(limits, key):
                setattr(limits, key, value)
        limits.save()
        return limits

    @staticmethod
    def update_equity(portfolio_id: int, equity: float) -> dict:
        state = RiskManagementService._get_or_create_state(portfolio_id)
        limits_config = RiskManagementService._get_or_create_limits(portfolio_id)
        rm = RiskManagementService._build_risk_manager(limits_config, state)
        rm.update_equity(equity)
        RiskManagementService._persist_state(rm, state)
        return RiskManagementService.get_status(portfolio_id)

    @staticmethod
    def check_trade(
        portfolio_id: int, symbol: str, side: str, size: float,
        entry_price: float, stop_loss_price: float | None = None,
    ) -> tuple[bool, str]:
        state = RiskManagementService._get_or_create_state(portfolio_id)
        limits_config = RiskManagementService._get_or_create_limits(portfolio_id)
        rm = RiskManagementService._build_risk_manager(limits_config, state)
        approved, reason = rm.check_new_trade(symbol, side, size, entry_price, stop_loss_price)

        peak = state.peak_equity if state.peak_equity > 0 else 1
        drawdown = 1.0 - (state.total_equity / peak)
        TradeCheckLog.objects.create(
            portfolio_id=portfolio_id, symbol=symbol, side=side,
            size=size, entry_price=entry_price, stop_loss_price=stop_loss_price,
            approved=approved, reason=reason, equity_at_check=state.total_equity,
            drawdown_at_check=round(drawdown, 4),
            open_positions_at_check=len(state.open_positions or {}),
        )

        if not approved:
            RiskManagementService.send_notification(
                portfolio_id, "trade_rejected", "warning",
                f"Trade REJECTED: {symbol} {side} x{size} @ {entry_price} — {reason}",
            )

        return approved, reason

    @staticmethod
    def calculate_position_size(
        portfolio_id: int, entry_price: float, stop_loss_price: float,
        risk_per_trade: float | None = None,
    ) -> dict:
        state = RiskManagementService._get_or_create_state(portfolio_id)
        limits_config = RiskManagementService._get_or_create_limits(portfolio_id)
        rm = RiskManagementService._build_risk_manager(limits_config, state)
        size = rm.calculate_position_size(entry_price, stop_loss_price, risk_per_trade)
        risk_pct = risk_per_trade or limits_config.max_single_trade_risk
        risk_amount = state.total_equity * risk_pct
        return {
            "size": round(size, 6),
            "risk_amount": round(risk_amount, 2),
            "position_value": round(size * entry_price, 2),
        }

    @staticmethod
    def reset_daily(portfolio_id: int) -> dict:
        state = RiskManagementService._get_or_create_state(portfolio_id)
        limits_config = RiskManagementService._get_or_create_limits(portfolio_id)
        rm = RiskManagementService._build_risk_manager(limits_config, state)
        rm.reset_daily()
        RiskManagementService._persist_state(rm, state)
        RiskManagementService.send_notification(
            portfolio_id, "daily_reset", "info", "Daily risk counters reset",
        )
        return RiskManagementService.get_status(portfolio_id)

    @staticmethod
    def get_var(portfolio_id: int, method: str = "parametric") -> dict:
        state = RiskManagementService._get_or_create_state(portfolio_id)
        limits_config = RiskManagementService._get_or_create_limits(portfolio_id)
        rm = RiskManagementService._build_risk_manager(limits_config, state)
        result = rm.get_var(method)
        return {
            "var_95": result.var_95, "var_99": result.var_99,
            "cvar_95": result.cvar_95, "cvar_99": result.cvar_99,
            "method": result.method, "window_days": result.window_days,
        }

    @staticmethod
    def get_heat_check(portfolio_id: int) -> dict:
        state = RiskManagementService._get_or_create_state(portfolio_id)
        limits_config = RiskManagementService._get_or_create_limits(portfolio_id)
        rm = RiskManagementService._build_risk_manager(limits_config, state)
        return rm.portfolio_heat_check()

    @staticmethod
    def record_metrics(portfolio_id: int, method: str = "parametric") -> RiskMetricHistory:
        state = RiskManagementService._get_or_create_state(portfolio_id)
        limits_config = RiskManagementService._get_or_create_limits(portfolio_id)
        rm = RiskManagementService._build_risk_manager(limits_config, state)
        var_result = rm.get_var(method)
        peak = state.peak_equity if state.peak_equity > 0 else 1
        drawdown = 1.0 - (state.total_equity / peak)

        return RiskMetricHistory.objects.create(
            portfolio_id=portfolio_id,
            var_95=var_result.var_95, var_99=var_result.var_99,
            cvar_95=var_result.cvar_95, cvar_99=var_result.cvar_99,
            method=var_result.method, drawdown=round(drawdown, 4),
            equity=state.total_equity,
            open_positions_count=len(state.open_positions or {}),
        )

    @staticmethod
    def get_metric_history(portfolio_id: int, hours: int = 168) -> list:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return list(
            RiskMetricHistory.objects.filter(
                portfolio_id=portfolio_id, recorded_at__gte=cutoff,
            ).order_by("-recorded_at")
        )

    @staticmethod
    def halt_trading(portfolio_id: int, reason: str) -> dict:
        state = RiskManagementService._get_or_create_state(portfolio_id)
        state.is_halted = True
        state.halt_reason = reason
        state.save()
        return {"is_halted": True, "halt_reason": reason, "message": f"Trading halted: {reason}"}

    @staticmethod
    def resume_trading(portfolio_id: int) -> dict:
        state = RiskManagementService._get_or_create_state(portfolio_id)
        state.is_halted = False
        state.halt_reason = ""
        state.save()
        return {"is_halted": False, "halt_reason": "", "message": "Trading resumed"}

    @staticmethod
    def send_notification(
        portfolio_id: int, event_type: str, severity: str, message: str,
    ) -> None:
        AlertLog.objects.create(
            portfolio_id=portfolio_id, event_type=event_type,
            severity=severity, message=message, channel="log",
            delivered=True, error="",
        )
        # Telegram (sync)
        delivered, error = NotificationService.send_telegram_sync(
            f"[{severity.upper()}] {message}"
        )
        AlertLog.objects.create(
            portfolio_id=portfolio_id, event_type=event_type,
            severity=severity, message=message, channel="telegram",
            delivered=delivered, error=error,
        )

    @staticmethod
    def get_alerts(portfolio_id: int, limit: int = 50) -> list:
        return list(
            AlertLog.objects.filter(portfolio_id=portfolio_id).order_by("-created_at")[:limit]
        )

    @staticmethod
    def get_trade_log(portfolio_id: int, limit: int = 50) -> list:
        return list(
            TradeCheckLog.objects.filter(portfolio_id=portfolio_id).order_by("-checked_at")[:limit]
        )
