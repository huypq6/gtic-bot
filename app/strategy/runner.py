"""StrategyRunner (1 task/bot) + BotManager (vòng đời các bot).

Runner: subscribe kline → mỗi tick gọi executor.on_price (SL/TP/limit + PnL realtime);
mỗi nến ĐÓNG dựng Context gọi strategy.on_candle → đẩy Signal cho executor.
PAUSED: vẫn quản vị thế cũ (on_price) nhưng KHÔNG sinh tín hiệu mới (US-19).
"""

import asyncio
import logging
import time
from collections import deque

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.execution.base import Executor
from app.execution.paper import PaperExecutor
from app.market.bus import EventBus
from app.market.store import get_klines, sync_historical
from app.strategy.base import Context, Strategy
from app.strategy.registry import discover, get

logger = logging.getLogger(__name__)

_TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000,
          "4h": 14_400_000, "1d": 86_400_000}


class StrategyRunner:
    def __init__(
        self,
        bot_id: int,
        strategy: Strategy,
        executor: Executor,
        bus: EventBus,
        symbol: str,
        tf: str,
        session_factory: async_sessionmaker,
        order_manager=None,
        mode: str = "PAPER",
        lookback: int = 300,
        backfill: bool = False,
    ) -> None:
        self.bot_id = bot_id
        self.strategy = strategy
        self.executor = executor
        self._bus = bus
        self.symbol = symbol
        self.tf = tf
        self._sf = session_factory
        self._om = order_manager
        self.mode = mode
        self.status = "RUNNING"
        self._candles: deque = deque(maxlen=lookback)
        self._task: asyncio.Task | None = None
        self._stop = False
        self._backfill = backfill
        self.last_candle_ts: int | None = None  # open-time nến đóng cuối nhận được (quan sát)

    async def start(self) -> None:
        # seed nến lịch sử để indicator có đủ dữ liệu ngay. Backfill từ Binance trước để
        # lịch sử liền mạch tới hiện tại (DB có thể cũ/đứt đoạn nếu feed chưa từng stream tf này).
        n = self._candles.maxlen or 300
        tf_ms = _TF_MS.get(self.tf, 60_000)
        if self._backfill:
            try:
                async with self._sf() as s:
                    await sync_historical(
                        s, self.symbol, self.tf, f"{(n + 5) * tf_ms // 60_000} minutes ago UTC"
                    )
            except Exception:  # noqa: BLE001 — offline vẫn chạy với lịch sử DB
                logger.warning("backfill %s %s thất bại", self.symbol, self.tf, exc_info=True)
        async with self._sf() as s:
            hist = await get_klines(s, self.symbol, self.tf, limit=n)
        now_ms = int(time.time() * 1000)
        hist = [c for c in hist if c["ts"] + tf_ms <= now_ms]  # bỏ nến chưa đóng
        self._candles.extend(hist)
        self._task = asyncio.create_task(self.run(), name=f"runner-{self.bot_id}")

    def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()

    async def run(self) -> None:
        sub = self._bus.subscribe(f"kline.{self.symbol}.{self.tf}")
        try:
            while not self._stop:
                msg = await sub.get()
                price = msg["close"]
                await self.executor.on_price(price)
                if msg.get("closed"):
                    last = self._candles[-1]["ts"] if self._candles else None
                    if last is not None and msg["ts"] <= last:
                        if msg["ts"] < last:
                            continue  # nến cũ (reconnect) → bỏ
                        self._candles[-1] = msg
                    else:
                        self._candles.append(msg)
                    self.last_candle_ts = msg["ts"]
                    if self.status == "RUNNING":
                        ctx = Context(
                            symbol=self.symbol,
                            price=price,
                            candles=list(self._candles),
                            position=self.executor.current_position(),
                        )
                        for sig in self.strategy.on_candle(ctx):
                            # NFR: ghi audit TRƯỚC khi executor tác động.
                            if self._om:
                                await self._om.execute(
                                    source="BOT", action=sig.action, mode=self.mode,
                                    bot_id=self.bot_id, symbol=self.symbol,
                                    detail={"size": sig.size, "type": sig.order_type},
                                    do=lambda s=sig: self.executor.submit(s),
                                )
                            else:
                                await self.executor.submit(sig)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — không để 1 lỗi giết runner
            logger.exception("runner bot %s lỗi", self.bot_id)
        finally:
            self._bus.unsubscribe(f"kline.{self.symbol}.{self.tf}", sub)


