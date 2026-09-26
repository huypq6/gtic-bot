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


class Account(Base):
    """Tài khoản giao dịch (P9). PAPER: số dư giả lập, mô phỏng USDT-M Futures.

    `balance` = số dư ví (wallet) = nạp − rút + lãi/lỗ đã chốt − phí; luôn cập nhật cùng
    transaction với 1 dòng `account_txn` (sổ cái là nguồn sự thật, balance là cache).
    """

    __tablename__ = "account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False, default="PAPER")
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USDT")
    balance: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    peak_equity: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    # mô phỏng khớp lệnh
    leverage: Mapped[float] = mapped_column(Numeric, nullable=False, default=1)
    taker_fee: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0005)
    maker_fee: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0002)
    slippage_bps: Mapped[float] = mapped_column(Numeric, nullable=False, default=2)
    # rào chắn rủi ro (% theo equity); NULL = tắt
    max_risk_pct: Mapped[float | None] = mapped_column(Numeric)  # trần rủi ro 1 lệnh
    max_open_risk_pct: Mapped[float | None] = mapped_column(Numeric)  # tổng rủi ro đang mở
    max_positions: Mapped[int | None] = mapped_column(Integer)
    daily_loss_pct: Mapped[float | None] = mapped_column(Numeric)  # lỗ trong ngày UTC → nghỉ
    max_dd_pct: Mapped[float | None] = mapped_column(Numeric)  # sụt từ đỉnh → HALTED
    status: Mapped[str] = mapped_column(String, nullable=False, default="ACTIVE")
    halted_reason: Mapped[str | None] = mapped_column(String)
    halted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','HALTED')", name="ck_account_status"),
        CheckConstraint("mode IN ('PAPER','TESTNET','LIVE')", name="ck_account_mode"),
    )


class AccountTxn(Base):
    """Sổ cái: mọi biến động số dư ví. amount có dấu; balance_after = số dư sau dòng này."""

    __tablename__ = "account_txn"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    type: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric, nullable=False)
    position_id: Mapped[int | None] = mapped_column(Integer)
    bot_id: Mapped[int | None] = mapped_column(Integer)
    symbol: Mapped[str | None] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        CheckConstraint(
            "type IN ('DEPOSIT','WITHDRAW','REALIZED_PNL','FEE','ADJUST')", name="ck_txn_type"
        ),
    )


class Bot(Base):
    __tablename__ = "bot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategy.id"))
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    tf: Mapped[str] = mapped_column(String, nullable=False, default="1h")
    mode: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False, default="STOPPED")
    account_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"))
    # quản lý vốn: {"method": risk_pct|risk_usdt|notional_usdt|notional_pct|fixed_qty, "value": x}
    sizing: Mapped[dict | None] = mapped_column(JSONB)
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
    exit_reason: Mapped[str | None] = mapped_column(String)  # SL|TP|SIGNAL|MANUAL
    init_sl: Mapped[float | None] = mapped_column(Numeric)  # SL lúc mở → mốc 1R
    # Snapshot lúc mở — bot_id bị NULL khi xóa bot, các cột này thì giữ nguyên.
    source: Mapped[str | None] = mapped_column(String)  # BOT|MANUAL
    bot_ref: Mapped[int | None] = mapped_column(Integer)  # id bot gốc (không FK)
    strategy: Mapped[str | None] = mapped_column(String)  # "ict_po3 v4"
    tf: Mapped[str | None] = mapped_column(String)
    params: Mapped[dict | None] = mapped_column(JSONB)
    account_id: Mapped[int | None] = mapped_column(Integer)
    fee: Mapped[float | None] = mapped_column(Numeric)  # tổng phí vào + ra (USDT)
    margin: Mapped[float | None] = mapped_column(Numeric)  # ký quỹ khóa khi mở
    risk_amount: Mapped[float | None] = mapped_column(Numeric)  # USDT mất nếu chạm SL ban đầu
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
    # P9c: VBT (vectorbt, 100% vốn, vào/ra giá đóng) | ACCOUNT (mô phỏng tài khoản)
    engine: Mapped[str | None] = mapped_column(String)
    sizing: Mapped[dict | None] = mapped_column(JSONB)
    settings: Mapped[dict | None] = mapped_column(JSONB)  # phí/trượt/rào chắn đã dùng
    stats: Mapped[dict | None] = mapped_column(JSONB)  # CAGR, PF, avgR, tháng, so sánh…
    final_equity: Mapped[float | None] = mapped_column(Numeric)
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
    # P9c (engine ACCOUNT)
    qty: Mapped[float | None] = mapped_column(Numeric)
    pnl: Mapped[float | None] = mapped_column(Numeric)  # USDT ròng
    fee: Mapped[float | None] = mapped_column(Numeric)
    r: Mapped[float | None] = mapped_column(Numeric)
    reason: Mapped[str | None] = mapped_column(String)
    mfe_r: Mapped[float | None] = mapped_column(Numeric)
    mae_r: Mapped[float | None] = mapped_column(Numeric)


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
