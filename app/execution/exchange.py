"""ExchangeExecutor — places REAL orders on the exchange (Binance testnet OR live), with the same
Executor interface. Shared by TESTNET + LIVE (only the client + mode differ); factory +
guards live in testnet.py / live.py.

Reuses **PaperEngine** for position state + PnL + SL/TP checks (consistent paper/live),
but EVERY entry/exit fill is a real order sent to the exchange (stored in `ext_id`). SL/TP is
managed client-side: on_price detects a hit → sends a real market close. LIMIT orders are placed
on the exchange + auto-cancelled per `timeout` (NFR US-26).

`client` is injectable (BinanceFuturesClient or a fake) so tests don't need keys.

P9b — Futures client (has `protect`): SL/TP placed ON THE EXCHANGE (STOP/TAKE_PROFIT_MARKET
closePosition) instead of only client-side → positions stay protected if the app dies. Reversal =
close (reduceOnly) then open new (one-way mode doesn't flip by itself). Periodically reconciles
the exchange position: closed on the exchange (SL/TP/liquidation/manual close in the Binance app)
→ record the close from the real fill. The exchange account's cash ledger is NOT written here
(avoids duplicates) — AccountService imports it from the exchange's income history.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.execution.base import Executor
from app.execution.paper_engine import PaperEngine
from app.market.bus import EventBus
from app.orders.models import OrderModel, PositionModel
from app.strategy.base import Position, Signal

logger = logging.getLogger(__name__)


class ExchangeExecutor(Executor):
    def __init__(
        self,
        bot_id: int | None,
        symbol: str,
        mode: str,
        bus: EventBus,
        session_factory: async_sessionmaker,
        client,
        timeout: float | None = None,
        fee_rate: float = 0.0,
    ) -> None:
        self.engine = PaperEngine(symbol, fee_rate)
        self.bot_id = bot_id
        self.symbol = symbol
        self.mode = mode
        self.source = "BOT" if bot_id is not None else "MANUAL"
        self._bus = bus
        self._sf = session_factory
        self._client = client
        self._timeout = timeout
        self._last_price = 0.0
        self._pos_db_id: int | None = None
        self._cancel_tasks: dict[str, asyncio.Task] = {}
        # P9b
        self._futures = hasattr(client, "protect")
        self._protect: dict = {}  # {"sl": algoId, "tp": algoId} currently placed on the exchange
        self._opened_ms: int | None = None
        self._last_reconcile = 0.0
        self.reconcile_every = 5.0  # seconds between exchange position polls
        self.account_id: int | None = None
        self._accounts = None

    def attach_account(self, account, service) -> None:
        """Attach the exchange account: set leverage on the exchange before orders + estimated
        fee for unrealized PnL."""
        self.account_id = account.id
        self._accounts = service
        self.engine.leverage = max(1.0, float(account.leverage))
        self.engine.fee_rate = float(account.taker_fee)
        self.engine.maker_fee = float(account.maker_fee)

    def current_position(self):
        return self.engine.position

    async def submit(self, signal: Signal) -> None:
        a = signal.action
        if a == "CANCEL":
            return
        if a == "CLOSE":
            await self._market_close("SIGNAL")
            return
        if a not in ("BUY", "SELL"):
            return
        desired = "LONG" if a == "BUY" else "SHORT"
        pos = self.engine.position
        if pos and pos.side == desired:
            return  # same side → no pyramiding
        if pos and self._futures:
            await self._market_close("SIGNAL")  # one-way mode: fully close, then open the new side
        if self._futures:
            await self._client.ensure_leverage(self.symbol, self.engine.leverage)

        if signal.order_type == "LIMIT" and signal.price is not None:
            resp = await self._client.limit_order(self.symbol, a, signal.size, signal.price)
            ext = resp["orderId"]
            await self._persist_order(
                a, "LIMIT", signal.size, signal.price, "NEW", ext, signal.sl, signal.tp
            )
            await self._broadcast_order(a, "LIMIT", signal.size, signal.price, "NEW")
            if self._timeout:
                self._cancel_tasks[ext] = asyncio.create_task(self._auto_cancel(ext))
        else:
            resp = await self._client.market_order(self.symbol, a, signal.size)
            fill = resp["price"] or self._last_price
            qty = resp.get("qty") or signal.size  # exchange rounds to stepSize
            ext = resp["orderId"]
            await self._apply_fill(a, qty, fill, ext, signal.sl, signal.tp)

    async def on_price(self, price: float) -> None:
        self._last_price = price
        if self._accounts:
            self._accounts.mark(self.symbol, price)
        if self._futures and self.engine.position:
            now = time.monotonic()
            if now - self._last_reconcile >= self.reconcile_every:
                self._last_reconcile = now
                await self.reconcile()
        # Client-side SL/TP is only a FALLBACK for legs not yet placed on the exchange.
        reason = self.engine.sltp_reason(price)
        if reason and not self._protect.get(reason.lower()):
            await self._market_close(reason)
        await self._broadcast_position(price)

    async def reconcile(self) -> None:
        """Exchange position went to 0 while the app still holds it → SL/TP/liquidation was
        filled on the exchange."""
        p = self.engine.position
        if not p:
            return
        try:
            ex = await self._client.position(self.symbol)
            if abs(ex["amt"]) > 0:
                return
            fill = await self._client.last_close_fill(self.symbol, self._opened_ms or 0)
        except Exception:  # noqa: BLE001 — flaky network: retry next time
            logger.warning("position reconciliation %s failed", self.symbol, exc_info=True)
            return
        price = (fill or {}).get("price") or self._last_price
        reason = "EXTERNAL"
        for key, lvl in (("SL", p.sl), ("TP", p.tp)):
            if lvl and abs(price - lvl) / lvl < 0.005:
                reason = key
        await self._client.cancel_protection(self.symbol, self._protect)
        self._protect = {}
        for e in self.engine.force_close(price, reason):
            if e.closed:
                if fill:  # real exchange figures replace the estimate
                    e.closed.gross = fill["realized"]
                    e.closed.exit_fee = fill["fee"]
                    e.closed.pnl = fill["realized"] - fill["fee"] - e.closed.entry_fee
                await self._persist_close(e.closed, (fill or {}).get("orderId", ""))
        logger.info("position %s closed on the exchange (%s) @ %s", self.symbol, reason, price)

    async def restore_open(self) -> bool:
        """After restart: reload the bot's OPEN position; if the exchange already closed it →
        record the close from the exchange."""
        q = select(PositionModel).where(
            PositionModel.status == "OPEN", PositionModel.mode == self.mode,
            PositionModel.symbol == self.symbol,
        )
        q = q.where(
            PositionModel.bot_id == self.bot_id if self.bot_id is not None
            else PositionModel.bot_id.is_(None)
        )
        q = q.order_by(PositionModel.id.desc()).limit(1)
        async with self._sf() as s:
            row = (await s.execute(q)).scalar_one_or_none()
        if row is None:
            return False

        def f(v):
            return float(v) if v is not None else None

        self.engine.restore(
            Position(row.symbol, row.side, float(row.qty), float(row.entry_price),
                     sl=f(row.sl), tp=f(row.tp)),
            entry_fee=float(row.fee or 0),
        )
        self._pos_db_id = row.id
        self._protect = dict(row.ext_protect or {})
        self._opened_ms = int(row.opened_at.timestamp() * 1000) if row.opened_at else None
        if self._futures:
            await self.reconcile()  # closed while the app was down?
        return self.engine.position is not None

    async def cancel(self, order_id: str | None = None) -> None:
        # order_id = ext_id of the pending order.
        if not order_id:
            return
        await self._client.cancel(self.symbol, order_id)
        await self._mark_order_by_ext(order_id, "CANCELLED")
        t = self._cancel_tasks.pop(order_id, None)
        if t:
            t.cancel()

    async def modify_sltp(self, sl: float | None, tp: float | None) -> None:
        p = self.engine.position
        if not p:
            return
        p.sl, p.tp = sl, tp
        if self._futures:  # replace protective orders on the exchange
            await self._client.cancel_protection(self.symbol, self._protect)
            self._protect = await self._safe_protect(p)
        if self._pos_db_id is not None:
            async with self._sf() as s:
                await s.execute(
                    update(PositionModel)
                    .where(PositionModel.id == self._pos_db_id)
                    .values(sl=sl, tp=tp, ext_protect=self._protect or None)
                )
                await s.commit()
        await self._broadcast_position(self._last_price)

    async def close(self, reason: str = "MANUAL") -> None:
        await self._market_close(reason)

    # ---------- internal ----------
    async def _apply_fill(
        self, side: str, qty: float, price: float, ext: str,
        sl: float | None, tp: float | None,
    ) -> None:
        """Register a real fill into the engine (open/flip) + persist + broadcast."""
        events = self.engine.submit(
            Signal(side, self.symbol, qty, "MARKET", sl=sl, tp=tp), price
        )
        for e in events:
            if e.closed:
                await self._persist_close(e.closed, ext)
            if e.opened:
                self._opened_ms = int(time.time() * 1000)
                if self._futures:
                    self._protect = await self._safe_protect(e.opened)
                await self._persist_position_open(ext)
                await self._broadcast_position(price)
        await self._broadcast_order(side, "MARKET", qty, price, "FILLED")

    async def _safe_protect(self, p) -> dict:
        """Place SL/TP on the exchange; on error → warn + rely on client-side SL/TP (on_price)."""
        if p.sl is None and p.tp is None:
            return {}
        try:
            return await self._client.protect(self.symbol, p.side, p.sl, p.tp)
        except Exception as e:  # noqa: BLE001
            logger.exception("placing SL/TP on the exchange failed for %s", self.symbol)
            await self._bus.publish(
                "risk", {"type": "risk", "bot_id": self.bot_id, "symbol": self.symbol,
                         "reason": f"could not place SL/TP on the exchange ({e}) — "
                                   "the app will close it instead"},
            )
            return {}

    async def _market_close(self, reason: str) -> None:
        pos = self.engine.position
        if not pos:
            return
        side = "SELL" if pos.side == "LONG" else "BUY"
        if self._futures:
            await self._client.cancel_protection(self.symbol, self._protect)
            self._protect = {}
            resp = await self._client.market_order(self.symbol, side, pos.qty, reduce_only=True)
        else:
            resp = await self._client.market_order(self.symbol, side, pos.qty)
        fill = resp["price"] or self._last_price
        ext = resp["orderId"]
        events = self.engine.force_close(fill, reason)
        for e in events:
            if e.closed:
                await self._persist_close(e.closed, ext)
        await self._broadcast_order(side, "MARKET", pos.qty, fill, "FILLED")

    async def _auto_cancel(self, ext: str) -> None:
        try:
            await asyncio.sleep(self._timeout)
            await self._client.cancel(self.symbol, ext)
            await self._mark_order_by_ext(ext, "CANCELLED")
            await self._bus.publish(
                "order.update",
                {"type": "order", "bot_id": self.bot_id, "symbol": self.symbol,
                 "status": "CANCELLED", "ext_id": ext, "reason": "TIMEOUT"},
            )
            logger.info("auto-cancel limit %s after %.0fs", ext, self._timeout)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("auto-cancel %s failed", ext)
        finally:
            self._cancel_tasks.pop(ext, None)

    async def _persist_order(
        self, side: str, otype: str, qty: float, price: float | None,
        status: str, ext: str, sl: float | None = None, tp: float | None = None,
    ) -> None:
        async with self._sf() as s:
            s.add(
                OrderModel(
                    bot_id=self.bot_id, ext_id=ext, source=self.source, mode=self.mode,
                    symbol=self.symbol, side=side, type=otype, qty=qty, price=price,
                    status=status, sl=sl, tp=tp,
                    filled_qty=qty if status == "FILLED" else 0,
                    avg_price=price if status == "FILLED" else None,
                )
            )
            await s.commit()

    async def _persist_position_open(self, ext: str) -> None:
        from app.account.risk import position_risk

        p = self.engine.position
        assert p is not None
        async with self._sf() as s:
            pos = PositionModel(
                account_id=self.account_id, fee=self.engine.entry_fee,
                margin=self.engine.margin(), ext_protect=self._protect or None,
                risk_amount=position_risk(p.side, p.qty, p.entry_price, p.sl),
                bot_id=self.bot_id, mode=self.mode, symbol=self.symbol, side=p.side,
                qty=p.qty, entry_price=p.entry_price, sl=p.sl, tp=p.tp, init_sl=p.sl, status="OPEN",
                source=self.source, bot_ref=self.bot_id, **self.trade_meta,
            )
            s.add(pos)
            s.add(
                OrderModel(
                    bot_id=self.bot_id, ext_id=ext, source=self.source, mode=self.mode,
                    symbol=self.symbol, side="BUY" if p.side == "LONG" else "SELL",
                    type="MARKET", qty=p.qty, price=p.entry_price, status="FILLED",
                    filled_qty=p.qty, avg_price=p.entry_price, sl=p.sl, tp=p.tp,
                )
            )
            await s.flush()
            self._pos_db_id = pos.id
            await s.commit()

    async def _persist_close(self, closed, ext: str) -> None:
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
            if ext:
                s.add(OrderModel(
                    bot_id=self.bot_id, ext_id=ext, source=self.source, mode=self.mode,
                    symbol=self.symbol, side="SELL" if closed.side == "LONG" else "BUY",
                    type="MARKET", qty=closed.qty, price=closed.exit_price, status="FILLED",
                    filled_qty=closed.qty, avg_price=closed.exit_price, fee=closed.exit_fee,
                ))
            await s.commit()
        self._pos_db_id = None
        await self._bus.publish(
            "position",
            {"type": "position", "key": self._pos_key(), "bot_id": self.bot_id,
             "source": self.source, "mode": self.mode, "symbol": self.symbol,
             "side": closed.side, "qty": 0, "entry_price": closed.entry_price,
             "price": closed.exit_price, "pnl": closed.pnl, "status": "CLOSED",
             "reason": closed.reason},
        )

    async def _mark_order_by_ext(self, ext: str, status: str) -> None:
        async with self._sf() as s:
            await s.execute(
                update(OrderModel).where(OrderModel.ext_id == ext).values(status=status)
            )
            await s.commit()

    def _pos_key(self) -> str:
        return f"bot:{self.bot_id}" if self.bot_id is not None else f"manual:{self.symbol}"

    async def _broadcast_order(
        self, side: str, otype: str, qty: float, price: float | None, status: str
    ) -> None:
        await self._bus.publish(
            "order.update",
            {"type": "order", "bot_id": self.bot_id, "source": self.source, "mode": self.mode,
             "symbol": self.symbol, "side": side, "order_type": otype, "qty": qty,
             "price": price, "status": status},
        )

    async def _broadcast_position(self, price: float) -> None:
        p = self.engine.position
        if not p:
            return
        await self._bus.publish(
            "position",
            {"type": "position", "key": self._pos_key(), "bot_id": self.bot_id,
             "source": self.source, "mode": self.mode, "symbol": self.symbol,
             "side": p.side, "qty": p.qty, "entry_price": p.entry_price, "sl": p.sl, "tp": p.tp,
             "price": price, "pnl": self.engine.unrealized_pnl(price), "status": "OPEN"},
        )