class BotManager:
    """Quản lý các runner đang chạy. Lưu ở app.state, dùng bởi API + lifespan."""

    def __init__(
        self, bus: EventBus, session_factory: async_sessionmaker, order_manager=None,
        feed=None, backfill: bool = False,
    ) -> None:
        self._bus = bus
        self._sf = session_factory
        self._om = order_manager
        self._feed = feed  # MarketFeed: bot đăng ký stream kline (symbol, tf) của nó
        self._backfill = backfill
        self._runners: dict[int, StrategyRunner] = {}

    async def start_bot(
        self, bot_id: int, strategy_name: str, strategy_version: str,
        params: dict, symbol: str, tf: str, mode: str,
    ) -> None:
        discover()
        strat = get(strategy_name, strategy_version)(params)
        executor = await self._make_executor(bot_id, symbol, mode, params)
        if self._feed is not None:
            await self._feed.ensure_kline(symbol, tf)
        runner = StrategyRunner(
            bot_id, strat, executor, self._bus, symbol, tf, self._sf,
            order_manager=self._om, mode=mode, backfill=self._backfill,
        )
        await runner.start()
        self._runners[bot_id] = runner

    async def _make_executor(
        self, bot_id: int | None, symbol: str, mode: str, params: dict
    ) -> Executor:
        if mode == "PAPER":
            return PaperExecutor(bot_id, symbol, mode, self._bus, self._sf)
        timeout = params.get("timeout")
        if mode == "TESTNET":
            from app.execution.testnet import make_testnet_executor

            return await make_testnet_executor(
                bot_id, symbol, self._bus, self._sf, settings, timeout
            )
        if mode == "LIVE":
            from app.execution.live import make_live_executor

            return await make_live_executor(
                bot_id, symbol, self._bus, self._sf, settings, timeout
            )
        raise ValueError(f"mode {mode} không hợp lệ")

    def last_candle_ts(self, bot_id: int) -> int | None:
        r = self._runners.get(bot_id)
        return r.last_candle_ts if r else None

    def get_executor(self, bot_id: int) -> Executor | None:
        r = self._runners.get(bot_id)
        return r.executor if r else None

    def set_status(self, bot_id: int, status: str) -> None:
        r = self._runners.get(bot_id)
        if r:
            r.status = status

    async def pause_all_running(self, reason: str) -> int:
        """Auto-pause mọi bot đang RUNNING (vd mất feed — US-27). Ghi audit SYSTEM."""
        from sqlalchemy import update as sa_update

        from app.orders.models import Bot

        paused = [r for r in self._runners.values() if r.status == "RUNNING"]
        for r in paused:
            r.status = "PAUSED"
            async with self._sf() as s:
                await s.execute(sa_update(Bot).where(Bot.id == r.bot_id).values(status="PAUSED"))
                await s.commit()
            if self._om:
                await self._om.write_audit(
                    source="SYSTEM", action="PAUSE", mode=r.mode,
                    bot_id=r.bot_id, symbol=r.symbol, detail={"reason": reason},
                )
        return len(paused)

    async def stop_bot(self, bot_id: int) -> None:
        r = self._runners.pop(bot_id, None)
        if r:
            r.stop()

    def is_running(self, bot_id: int) -> bool:
        return bot_id in self._runners

    async def stop_all(self) -> None:
        for r in list(self._runners.values()):
            r.stop()
        self._runners.clear()


class ManualTrader:
    """Quản lý lệnh tay rời (không thuộc bot). 1 PaperExecutor/symbol, subscribe
    ticker để cập nhật giá + check SL/TP/limit. bot_id=None, source=MANUAL."""

    def __init__(self, bus: EventBus, session_factory: async_sessionmaker) -> None:
        self._bus = bus
        self._sf = session_factory
        self._ex: dict[str, PaperExecutor] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def ensure(self, symbol: str, mode: str = "PAPER") -> PaperExecutor:
        if symbol not in self._ex:
            ex = PaperExecutor(None, symbol, mode, self._bus, self._sf)
            self._ex[symbol] = ex
            self._tasks[symbol] = asyncio.create_task(
                self._price_loop(symbol, ex), name=f"manual-{symbol}"
            )
        return self._ex[symbol]

    def executor_for(self, symbol: str) -> PaperExecutor | None:
        return self._ex.get(symbol)

    async def _price_loop(self, symbol: str, ex: PaperExecutor) -> None:
        sub = self._bus.subscribe(f"ticker.{symbol}")
        try:
            while True:
                msg = await sub.get()
                await ex.on_price(msg["price"])
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("manual trader %s lỗi", symbol)
        finally:
            self._bus.unsubscribe(f"ticker.{symbol}", sub)

    async def stop_all(self) -> None:
        for t in self._tasks.values():
            t.cancel()
        self._tasks.clear()
        self._ex.clear()
