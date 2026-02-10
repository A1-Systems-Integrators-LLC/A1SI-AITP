from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import MarketData
from app.schemas.market import OHLCVData, TickerData
from app.services.exchange import ExchangeService


class MarketService:
    def __init__(self, session: AsyncSession, exchange: ExchangeService) -> None:
        self.session = session
        self.exchange = exchange

    async def get_ticker(self, symbol: str) -> TickerData:
        return await self.exchange.fetch_ticker(symbol)

    async def get_tickers(self, symbols: list[str] | None = None) -> list[TickerData]:
        return await self.exchange.fetch_tickers(symbols)

    async def get_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> list[OHLCVData]:
        return await self.exchange.fetch_ohlcv(symbol, timeframe, limit)

    async def save_ticker(self, ticker: TickerData, exchange_id: str) -> MarketData:
        record = MarketData(
            symbol=ticker.symbol,
            exchange_id=exchange_id,
            price=ticker.price,
            volume_24h=ticker.volume_24h,
            change_24h=ticker.change_24h,
            high_24h=ticker.high_24h,
            low_24h=ticker.low_24h,
            timestamp=ticker.timestamp,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get_price_history(
        self, symbol: str, limit: int = 100
    ) -> list[MarketData]:
        stmt = (
            select(MarketData)
            .where(MarketData.symbol == symbol)
            .order_by(MarketData.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
