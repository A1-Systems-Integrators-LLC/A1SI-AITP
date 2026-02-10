from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.exchange import ExchangeService
from app.services.market import MarketService
from app.services.portfolio import PortfolioService
from app.services.trading import TradingService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_exchange_service() -> AsyncGenerator[ExchangeService, None]:
    service = ExchangeService()
    try:
        yield service
    finally:
        await service.close()


ExchangeServiceDep = Annotated[ExchangeService, Depends(get_exchange_service)]


def get_portfolio_service(session: SessionDep) -> PortfolioService:
    return PortfolioService(session)


def get_market_service(
    session: SessionDep, exchange: ExchangeServiceDep
) -> MarketService:
    return MarketService(session, exchange)


def get_trading_service(
    session: SessionDep, exchange: ExchangeServiceDep
) -> TradingService:
    return TradingService(session, exchange)


PortfolioServiceDep = Annotated[PortfolioService, Depends(get_portfolio_service)]
MarketServiceDep = Annotated[MarketService, Depends(get_market_service)]
TradingServiceDep = Annotated[TradingService, Depends(get_trading_service)]
