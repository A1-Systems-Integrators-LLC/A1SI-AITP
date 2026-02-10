from datetime import datetime

from pydantic import BaseModel


class HoldingBase(BaseModel):
    symbol: str
    amount: float = 0.0
    avg_buy_price: float = 0.0


class HoldingCreate(HoldingBase):
    pass


class HoldingRead(HoldingBase):
    id: int
    portfolio_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PortfolioBase(BaseModel):
    name: str
    exchange_id: str = "binance"
    description: str = ""


class PortfolioCreate(PortfolioBase):
    pass


class PortfolioRead(PortfolioBase):
    id: int
    holdings: list[HoldingRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
