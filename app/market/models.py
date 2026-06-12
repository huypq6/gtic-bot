"""ORM models cho dữ liệu thị trường. `kline` là Timescale hypertable (P1).

Các model nghiệp vụ (strategy/bot/order/position/audit) thêm ở app/orders/models.py (P2+).
"""

from datetime import datetime

from sqlalchemy import DateTime, Numeric, PrimaryKeyConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WatchSymbol(Base):
    """Watchlist — cặp theo dõi (sửa từ UI). Feed subscribe realtime theo bảng này."""

    __tablename__ = "watch_symbol"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Kline(Base):
    __tablename__ = "kline"

    symbol: Mapped[str] = mapped_column(String, nullable=False)
    tf: Mapped[str] = mapped_column(String, nullable=False)  # 1m,5m,1h,1d
    # timestamptz — khớp migration; phải tz-aware để asyncpg encode đúng.
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(Numeric, nullable=False)
    high: Mapped[float] = mapped_column(Numeric, nullable=False)
    low: Mapped[float] = mapped_column(Numeric, nullable=False)
    close: Mapped[float] = mapped_column(Numeric, nullable=False)
    volume: Mapped[float] = mapped_column(Numeric, nullable=False)

    __table_args__ = (PrimaryKeyConstraint("symbol", "tf", "ts"),)
