"""REST routes. P0: /api/health. P1: /api/klines + /api/klines/sync (see SRS §5)."""

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
from app.version import get_version

router = APIRouter(prefix="/api")

# Supported timeframes (UI dropdown). Not hardcoded in the frontend.
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]


@router.get("/health")
async def health() -> dict:
    """Liveness probe — used by the compose healthcheck + frontend smoke test."""
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict:
    """Running version (commit/build/date) — shown in the web header; flags new builds."""
    return get_version()


@router.get("/config")
async def config(session: AsyncSession = Depends(get_session)) -> dict:
    """UI config: watchlist (DB) + timeframes + default tf."""
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
    """Add a pair to the watchlist + subscribe the realtime feed. Checks it exists on Binance."""
    symbol = body.symbol.strip().upper()
    if not symbol.isalnum():
        raise HTTPException(400, "invalid symbol")
    from binance import AsyncClient

    client = await AsyncClient.create()
    try:
        info = await client.get_symbol_info(symbol)
    finally:
        await client.close_connection()
    if not info:
        raise HTTPException(400, f"pair {symbol} does not exist on Binance")

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
    """Historical candles for the chart's initial load (then updated in realtime via WS)."""
    s = datetime.fromtimestamp(start / 1000, tz=UTC) if start else None
    e = datetime.fromtimestamp(end / 1000, tz=UTC) if end else None
    return await get_klines(session, symbol, tf, s, e, limit)


class SyncRequest(BaseModel):
    symbol: str
    tf: str = "1m"
    start: str = "1 day ago UTC"  # python-binance understands this string
    end: str | None = None


@router.get("/scan")
async def scan(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Latest scan results (1 row per symbol, most recent ts)."""
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
    """Download history from Binance REST into Postgres (hypertable)."""
    n = await sync_historical(session, body.symbol, body.tf, body.start, body.end)
    return {"synced": n, "symbol": body.symbol, "tf": body.tf}
