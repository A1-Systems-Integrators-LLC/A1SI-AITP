from fastapi import APIRouter

from app.deps import SessionDep
from app.schemas.risk import (
    EquityUpdateRequest,
    HeatCheckResponse,
    PositionSizeRequest,
    PositionSizeResponse,
    RiskLimitsRead,
    RiskLimitsUpdate,
    RiskStatusRead,
    TradeCheckRequest,
    TradeCheckResponse,
    VaRResponse,
)
from app.services.risk import RiskManagementService

router = APIRouter(prefix="/risk", tags=["risk"])


def _get_service(session) -> RiskManagementService:
    return RiskManagementService(session)


@router.get("/{portfolio_id}/status", response_model=RiskStatusRead)
async def get_status(portfolio_id: int, session: SessionDep) -> dict:
    return await _get_service(session).get_status(portfolio_id)


@router.get("/{portfolio_id}/limits", response_model=RiskLimitsRead)
async def get_limits(portfolio_id: int, session: SessionDep) -> object:
    return await _get_service(session).get_limits(portfolio_id)


@router.put("/{portfolio_id}/limits", response_model=RiskLimitsRead)
async def update_limits(
    portfolio_id: int, data: RiskLimitsUpdate, session: SessionDep
) -> object:
    return await _get_service(session).update_limits(
        portfolio_id, data.model_dump(exclude_none=True)
    )


@router.post("/{portfolio_id}/equity", response_model=RiskStatusRead)
async def update_equity(
    portfolio_id: int, data: EquityUpdateRequest, session: SessionDep
) -> dict:
    return await _get_service(session).update_equity(portfolio_id, data.equity)


@router.post("/{portfolio_id}/check-trade", response_model=TradeCheckResponse)
async def check_trade(
    portfolio_id: int, data: TradeCheckRequest, session: SessionDep
) -> dict:
    approved, reason = await _get_service(session).check_trade(
        portfolio_id, data.symbol, data.side, data.size, data.entry_price, data.stop_loss_price
    )
    return {"approved": approved, "reason": reason}


@router.post("/{portfolio_id}/position-size", response_model=PositionSizeResponse)
async def position_size(
    portfolio_id: int, data: PositionSizeRequest, session: SessionDep
) -> dict:
    return await _get_service(session).calculate_position_size(
        portfolio_id, data.entry_price, data.stop_loss_price, data.risk_per_trade
    )


@router.post("/{portfolio_id}/reset-daily", response_model=RiskStatusRead)
async def reset_daily(portfolio_id: int, session: SessionDep) -> dict:
    return await _get_service(session).reset_daily(portfolio_id)


@router.get("/{portfolio_id}/var", response_model=VaRResponse)
async def get_var(
    portfolio_id: int, session: SessionDep, method: str = "parametric"
) -> dict:
    return await _get_service(session).get_var(portfolio_id, method)


@router.get("/{portfolio_id}/heat-check", response_model=HeatCheckResponse)
async def get_heat_check(portfolio_id: int, session: SessionDep) -> dict:
    return await _get_service(session).get_heat_check(portfolio_id)
