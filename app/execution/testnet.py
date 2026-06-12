"""TestnetExecutor — đặt lệnh THẬT trên Binance testnet, cùng interface Executor.

Tái dùng **PaperEngine** cho state vị thế + PnL + kiểm SL/TP (nhất quán paper/live),
nhưng MỌI fill vào/ra là lệnh thật gửi sàn (lưu `ext_id`). SL/TP quản client-side:
on_price phát hiện chạm → gửi lệnh market đóng thật. LIMIT đặt trên sàn + auto-cancel
theo `timeout` (NFR US-26).

`client` inject được (BinanceClient hoặc fake) để test không cần key.
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.execution.base import Executor
from app.execution.paper_engine import PaperEngine
from app.market.bus import EventBus
from app.orders.models import OrderModel, PositionModel
from app.strategy.base import Signal

logger = logging.getLogger(__name__)


class TestnetExecutor(Executor):
    __test__ = False  # tránh pytest hiểu nhầm là test class (tên bắt đầu 'Test')

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
            fill = resp["price"]
            ext = resp["orderId"]
            await self._apply_fill(a, signal.size, fill, ext, signal.sl, signal.tp)

    async def on_price(self, price: float) -> None:
        self._last_price = price
        reason = self.engine.sltp_reason(price)
        if reason:
            await self._market_close(reason)
        await self._broadcast_position(price)

    async def cancel(self, order_id: str | None = None) -> None:
        # order_id = ext_id của lệnh chờ.
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
        if self._pos_db_id is not None:
            async with self._sf() as s:
                await s.execute(
                    update(PositionModel)
                    .where(PositionModel.id == self._pos_db_id)
                    .values(sl=sl, tp=tp)
                )
                await s.commit()
        await self._broadcast_position(self._last_price)

    async def close(self, reason: str = "MANUAL") -> None:
        await self._market_close(reason)

    # ---------- nội bộ ----------
    async def _apply_fill(
        self, side: str, qty: float, price: float, ext: str,
        sl: float | None, tp: float | None,
    ) -> None:
        """Đăng ký fill thật vào engine (mở/flip) + persist + broadcast."""
        events = self.engine.submit(
            Signal(side, self.symbol, qty, "MARKET", sl=sl, tp=tp), price
        )
        for e in events:
            if e.closed:
                await self._persist_close(e.closed, ext)
            if e.opened:
                await self._persist_position_open(ext)
                await self._broadcast_position(price)
        await self._broadcast_order(side, "MARKET", qty, price, "FILLED")

    async def _market_close(self, reason: str) -> None:
        pos = self.engine.position
        if not pos:
            return
        side = "SELL" if pos.side == "LONG" else "BUY"
        resp = await self._client.market_order(self.symbol, side, pos.qty)
        fill = resp["price"]
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
            logger.info("auto-cancel limit %s sau %.0fs", ext, self._timeout)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("auto-cancel %s lỗi", ext)
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
        p = self.engine.position
        assert p is not None
        async with self._sf() as s:
            pos = PositionModel(
                bot_id=self.bot_id, mode=self.mode, symbol=self.symbol, side=p.side,
                qty=p.qty, entry_price=p.entry_price, sl=p.sl, tp=p.tp, status="OPEN",
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
                        closed_at=datetime.now(UTC),
                    )
                )
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
