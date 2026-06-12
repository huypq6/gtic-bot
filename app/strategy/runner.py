"""StrategyRunner (1 task/bot) + BotManager (vòng đời các bot).

Runner: subscribe kline → mỗi tick gọi executor.on_price (SL/TP/limit + PnL realtime);
mỗi nến ĐÓNG dựng Context gọi strategy.on_candle → đẩy Signal cho executor.
PAUSED: vẫn quản vị thế cũ (on_price) nhưng KHÔNG sinh tín hiệu mới (US-19).
"""

import asyncio
import logging
from collections import deque

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.execution.base import Executor
from app.execution.paper import PaperExecutor
from app.market.bus import EventBus
from app.market.store import get_klines
from app.strategy.base import Context, Strategy
from app.strategy.registry import discover, get

logger = logging.getLogger(__name__)


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
        lookback: int = 300,
    ) -> None:
        self.bot_id = bot_id
        self.strategy = strategy
        self.executor = executor
        self._bus = bus
        self.symbol = symbol
        self.tf = tf
        self._sf = session_factory
        self.status = "RUNNING"
        self._candles: deque = deque(maxlen=lookback)
        self._task: asyncio.Task | None = None
        self._stop = False

    async def start(self) -> None:
        # seed nến lịch sử để indicator có đủ dữ liệu ngay.
        async with self._sf() as s:
            hist = await get_klines(s, self.symbol, self.tf, limit=self._candles.maxlen or 300)
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
                    self._candles.append(msg)
                    if self.status == "RUNNING":
                        ctx = Context(
                            symbol=self.symbol,
                            price=price,
                            candles=list(self._candles),
                            position=self.executor.current_position(),
                        )
                        for sig in self.strategy.on_candle(ctx):
                            await self.executor.submit(sig)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — không để 1 lỗi giết runner
            logger.exception("runner bot %s lỗi", self.bot_id)
        finally:
            self._bus.unsubscribe(f"kline.{self.symbol}.{self.tf}", sub)


class BotManager:
    """Quản lý các runner đang chạy. Lưu ở app.state, dùng bởi API + lifespan."""

    def __init__(self, bus: EventBus, session_factory: async_sessionmaker) -> None:
        self._bus = bus
        self._sf = session_factory
        self._runners: dict[int, StrategyRunner] = {}

    async def start_bot(
        self, bot_id: int, strategy_name: str, strategy_version: str,
        params: dict, symbol: str, tf: str, mode: str,
    ) -> None:
        if mode != "PAPER":
            raise ValueError(f"mode {mode} chưa hỗ trợ ở P2 (PAPER only)")
        discover()
        strat = get(strategy_name, strategy_version)(params)
        executor = PaperExecutor(bot_id, symbol, mode, self._bus, self._sf)
        runner = StrategyRunner(bot_id, strat, executor, self._bus, symbol, tf, self._sf)
        await runner.start()
        self._runners[bot_id] = runner

    def set_status(self, bot_id: int, status: str) -> None:
        r = self._runners.get(bot_id)
        if r:
            r.status = status

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
