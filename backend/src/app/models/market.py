from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MarketData(TimestampMixin, Base):
    __tablename__ = "market_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)  # e.g. BTC/USDT
    exchange_id: Mapped[str] = mapped_column(String(50))
    price: Mapped[float] = mapped_column()
    volume_24h: Mapped[float] = mapped_column(default=0.0)
    change_24h: Mapped[float] = mapped_column(default=0.0)
    high_24h: Mapped[float] = mapped_column(default=0.0)
    low_24h: Mapped[float] = mapped_column(default=0.0)
    timestamp: Mapped[datetime] = mapped_column()
