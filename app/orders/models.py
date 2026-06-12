"""ORM models nghiệp vụ: strategy, bot, order, position. (audit_log thêm ở P3.)

Khớp DDL trong docs/04-SRS.md §4. `kline` ở app/market/models.py.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StrategyModel(Base):
    __tablename__ = "strategy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    default_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source_file: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("name", "version", name="uq_strategy_name_version"),)


class Bot(Base):
    __tablename__ = "bot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategy.id"))
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    tf: Mapped[str] = mapped_column(String, nullable=False, default="1h")
    mode: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False, default="STOPPED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("mode IN ('PAPER','TESTNET','LIVE')", name="ck_bot_mode"),
        CheckConstraint("status IN ('RUNNING','PAUSED','STOPPED')", name="ck_bot_status"),
    )


class OrderModel(Base):
    __tablename__ = "order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int | None] = mapped_column(ForeignKey("bot.id"))  # NULL nếu lệnh tay rời
    ext_id: Mapped[str | None] = mapped_column(String)  # id sàn (testnet/live)
    source: Mapped[str] = mapped_column(String, nullable=False)  # BOT|MANUAL|SYSTEM
    mode: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    side: Mapped[str] = mapped_column(String, nullable=False)  # BUY|SELL
    type: Mapped[str] = mapped_column(String, nullable=False)  # MARKET|LIMIT
    qty: Mapped[float] = mapped_column(Numeric, nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(String, nullable=False)  # NEW|FILLED|...
    sl: Mapped[float | None] = mapped_column(Numeric)
    tp: Mapped[float | None] = mapped_column(Numeric)
    filled_qty: Mapped[float] = mapped_column(Numeric, default=0)
    avg_price: Mapped[float | None] = mapped_column(Numeric)
    fee: Mapped[float] = mapped_column(Numeric, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("source IN ('BOT','MANUAL','SYSTEM')", name="ck_order_source"),
        CheckConstraint("side IN ('BUY','SELL')", name="ck_order_side"),
        CheckConstraint("type IN ('MARKET','LIMIT')", name="ck_order_type"),
        CheckConstraint(
            "status IN ('NEW','FILLED','PARTIAL','CANCELLED','REJECTED')", name="ck_order_status"
        ),
    )


class PositionModel(Base):
    __tablename__ = "position"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int | None] = mapped_column(ForeignKey("bot.id"))
    mode: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    side: Mapped[str] = mapped_column(String, nullable=False)  # LONG|SHORT
    qty: Mapped[float] = mapped_column(Numeric, nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    sl: Mapped[float | None] = mapped_column(Numeric)
    tp: Mapped[float | None] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(String, nullable=False, default="OPEN")
    exit_price: Mapped[float | None] = mapped_column(Numeric)
    pnl: Mapped[float | None] = mapped_column(Numeric)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("side IN ('LONG','SHORT')", name="ck_position_side"),
        CheckConstraint("status IN ('OPEN','CLOSED')", name="ck_position_status"),
    )
