"""FastAPI entrypoint — single process, asyncio.

Lifespan là nơi (từ P1) spawn các asyncio task: MarketFeed, StrategyRunner,
Scanner... Hiện P0 chỉ khung rỗng.

Prod (1 endpoint): nếu `frontend/dist` tồn tại → mount StaticFiles tại "/" để
FastAPI phục vụ cả UI lẫn API trên cùng cổng. Dev: Vite (:5173) proxy sang đây.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.config import settings

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup — P1+: tạo MarketFeed/EventBus/StrategyRunner tasks ở đây
    app.state.settings = settings
    yield
    # shutdown — P1+: hủy task, đóng WS/feed


app = FastAPI(title="GTIC Trading Bot", version="0.1.0", lifespan=lifespan)

app.include_router(api_router)

# Prod: serve built frontend. Chỉ mount khi dist tồn tại (dev dùng Vite proxy).
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
