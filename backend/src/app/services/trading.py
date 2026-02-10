from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import Order
from app.schemas.trading import OrderCreate
from app.services.exchange import ExchangeService


class TradingService:
    def __init__(self, session: AsyncSession, exchange: ExchangeService) -> None:
        self.session = session
        self.exchange = exchange

    async def list_orders(self, limit: int = 50) -> list[Order]:
        stmt = select(Order).order_by(Order.timestamp.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_order(self, order_id: int) -> Order | None:
        stmt = select(Order).where(Order.id == order_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_order(self, data: OrderCreate) -> Order:
        order = Order(
            exchange_id=data.exchange_id,
            symbol=data.symbol,
            side=data.side,
            order_type=data.order_type,
            amount=data.amount,
            price=data.price,
            status="created",
            timestamp=datetime.now(timezone.utc),
        )
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)
        return order
