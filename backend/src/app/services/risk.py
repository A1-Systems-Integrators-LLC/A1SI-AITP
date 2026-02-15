"""
Risk management service — wraps common.risk.risk_manager with DB persistence.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk import RiskLimitsConfig, RiskState
from app.services.platform_bridge import ensure_platform_imports

logger = logging.getLogger("risk_service")


class RiskManagementService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_or_create_state(self, portfolio_id: int) -> RiskState:
        result = await self._session.execute(
            select(RiskState).where(RiskState.portfolio_id == portfolio_id)
        )
        state = result.scalar_one_or_none()
        if not state:
            state = RiskState(portfolio_id=portfolio_id)
            self._session.add(state)
            await self._session.flush()
        return state

    async def _get_or_create_limits(self, portfolio_id: int) -> RiskLimitsConfig:
        result = await self._session.execute(
            select(RiskLimitsConfig).where(RiskLimitsConfig.portfolio_id == portfolio_id)
        )
        limits = result.scalar_one_or_none()
        if not limits:
            limits = RiskLimitsConfig(portfolio_id=portfolio_id)
            self._session.add(limits)
            await self._session.flush()
        return limits

    def _build_risk_manager(self, limits_config: RiskLimitsConfig, state: RiskState):
        """Build an in-memory RiskManager from DB state."""
        ensure_platform_imports()
        from common.risk.risk_manager import PortfolioState, RiskLimits, RiskManager

        limits = RiskLimits(
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

    def _persist_state(self, rm, state: RiskState) -> None:
        """Copy RiskManager state back to DB model."""
        state.total_equity = rm.state.total_equity
        state.peak_equity = rm.state.peak_equity
        state.daily_start_equity = rm.state.daily_start_equity
        state.open_positions = rm.state.open_positions
        state.daily_pnl = rm.state.daily_pnl
        state.total_pnl = rm.state.total_pnl
        state.is_halted = rm.state.is_halted
        state.halt_reason = rm.state.halt_reason

    async def get_status(self, portfolio_id: int) -> dict:
        state = await self._get_or_create_state(portfolio_id)
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

    async def get_limits(self, portfolio_id: int) -> RiskLimitsConfig:
        return await self._get_or_create_limits(portfolio_id)

    async def update_limits(self, portfolio_id: int, updates: dict) -> RiskLimitsConfig:
        limits = await self._get_or_create_limits(portfolio_id)
        for key, value in updates.items():
            if value is not None and hasattr(limits, key):
                setattr(limits, key, value)
        await self._session.commit()
        return limits

    async def update_equity(self, portfolio_id: int, equity: float) -> dict:
        state = await self._get_or_create_state(portfolio_id)
        limits_config = await self._get_or_create_limits(portfolio_id)
        rm = self._build_risk_manager(limits_config, state)
        rm.update_equity(equity)
        self._persist_state(rm, state)
        await self._session.commit()
        return await self.get_status(portfolio_id)

    async def check_trade(
        self,
        portfolio_id: int,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        stop_loss_price: float | None = None,
    ) -> tuple[bool, str]:
        state = await self._get_or_create_state(portfolio_id)
        limits_config = await self._get_or_create_limits(portfolio_id)
        rm = self._build_risk_manager(limits_config, state)
        return rm.check_new_trade(symbol, side, size, entry_price, stop_loss_price)

    async def calculate_position_size(
        self,
        portfolio_id: int,
        entry_price: float,
        stop_loss_price: float,
        risk_per_trade: float | None = None,
    ) -> dict:
        state = await self._get_or_create_state(portfolio_id)
        limits_config = await self._get_or_create_limits(portfolio_id)
        rm = self._build_risk_manager(limits_config, state)
        size = rm.calculate_position_size(entry_price, stop_loss_price, risk_per_trade)
        risk_pct = risk_per_trade or limits_config.max_single_trade_risk
        risk_amount = state.total_equity * risk_pct
        return {
            "size": round(size, 6),
            "risk_amount": round(risk_amount, 2),
            "position_value": round(size * entry_price, 2),
        }

    async def reset_daily(self, portfolio_id: int) -> dict:
        state = await self._get_or_create_state(portfolio_id)
        limits_config = await self._get_or_create_limits(portfolio_id)
        rm = self._build_risk_manager(limits_config, state)
        rm.reset_daily()
        self._persist_state(rm, state)
        await self._session.commit()
        return await self.get_status(portfolio_id)

    async def get_var(self, portfolio_id: int, method: str = "parametric") -> dict:
        state = await self._get_or_create_state(portfolio_id)
        limits_config = await self._get_or_create_limits(portfolio_id)
        rm = self._build_risk_manager(limits_config, state)
        result = rm.get_var(method)
        return {
            "var_95": result.var_95,
            "var_99": result.var_99,
            "cvar_95": result.cvar_95,
            "cvar_99": result.cvar_99,
            "method": result.method,
            "window_days": result.window_days,
        }

    async def get_heat_check(self, portfolio_id: int) -> dict:
        state = await self._get_or_create_state(portfolio_id)
        limits_config = await self._get_or_create_limits(portfolio_id)
        rm = self._build_risk_manager(limits_config, state)
        return rm.portfolio_heat_check()
