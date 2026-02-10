from fastapi import APIRouter, Query

from app.deps import MarketServiceDep
from app.schemas.market import OHLCVData, TickerData

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/ticker/{symbol:path}", response_model=TickerData)
async def get_ticker(symbol: str, service: MarketServiceDep) -> TickerData:
    return await service.get_ticker(symbol)


@router.get("/tickers", response_model=list[TickerData])
async def get_tickers(
    service: MarketServiceDep,
    symbols: str | None = Query(None, description="Comma-separated symbols"),
) -> list[TickerData]:
    symbol_list = symbols.split(",") if symbols else None
    return await service.get_tickers(symbol_list)


@router.get("/ohlcv/{symbol:path}", response_model=list[OHLCVData])
async def get_ohlcv(
    symbol: str,
    service: MarketServiceDep,
    timeframe: str = Query("1h"),
    limit: int = Query(100, ge=1, le=1000),
) -> list[OHLCVData]:
    return await service.get_ohlcv(symbol, timeframe, limit)
