from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange_id: Mapped[str] = mapped_column(String(50))
    exchange_order_id: Mapped[str] = mapped_column(String(100), default="")
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(10))  # buy / sell
    order_type: Mapped[str] = mapped_column(String(20))  # market / limit
    amount: Mapped[float] = mapped_column()
    price: Mapped[float] = mapped_column(default=0.0)
    filled: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    timestamp: Mapped[datetime] = mapped_column()
