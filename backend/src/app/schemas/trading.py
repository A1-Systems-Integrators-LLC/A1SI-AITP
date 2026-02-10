from datetime import datetime

from pydantic import BaseModel


class OrderBase(BaseModel):
    symbol: str
    side: str  # buy / sell
    order_type: str = "market"  # market / limit
    amount: float
    price: float = 0.0


class OrderCreate(OrderBase):
    exchange_id: str = "binance"


class OrderRead(OrderBase):
    id: int
    exchange_id: str
    exchange_order_id: str
    filled: float
    status: str
    timestamp: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
