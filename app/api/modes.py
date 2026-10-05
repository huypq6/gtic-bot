"""Mode workspaces (docs/08): per-mode overview + cross-mode / cross-version comparison."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.orders.compare import MODES, compare, trade_r
from app.orders.models import Bot, PositionModel

router = APIRouter(prefix="/api")

_TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000,
          "1d": 86_400_000}


def _f(v):
    return float(v) if v is not None else None


def _trade(p: PositionModel) -> dict:
    return {
        "mode": p.mode, "strategy": p.strategy, "symbol": p.symbol, "tf": p.tf,
        "side": p.side, "qty": float(p.qty), "entry": float(p.entry_price),
        "exit": _f(p.exit_price), "pnl": _f(p.pnl), "fee": _f(p.fee),
        "init_sl": _f(p.init_sl) if p.init_sl is not None else _f(p.sl),
        "opened_ms": int(p.opened_at.timestamp() * 1000),
        "bot_ref": p.bot_ref if p.bot_ref is not None else p.bot_id,
    }


async def _closed_since(
    session: AsyncSession, since: datetime | None, symbol: str | None = None
) -> list[PositionModel]:
    q = select(PositionModel).where(PositionModel.status == "CLOSED")
    if since is not None:
        q = q.where(PositionModel.closed_at >= since)
    if symbol:
        q = q.where(PositionModel.symbol == symbol)
    return list((await session.execute(q.order_by(PositionModel.opened_at))).scalars().all())


@router.get("/modes/summary")
async def modes_summary(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """One card per mode: bots by status, open positions + open risk, today / 7-day results."""
    now = datetime.now(UTC)
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)  # UTC, like the daily guard
    bots = (
        await session.execute(
            select(Bot.mode, Bot.status, func.count()).group_by(Bot.mode, Bot.status)
        )
    ).all()
    opens = (
        await session.execute(
            select(
                PositionModel.mode, func.count(),
                func.coalesce(func.sum(PositionModel.risk_amount), 0),
            ).where(PositionModel.status == "OPEN").group_by(PositionModel.mode)
        )
    ).all()
    week = await _closed_since(session, now - timedelta(days=7))

    out = []
    for m in ("PAPER", "TESTNET", "LIVE"):
        wk = [p for p in week if p.mode == m]
        td = [p for p in wk if p.closed_at and p.closed_at >= day0]
        rs = [r for r in (trade_r(_trade(p)) for p in wk) if r is not None]
        op = next(((n, risk) for mm, n, risk in opens if mm == m), (0, 0))
        out.append({
            "mode": m,
            "bots": {s: n for mm, s, n in bots if mm == m},
            "open_positions": op[0],
            "open_risk": float(op[1]),
            "today": {"trades": len(td), "pnl": sum(_f(p.pnl) or 0 for p in td)},
            "week": {
                "trades": len(wk),
                "wins": sum(1 for p in wk if (_f(p.pnl) or 0) > 0),
                "pnl": sum(_f(p.pnl) or 0 for p in wk),
                "sum_r": sum(rs) if rs else None,
            },
        })
    return out


@router.get("/compare")
async def compare_modes(
    days: int = 30, symbol: str | None = None, session: AsyncSession = Depends(get_session)
) -> dict:
    """Same strategy across modes & versions + live-vs-paper divergence (paired trades).
    days ≤ 0 → all history."""
    since = datetime.now(UTC) - timedelta(days=days) if days > 0 else None
    rows = await _closed_since(session, since, symbol)
    return {"days": days, "modes": list(MODES),
            "groups": compare([_trade(p) for p in rows], _TF_MS)}
