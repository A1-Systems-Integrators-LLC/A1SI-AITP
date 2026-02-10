from datetime import datetime

from pydantic import BaseModel


class TickerData(BaseModel):
    symbol: str
    price: float
    volume_24h: float = 0.0
    change_24h: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    timestamp: datetime


class MarketDataRead(TickerData):
    id: int
    exchange_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OHLCVData(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
