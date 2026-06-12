"""ORM models nghiệp vụ: strategy, bot, order, position. (audit_log thêm ở P3.)

Khớp DDL trong docs/04-SRS.md §4. `kline` ở app/market/models.py.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
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


class BacktestRun(Base):
    __tablename__ = "backtest_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategy.id"))
    params: Mapped[dict | None] = mapped_column(JSONB)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    tf: Mapped[str] = mapped_column(String, nullable=False)
    from_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    capital: Mapped[float | None] = mapped_column(Numeric)
    fee_rate: Mapped[float | None] = mapped_column(Numeric)
    market: Mapped[str | None] = mapped_column(String)  # SPOT | FUTURES
    leverage: Mapped[int | None] = mapped_column(Integer)
    pnl_pct: Mapped[float | None] = mapped_column(Numeric)
    winrate: Mapped[float | None] = mapped_column(Numeric)
    max_dd: Mapped[float | None] = mapped_column(Numeric)
    sharpe: Mapped[float | None] = mapped_column(Numeric)
    n_trades: Mapped[int | None] = mapped_column(Integer)
    equity_curve: Mapped[list | None] = mapped_column(JSONB)  # [[ts_ms, equity], ...]
    indicators: Mapped[dict | None] = mapped_column(JSONB)  # {name: [[ts, value], ...]}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BacktestTrade(Base):
    __tablename__ = "backtest_trade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("backtest_run.id", ondelete="CASCADE"))
    side: Mapped[str | None] = mapped_column(String)
    entry_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entry: Mapped[float | None] = mapped_column(Numeric)
    exit_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit: Mapped[float | None] = mapped_column(Numeric)
    pnl_pct: Mapped[float | None] = mapped_column(Numeric)
    sl: Mapped[float | None] = mapped_column(Numeric)
    tp: Mapped[float | None] = mapped_column(Numeric)


class ScanResult(Base):
    __tablename__ = "scan_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    symbol: Mapped[str | None] = mapped_column(String)
    score: Mapped[float | None] = mapped_column(Numeric)
    signal: Mapped[str | None] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(String)
    entry: Mapped[float | None] = mapped_column(Numeric)  # giá hiện tại
    atr: Mapped[float | None] = mapped_column(Numeric)
    sl: Mapped[float | None] = mapped_column(Numeric)  # SL đề xuất (ATR)
    tp: Mapped[float | None] = mapped_column(Numeric)  # TP đề xuất (ATR)


class AuditLog(Base):
    """Ghi MỌI hành động (bot + tay) TRƯỚC khi tác động (NFR truy vết)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(String, nullable=False)  # BOT|MANUAL|SYSTEM
    mode: Mapped[str | None] = mapped_column(String)
    bot_id: Mapped[int | None] = mapped_column(Integer)
    symbol: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, nullable=False)  # OPEN|CLOSE|EDIT_SLTP|CANCEL|...
    detail: Mapped[dict | None] = mapped_column(JSONB)
