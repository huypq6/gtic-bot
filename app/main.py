"""FastAPI entrypoint — single process, asyncio.

Lifespan spawn các asyncio task realtime: MarketFeed (Binance WS → EventBus),
persister (ghi nến đóng vào DB), tracker trạng thái feed. P2+ thêm StrategyRunner,
Scanner...

Prod (1 endpoint): nếu `frontend/dist` tồn tại → mount StaticFiles tại "/" để
FastAPI phục vụ cả UI lẫn API trên cùng cổng. Dev: Vite (:5173) proxy sang đây.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.backtest import router as backtest_router
from app.api.routes import router as api_router
from app.api.trading import router as trading_router
from app.api.ws import WSGateway
from app.config import settings
from app.db import async_session
from app.market.bus import EventBus
from app.market.feed import MarketFeed
from app.market.store import persist_closed_klines
from app.orders.manager import OrderManager
from app.scanner.research import run_scanner
from app.strategy.runner import BotManager, ManualTrader

logging.basicConfig(level=logging.INFO)

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    bus = EventBus()
    gateway = WSGateway(bus)
    feed = MarketFeed(bus, symbols=settings.default_symbols, tf=settings.default_tf)
    order_manager = OrderManager(async_session)
    bot_manager = BotManager(bus, async_session, order_manager)
    manual_trader = ManualTrader(bus, async_session)

    app.state.bus = bus
    app.state.gateway = gateway
    app.state.feed = feed
    app.state.order_manager = order_manager
    app.state.bot_manager = bot_manager
    app.state.manual_trader = manual_trader

    tasks = [
        asyncio.create_task(gateway.track_feed_status(), name="feed-status-tracker"),
    ]
    if settings.feed_autostart:
        tasks.append(asyncio.create_task(feed.run(), name="market-feed"))
        tasks.append(
            asyncio.create_task(
                persist_closed_klines(bus, async_session), name="kline-persister"
            )
        )
        tasks.append(asyncio.create_task(run_scanner(bus, async_session), name="scanner"))
        tasks.append(
            asyncio.create_task(_feed_autopause_watcher(bus, bot_manager), name="feed-autopause")
        )
        await _restore_running_bots(bot_manager)
    try:
        yield
    finally:
        await bot_manager.stop_all()
        await manual_trader.stop_all()
        feed.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _feed_autopause_watcher(bus: EventBus, bot_manager: BotManager) -> None:
    """Mất feed (DOWN) → auto-pause mọi bot RUNNING (US-27). Nối lại KHÔNG tự resume."""
    sub = bus.subscribe("feed")
    while True:
        msg = await sub.get()
        if msg.get("status") == "DOWN":
            n = await bot_manager.pause_all_running("feed DOWN")
            if n:
                logging.warning("feed DOWN → auto-pause %d bot", n)


async def _restore_running_bots(bot_manager: BotManager) -> None:
    """Khởi động lại các bot đang RUNNING sau khi process restart."""
    from sqlalchemy import select

    from app.orders.models import Bot, StrategyModel

    try:
        async with async_session() as s:
            rows = (
                await s.execute(
                    select(Bot, StrategyModel)
                    .join(StrategyModel, Bot.strategy_id == StrategyModel.id)
                    .where(Bot.status == "RUNNING")
                )
            ).all()
        for bot, strat in rows:
            await bot_manager.start_bot(
                bot.id, strat.name, strat.version, bot.params, bot.symbol, bot.tf, bot.mode
            )
            logging.info("restore bot %s (%s)", bot.id, strat.name)
    except Exception:  # noqa: BLE001
        logging.exception("không restore được bot đang chạy")


app = FastAPI(title="GTIC Trading Bot", version="0.1.0", lifespan=lifespan)

app.include_router(api_router)
app.include_router(trading_router)
app.include_router(backtest_router)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.app.state.gateway.handle(websocket)


class SPAStaticFiles(StaticFiles):
    """Serve static; fallback index.html cho client-side routes (vd /trade)."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


# Prod: serve built frontend. Chỉ mount khi dist tồn tại (dev dùng Vite proxy).
if FRONTEND_DIST.is_dir():
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
