"""PaperExecutor — internal order matching (PaperEngine) + DB persistence + bus broadcast.

Never calls the exchange. One executor per bot. The runner calls `on_price` on every tick (checks
SL/TP/limit + publishes realtime PnL) and `submit` when there is a Signal.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.execution.base import Executor
from app.execution.paper_engine import Closed, EngineEvent, Fill, PaperEngine
from app.market.bus import EventBus
from app.orders.models import OrderModel, PositionModel
from app.strategy.base import Position, Signal

logger = logging.getLogger(__name__)


class PaperExecutor(Executor):
    def __init__(
        self,
        bot_id: int | None,
        symbol: str,
        mode: str,
        bus: EventBus,
        session_factory: async_sessionmaker,
        fee_rate: float = 0.0,
    ) -> None:
        self.engine = PaperEngine(symbol, fee_rate)
        self.bot_id = bot_id
        self.symbol = symbol
        self.mode = mode
        self.source = "BOT" if bot_id is not None else "MANUAL"
        self._bus = bus
        self._sf = session_factory
        self._last_price = 0.0
        self._pos_db_id: int | None = None
        self._pending_db: dict[int, int] = {}  # engine pending oid → db order id
        self.account_id: int | None = None
        self._accounts = None  # AccountService (P9) — None = no ledger (tests/legacy)

    def attach_account(self, account, service) -> None:
        """Attach an account: the engine simulates per its config + every PnL/fee is booked."""
        self.account_id = account.id
        self._accounts = service
        e = self.engine
        e.fee_rate = float(account.taker_fee)
        e.maker_fee = float(account.maker_fee)
        e.slip = float(account.slippage_bps) / 10_000
        e.leverage = max(1.0, float(account.leverage))
        e.gap_fill = True

    async def restore_open(self) -> bool:
        """After restart: reload this bot's/manual order's OPEN position into the engine."""
        q = select(PositionModel).where(
            PositionModel.status == "OPEN", PositionModel.mode == self.mode,
            PositionModel.symbol == self.symbol,
        )
        q = q.where(
            PositionModel.bot_id == self.bot_id if self.bot_id is not None
            else PositionModel.bot_id.is_(None)
        )
        async with self._sf() as s:
            p = (await s.execute(q.order_by(PositionModel.id.desc()).limit(1))).scalar_one_or_none()
        if p is None:
            return False
        self.engine.restore(
            Position(p.symbol, p.side, float(p.qty), float(p.entry_price),
                     sl=float(p.sl) if p.sl is not None else None,
                     tp=float(p.tp) if p.tp is not None else None),
            entry_fee=float(p.fee or 0),
        )
        self._pos_db_id = p.id
        return True

    def current_position(self):
        return self.engine.position

    async def submit(self, signal: Signal) -> None:
        await self._apply(self.engine.submit(signal, self._last_price))

    async def on_price(self, price: float) -> None:
        self._last_price = price
        if self._accounts:
            self._accounts.mark(self.symbol, price)
        await self._apply(self.engine.on_price(price))
        await self._broadcast_position(price)

    async def cancel(self, order_id: str | None = None) -> None:
        await self._apply(self.engine.submit(Signal("CANCEL", self.symbol), self._last_price))

    async def close(self, reason: str = "MANUAL") -> None:
        """Close the current position (manual intervention)."""
        await self._apply(self.engine.force_close(self._last_price, reason))

    async def seed_price(self, price: float) -> None:
        """Set the reference price for a manual MARKET order before submit."""
        self._last_price = price

    async def modify_sltp(self, sl: float | None, tp: float | None) -> None:
        p = self.engine.position
        if not p:
            return
        p.sl, p.tp = sl, tp
        if self._pos_db_id is not None:
            async with self._sf() as s:
                await s.execute(
                    update(PositionModel)
                    .where(PositionModel.id == self._pos_db_id)
                    .values(sl=sl, tp=tp)
                )
                await s.commit()
        await self._broadcast_position(self._last_price)

    # ---------- applying events ----------
    async def _apply(self, events: list[EngineEvent]) -> None:
        for e in events:
            if e.queued:
                await self._persist_queued(e.queued)
            if e.closed:
                await self._persist_close(e.closed)
            if e.opened:
                await self._persist_position_open()
            if e.filled_pending_id is not None:
                await self._mark_order(e.filled_pending_id, "FILLED")
            elif e.fill:  # market fill → create a new FILLED order
                await self._persist_order_filled(e.fill)
            if e.fill:
                await self._broadcast_order(e.fill, "FILLED")
            if e.opened:
                await self._broadcast_position(self._last_price)  # publish OPEN immediately
            if e.cancelled_ids:
                for oid in e.cancelled_ids:
                    await self._mark_order(oid, "CANCELLED")

    async def _persist_queued(self, order) -> None:
        async with self._sf() as s:
            row = OrderModel(
                bot_id=self.bot_id, source=self.source, mode=self.mode, symbol=self.symbol,
                side=order.side, type="LIMIT", qty=order.qty, price=order.price,
                status="NEW", sl=order.sl, tp=order.tp,
            )
            s.add(row)
            await s.flush()
            self._pending_db[order.oid] = row.id
            await s.commit()
        await self._broadcast_order(Fill(order.side, "LIMIT", order.qty, order.price), "NEW")

    async def _mark_order(self, oid: int, status: str) -> None:
        db_id = self._pending_db.pop(oid, None)
        if db_id is None:
            return
        async with self._sf() as s:
            vals: dict = {"status": status}
            if status == "FILLED":
                vals["filled_qty"] = (
                    await s.get(OrderModel, db_id)
                ).qty
                vals["position_id"] = self._pos_db_id  # the limit fill opened this position
                vals["intent"] = "OPEN"
            await s.execute(update(OrderModel).where(OrderModel.id == db_id).values(**vals))
            await s.commit()

    async def _persist_position_open(self) -> None:
        from app.account.risk import position_risk

        p = self.engine.position
        assert p is not None
        async with self._sf() as s:
            pos = PositionModel(
                account_id=self.account_id, fee=self.engine.entry_fee,
                margin=self.engine.margin(),
                risk_amount=position_risk(p.side, p.qty, p.entry_price, p.sl),
                bot_id=self.bot_id, mode=self.mode, symbol=self.symbol, side=p.side,
                qty=p.qty, entry_price=p.entry_price, sl=p.sl, tp=p.tp, init_sl=p.sl, status="OPEN",
                source=self.source, bot_ref=self.bot_id, **self.trade_meta,
            )
            s.add(pos)
            await s.flush()
            self._pos_db_id = pos.id
            await s.commit()
        if self._accounts and self.account_id is not None:
            await self._accounts.record_fee(
                self.account_id, self.engine.entry_fee, position_id=pos.id,
                bot_id=self.bot_id, symbol=self.symbol,
            )

    async def _persist_order_filled(self, fill: Fill) -> None:
        async with self._sf() as s:
            s.add(self._order_row(fill, "FILLED"))
            await s.commit()

    async def _persist_close(self, closed: Closed) -> None:
        async with self._sf() as s:
            if self._pos_db_id is not None:
                await s.execute(
                    update(PositionModel)
                    .where(PositionModel.id == self._pos_db_id)
                    .values(
                        status="CLOSED", exit_price=closed.exit_price, pnl=closed.pnl,
                        exit_reason=closed.reason, closed_at=datetime.now(UTC),
                        fee=closed.entry_fee + closed.exit_fee,
                    )
                )
            # the closing order = opposite side of the position
            close_side = "SELL" if closed.side == "LONG" else "BUY"
            s.add(
                OrderModel(
                    bot_id=self.bot_id, source=self.source, mode=self.mode, symbol=self.symbol,
                    side=close_side, type="MARKET", qty=closed.qty, price=closed.exit_price,
                    status="FILLED", filled_qty=closed.qty, avg_price=closed.exit_price,
                    fee=closed.exit_fee, position_id=self._pos_db_id, intent="CLOSE",
                )
            )
            await s.commit()
        if self._accounts and self.account_id is not None:
            await self._accounts.record_close(
                self.account_id, gross=closed.gross, exit_fee=closed.exit_fee,
                position_id=self._pos_db_id, bot_id=self.bot_id, symbol=self.symbol,
                reason=closed.reason,
            )
        self._pos_db_id = None
        await self._broadcast_position_closed(closed)

    def _order_row(self, fill: Fill, status: str) -> OrderModel:
        p = self.engine.position
        return OrderModel(
            bot_id=self.bot_id, source=self.source, mode=self.mode, symbol=self.symbol,
            side=fill.side, type=fill.type, qty=fill.qty, price=fill.price, status=status,
            filled_qty=fill.qty, avg_price=fill.price, fee=fill.fee,
            sl=p.sl if p else None, tp=p.tp if p else None,
            # market fills only ever open a position (closes go through _persist_close)
            position_id=self._pos_db_id if p else None, intent="OPEN" if p else None,
        )

    @property
    def pos_key(self) -> str:
        # stable key so the frontend can tell bot positions from manual orders.
        return f"bot:{self.bot_id}" if self.bot_id is not None else f"manual:{self.symbol}"

    # ---------- broadcast ----------
    async def _broadcast_order(self, fill: Fill, status: str) -> None:
        await self._bus.publish(
            "order.update",
            {
                "type": "order", "bot_id": self.bot_id, "source": self.source, "mode": self.mode,
                "symbol": self.symbol, "side": fill.side, "order_type": fill.type,
                "qty": fill.qty, "price": fill.price, "status": status,
            },
        )

    async def _broadcast_position(self, price: float) -> None:
        p = self.engine.position
        if not p:
            return
        await self._bus.publish(
            "position",
            {
                "type": "position", "key": self.pos_key, "bot_id": self.bot_id,
                "source": self.source, "mode": self.mode, "symbol": self.symbol,
                "side": p.side, "qty": p.qty, "entry_price": p.entry_price, "sl": p.sl, "tp": p.tp,
                "price": price, "pnl": self.engine.unrealized_pnl(price), "status": "OPEN",
            },
        )

    async def _broadcast_position_closed(self, closed: Closed) -> None:
        await self._bus.publish(
            "position",
            {
                "type": "position", "key": self.pos_key, "bot_id": self.bot_id,
                "source": self.source, "mode": self.mode, "symbol": self.symbol,
                "side": closed.side, "qty": 0, "entry_price": closed.entry_price,
                "price": closed.exit_price, "pnl": closed.pnl, "status": "CLOSED",
                "reason": closed.reason,
            },
        )
