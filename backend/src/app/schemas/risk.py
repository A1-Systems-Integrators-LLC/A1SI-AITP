
from pydantic import BaseModel


class RiskLimitsRead(BaseModel):
    max_portfolio_drawdown: float = 0.15
    max_single_trade_risk: float = 0.02
    max_daily_loss: float = 0.05
    max_open_positions: int = 10
    max_position_size_pct: float = 0.20
    max_correlation: float = 0.70
    min_risk_reward: float = 1.5
    max_leverage: float = 1.0

    model_config = {"from_attributes": True}


class RiskLimitsUpdate(BaseModel):
    max_portfolio_drawdown: float | None = None
    max_single_trade_risk: float | None = None
    max_daily_loss: float | None = None
    max_open_positions: int | None = None
    max_position_size_pct: float | None = None
    max_correlation: float | None = None
    min_risk_reward: float | None = None
    max_leverage: float | None = None


class RiskStatusRead(BaseModel):
    equity: float
    peak_equity: float
    drawdown: float
    daily_pnl: float
    total_pnl: float
    open_positions: int
    is_halted: bool
    halt_reason: str


class EquityUpdateRequest(BaseModel):
    equity: float


class TradeCheckRequest(BaseModel):
    symbol: str
    side: str
    size: float
    entry_price: float
    stop_loss_price: float | None = None


class TradeCheckResponse(BaseModel):
    approved: bool
    reason: str


class PositionSizeRequest(BaseModel):
    entry_price: float
    stop_loss_price: float
    risk_per_trade: float | None = None


class PositionSizeResponse(BaseModel):
    size: float
    risk_amount: float
    position_value: float


class VaRResponse(BaseModel):
    var_95: float = 0.0
    var_99: float = 0.0
    cvar_95: float = 0.0
    cvar_99: float = 0.0
    method: str = "parametric"
    window_days: int = 0


class HeatCheckResponse(BaseModel):
    healthy: bool
    issues: list[str]
    drawdown: float
    daily_pnl: float
    open_positions: int
    max_correlation: float
    high_corr_pairs: list  # list of [symbol, symbol, correlation]
    max_concentration: float
    position_weights: dict[str, float]
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    is_halted: bool
