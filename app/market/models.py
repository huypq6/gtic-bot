"""ORM models for market data. `kline` is a Timescale hypertable (P1).

Domain models (strategy/bot/order/position/audit) live in app/orders/models.py (P2+).
"""

from datetime import datetime

from sqlalchemy import DateTime, Numeric, PrimaryKeyConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WatchSymbol(Base):
    """Watchlist — watched pairs (edited from the UI). The feed subscribes based on this table."""

    __tablename__ = "watch_symbol"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Kline(Base):
    __tablename__ = "kline"

    symbol: Mapped[str] = mapped_column(String, nullable=False)
    tf: Mapped[str] = mapped_column(String, nullable=False)  # 1m,5m,1h,1d
    # timestamptz — matches the migration; must be tz-aware for asyncpg to encode correctly.
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(Numeric, nullable=False)
    high: Mapped[float] = mapped_column(Numeric, nullable=False)
    low: Mapped[float] = mapped_column(Numeric, nullable=False)
    close: Mapped[float] = mapped_column(Numeric, nullable=False)
    volume: Mapped[float] = mapped_column(Numeric, nullable=False)

    __table_args__ = (PrimaryKeyConstraint("symbol", "tf", "ts"),)
