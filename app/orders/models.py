"""Business ORM models: strategy, bot, order, position. (audit_log added in P3.)

Matches the DDL in docs/04-SRS.md §4. `kline` lives in app/market/models.py.
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
    """Trading account (P9). PAPER: simulated balance, simulating USDT-M Futures.

    `balance` = wallet balance = deposits − withdrawals + realized PnL − fees; always updated in
    the same transaction as an `account_txn` row (ledger = source of truth, balance = cache).
    """

    __tablename__ = "account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False, default="PAPER")
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USDT")
    balance: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    peak_equity: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    # fill simulation
    leverage: Mapped[float] = mapped_column(Numeric, nullable=False, default=1)
    taker_fee: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0005)
    maker_fee: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0002)
    slippage_bps: Mapped[float] = mapped_column(Numeric, nullable=False, default=2)
    # risk guards (% of equity); NULL = disabled
    max_risk_pct: Mapped[float | None] = mapped_column(Numeric)  # per-trade risk cap
    max_open_risk_pct: Mapped[float | None] = mapped_column(Numeric)  # total open risk cap
    max_positions: Mapped[int | None] = mapped_column(Integer)
    daily_loss_pct: Mapped[float | None] = mapped_column(Numeric)  # daily loss (UTC) → pause
    max_dd_pct: Mapped[float | None] = mapped_column(Numeric)  # drawdown from peak → HALTED
    status: Mapped[str] = mapped_column(String, nullable=False, default="ACTIVE")
    halted_reason: Mapped[str | None] = mapped_column(String)
    halted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # P9b — exchange account (TESTNET/LIVE): figures read from Binance Futures (last-sync cache)
    market: Mapped[str] = mapped_column(String, nullable=False, default="FUTURES")
    exch_equity: Mapped[float | None] = mapped_column(Numeric)
    exch_unrealized: Mapped[float | None] = mapped_column(Numeric)
    exch_margin: Mapped[float | None] = mapped_column(Numeric)
    exch_available: Mapped[float | None] = mapped_column(Numeric)
    income_cursor: Mapped[int | None] = mapped_column(BigInteger)  # ms, ledger imported up to here
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_error: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','HALTED')", name="ck_account_status"),
        CheckConstraint("mode IN ('PAPER','TESTNET','LIVE')", name="ck_account_mode"),
    )


class AccountTxn(Base):
    """Ledger: every wallet balance change. amount is signed; balance_after = balance after row."""

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
    ext_id: Mapped[str | None] = mapped_column(String)  # exchange income id (dedup on import)

    __table_args__ = (
        CheckConstraint(
            "type IN ('DEPOSIT','WITHDRAW','REALIZED_PNL','FEE','FUNDING','ADJUST')",
            name="ck_txn_type",
        ),
        UniqueConstraint("account_id", "ext_id", name="uq_txn_ext"),
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
    # money management: {"method": risk_pct|risk_usdt|notional_usdt|notional_pct|fixed_qty,
    #                   "value": x}
    sizing: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("mode IN ('PAPER','TESTNET','LIVE')", name="ck_bot_mode"),
        CheckConstraint("status IN ('RUNNING','PAUSED','STOPPED')", name="ck_bot_status"),
    )


class OrderModel(Base):
    __tablename__ = "order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int | None] = mapped_column(ForeignKey("bot.id"))  # NULL for manual orders
    ext_id: Mapped[str | None] = mapped_column(String)  # exchange order id (testnet/live)
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
    # which trade this fill belongs to: OPEN = entry fill, CLOSE = exit fill (NULL = unknown/legacy)
    position_id: Mapped[int | None] = mapped_column(Integer)
    intent: Mapped[str | None] = mapped_column(String)  # OPEN|CLOSE
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
    init_sl: Mapped[float | None] = mapped_column(Numeric)  # SL at open → the 1R reference
    # Snapshot at open — bot_id becomes NULL when the bot is deleted, these columns are kept.
    source: Mapped[str | None] = mapped_column(String)  # BOT|MANUAL
    bot_ref: Mapped[int | None] = mapped_column(Integer)  # original bot id (no FK)
    strategy: Mapped[str | None] = mapped_column(String)  # "ict_po3 v4"
    tf: Mapped[str | None] = mapped_column(String)
    params: Mapped[dict | None] = mapped_column(JSONB)
    account_id: Mapped[int | None] = mapped_column(Integer)
    fee: Mapped[float | None] = mapped_column(Numeric)  # total entry + exit fees (USDT)
    margin: Mapped[float | None] = mapped_column(Numeric)  # margin locked at open
    risk_amount: Mapped[float | None] = mapped_column(Numeric)  # USDT lost if the initial SL is hit
    ext_protect: Mapped[dict | None] = mapped_column(JSONB)  # {"sl": algoId, "tp": algoId}
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
    # P9c: VBT (vectorbt, 100% equity, entry/exit at close) | ACCOUNT (account simulation)
    engine: Mapped[str | None] = mapped_column(String)
    sizing: Mapped[dict | None] = mapped_column(JSONB)
    settings: Mapped[dict | None] = mapped_column(JSONB)  # fees/slippage/guards used
    stats: Mapped[dict | None] = mapped_column(JSONB)  # CAGR, PF, avgR, monthly, comparison…
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
    pnl: Mapped[float | None] = mapped_column(Numeric)  # net USDT
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
    entry: Mapped[float | None] = mapped_column(Numeric)  # current price
    atr: Mapped[float | None] = mapped_column(Numeric)
    sl: Mapped[float | None] = mapped_column(Numeric)  # suggested SL (ATR)
    tp: Mapped[float | None] = mapped_column(Numeric)  # suggested TP (ATR)


class AuditLog(Base):
    """Log EVERY action (bot + manual) BEFORE acting (traceability NFR)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(String, nullable=False)  # BOT|MANUAL|SYSTEM
    mode: Mapped[str | None] = mapped_column(String)
    bot_id: Mapped[int | None] = mapped_column(Integer)
    symbol: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, nullable=False)  # OPEN|CLOSE|EDIT_SLTP|CANCEL|...
    detail: Mapped[dict | None] = mapped_column(JSONB)
