from pydantic import BaseModel


class ExchangeInfo(BaseModel):
    id: str
    name: str
    countries: list[str] = []
    has_fetch_tickers: bool = False
    has_fetch_ohlcv: bool = False
