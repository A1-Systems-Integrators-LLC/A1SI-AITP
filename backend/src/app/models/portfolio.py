from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Portfolio(TimestampMixin, Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    exchange_id: Mapped[str] = mapped_column(String(50), default="binance")
    description: Mapped[str] = mapped_column(String(500), default="")

    holdings: Mapped[list["Holding"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class Holding(TimestampMixin, Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    symbol: Mapped[str] = mapped_column(String(20))  # e.g. BTC, ETH
    amount: Mapped[float] = mapped_column(default=0.0)
    avg_buy_price: Mapped[float] = mapped_column(default=0.0)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="holdings")
