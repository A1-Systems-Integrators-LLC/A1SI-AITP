from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.portfolio import Holding, Portfolio
from app.schemas.portfolio import HoldingCreate, PortfolioCreate


class PortfolioService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_portfolios(self) -> list[Portfolio]:
        stmt = select(Portfolio).options(selectinload(Portfolio.holdings))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_portfolio(self, portfolio_id: int) -> Portfolio | None:
        stmt = (
            select(Portfolio)
            .options(selectinload(Portfolio.holdings))
            .where(Portfolio.id == portfolio_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_portfolio(self, data: PortfolioCreate) -> Portfolio:
        portfolio = Portfolio(**data.model_dump())
        self.session.add(portfolio)
        await self.session.commit()
        await self.session.refresh(portfolio, ["holdings"])
        return portfolio

    async def delete_portfolio(self, portfolio_id: int) -> bool:
        portfolio = await self.get_portfolio(portfolio_id)
        if portfolio is None:
            return False
        await self.session.delete(portfolio)
        await self.session.commit()
        return True

    async def add_holding(self, portfolio_id: int, data: HoldingCreate) -> Holding | None:
        portfolio = await self.get_portfolio(portfolio_id)
        if portfolio is None:
            return None
        holding = Holding(portfolio_id=portfolio_id, **data.model_dump())
        self.session.add(holding)
        await self.session.commit()
        await self.session.refresh(holding)
        return holding
