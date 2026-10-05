"""FastAPI entrypoint — single process, asyncio.

The lifespan spawns the realtime asyncio tasks: MarketFeed (Binance WS → EventBus),
persister (writes closed candles to the DB), feed status tracker. P2+ adds StrategyRunner,
Scanner...

Prod (single endpoint): if `frontend/dist` exists → mount StaticFiles at "/" so
FastAPI serves both the UI and the API on the same port. Dev: Vite (:5173) proxies here.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.account.service import AccountService, run_exchange_sync
from app.api.accounts import router as accounts_router
from app.api.backtest import router as backtest_router
from app.api.exchange import router as exchange_router
from app.api.modes import router as modes_router
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
    from app.market.watchlist import ensure_seeded

    bus = EventBus()
    gateway = WSGateway(bus)
    watch = await ensure_seeded(async_session, settings.default_symbols)
    feed = MarketFeed(bus, symbols=watch, tf=settings.default_tf)
    order_manager = OrderManager(async_session)
    accounts = AccountService(async_session, order_manager)
    bot_manager = BotManager(
        bus, async_session, order_manager, feed=feed, backfill=settings.feed_autostart,
        accounts=accounts,
    )
    manual_trader = ManualTrader(bus, async_session, accounts)

    app.state.bus = bus
    app.state.gateway = gateway
    app.state.feed = feed
    app.state.order_manager = order_manager
    app.state.accounts = accounts
    app.state.bot_manager = bot_manager
    app.state.manual_trader = manual_trader

    tasks = [
        asyncio.create_task(gateway.track_feed_status(), name="feed-status-tracker"),
        # P9b: TESTNET/LIVE account balance/ledger from the exchange (no exchange account → no-op)
        asyncio.create_task(run_exchange_sync(accounts), name="exchange-account-sync"),
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
        from app.execution.clients import close_all

        await close_all()
        feed.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _feed_autopause_watcher(bus: EventBus, bot_manager: BotManager) -> None:
    """Feed lost (DOWN) → auto-pause every RUNNING bot (US-27). Reconnect does NOT resume."""
    sub = bus.subscribe("feed")
    while True:
        msg = await sub.get()
        if msg.get("status") == "DOWN":
            n = await bot_manager.pause_all_running("feed DOWN")
            if n:
                logging.warning("feed DOWN → auto-pause %d bot", n)


async def _restore_running_bots(bot_manager: BotManager) -> None:
    """Restart RUNNING bots after a process restart."""
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
                bot.id, strat.name, strat.version, bot.params, bot.symbol, bot.tf, bot.mode,
                account_id=bot.account_id, sizing=bot.sizing,
            )
            logging.info("restore bot %s (%s)", bot.id, strat.name)
    except Exception:  # noqa: BLE001
        logging.exception("failed to restore running bots")


app = FastAPI(title="GTIC Trading Bot", version="0.1.0", lifespan=lifespan)

# CORS — allow access from other origins (mobile/LAN). allow_credentials=False
# since there is no auth cookie yet → "*" is safe.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(trading_router)
app.include_router(backtest_router)
app.include_router(accounts_router)
app.include_router(modes_router)
app.include_router(exchange_router)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.app.state.gateway.handle(websocket)


class SPAStaticFiles(StaticFiles):
    """Serve static; fallback to index.html for client-side routes (e.g. /trade)."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


# Prod: serve built frontend. Only mounted when dist exists (dev uses the Vite proxy).
if FRONTEND_DIST.is_dir():
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
