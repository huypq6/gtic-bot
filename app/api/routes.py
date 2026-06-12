"""REST routes. P0: /api/health. P1: /api/klines + /api/klines/sync (xem SRS §5)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.market.store import get_klines, sync_historical

router = APIRouter(prefix="/api")

# Khung thời gian hỗ trợ (UI dropdown). Không hardcode ở frontend.
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]


@router.get("/health")
async def health() -> dict:
    """Liveness probe — dùng cho compose healthcheck + smoke test frontend."""
    return {"status": "ok"}


@router.get("/config")
async def config() -> dict:
    """Cấu hình UI cần: danh sách symbol theo dõi + khung thời gian + tf mặc định."""
    return {
        "symbols": settings.default_symbols,
        "timeframes": TIMEFRAMES,
        "default_tf": settings.default_tf,
    }


@router.get("/klines")
async def list_klines(
    symbol: str = Query(...),
    tf: str = Query("1m"),
    start: int | None = Query(None, description="open time ms (UTC)"),
    end: int | None = Query(None, description="open time ms (UTC)"),
    limit: int = Query(1000, le=5000),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Nến lịch sử cho chart load ban đầu (sau đó cập nhật realtime qua WS)."""
    s = datetime.fromtimestamp(start / 1000, tz=UTC) if start else None
    e = datetime.fromtimestamp(end / 1000, tz=UTC) if end else None
    return await get_klines(session, symbol, tf, s, e, limit)


class SyncRequest(BaseModel):
    symbol: str
    tf: str = "1m"
    start: str = "1 day ago UTC"  # python-binance hiểu chuỗi này
    end: str | None = None


@router.post("/klines/sync")
async def sync_klines(
    body: SyncRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """Tải lịch sử từ Binance REST về Postgres (hypertable)."""
    n = await sync_historical(session, body.symbol, body.tf, body.start, body.end)
    return {"synced": n, "symbol": body.symbol, "tf": body.tf}
