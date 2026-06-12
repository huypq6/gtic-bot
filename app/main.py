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

from app.api.routes import router as api_router
from app.api.ws import WSGateway
from app.config import settings
from app.db import async_session
from app.market.bus import EventBus
from app.market.feed import MarketFeed
from app.market.store import persist_closed_klines

logging.basicConfig(level=logging.INFO)

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    bus = EventBus()
    gateway = WSGateway(bus)
    feed = MarketFeed(bus, symbols=settings.default_symbols, tf=settings.default_tf)

    app.state.bus = bus
    app.state.gateway = gateway
    app.state.feed = feed

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
    try:
        yield
    finally:
        feed.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="GTIC Trading Bot", version="0.1.0", lifespan=lifespan)

app.include_router(api_router)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.app.state.gateway.handle(websocket)


# Prod: serve built frontend. Chỉ mount khi dist tồn tại (dev dùng Vite proxy).
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
