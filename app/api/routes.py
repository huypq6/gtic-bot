"""REST routes. P0: /api/health. P1: /api/klines + /api/klines/sync (xem SRS §5)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.market.store import get_klines, sync_historical
from app.market.watchlist import add_symbol, get_watchlist, remove_symbol
from app.orders.models import ScanResult

router = APIRouter(prefix="/api")

# Khung thời gian hỗ trợ (UI dropdown). Không hardcode ở frontend.
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]


@router.get("/health")
async def health() -> dict:
    """Liveness probe — dùng cho compose healthcheck + smoke test frontend."""
    return {"status": "ok"}


@router.get("/config")
async def config(session: AsyncSession = Depends(get_session)) -> dict:
    """Cấu hình UI: watchlist (DB) + khung thời gian + tf mặc định."""
    return {
        "symbols": await get_watchlist(session),
        "timeframes": TIMEFRAMES,
        "default_tf": settings.default_tf,
    }


class WatchReq(BaseModel):
    symbol: str


@router.post("/watchlist")
async def watchlist_add(
    body: WatchReq, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    """Thêm cặp vào watchlist + feed subscribe realtime. Kiểm tra cặp tồn tại trên Binance."""
    symbol = body.symbol.strip().upper()
    if not symbol.isalnum():
        raise HTTPException(400, "symbol không hợp lệ")
    from binance import AsyncClient

    client = await AsyncClient.create()
    try:
        info = await client.get_symbol_info(symbol)
    finally:
        await client.close_connection()
    if not info:
        raise HTTPException(400, f"cặp {symbol} không tồn tại trên Binance")

    await add_symbol(session, symbol)
    feed = getattr(request.app.state, "feed", None)
    if feed:
        await feed.add_symbol(symbol)
    return {"added": symbol, "symbols": await get_watchlist(session)}


@router.delete("/watchlist/{symbol}")
async def watchlist_remove(
    symbol: str, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    symbol = symbol.upper()
    await remove_symbol(session, symbol)
    feed = getattr(request.app.state, "feed", None)
    if feed:
        await feed.remove_symbol(symbol)
    return {"removed": symbol, "symbols": await get_watchlist(session)}


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


@router.get("/scan")
async def scan(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Kết quả scan mới nhất (1 dòng/symbol, ts gần nhất)."""
    from sqlalchemy import func

    sub = (
        select(ScanResult.symbol, func.max(ScanResult.id).label("mid"))
        .group_by(ScanResult.symbol)
        .subquery()
    )
    rows = (
        await session.execute(select(ScanResult).join(sub, ScanResult.id == sub.c.mid))
    ).scalars().all()
    def f(v):
        return float(v) if v is not None else None

    out = [
        {
            "symbol": r.symbol,
            "score": f(r.score),
            "signal": r.signal,
            "reason": r.reason,
            "entry": f(r.entry),
            "atr": f(r.atr),
            "sl": f(r.sl),
            "tp": f(r.tp),
            "ts": r.ts.isoformat() if r.ts else None,
        }
        for r in rows
    ]
    out.sort(key=lambda x: x["score"] or 0, reverse=True)
    return out


@router.post("/klines/sync")
async def sync_klines(
    body: SyncRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """Tải lịch sử từ Binance REST về Postgres (hypertable)."""
    n = await sync_historical(session, body.symbol, body.tf, body.start, body.end)
    return {"synced": n, "symbol": body.symbol, "tf": body.tf}
