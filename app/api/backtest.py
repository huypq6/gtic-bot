"""REST backtest: POST /backtest (chạy + lưu), GET /backtest/{id}."""

import logging

from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtest.engine import run_backtest
from app.db import get_session
from app.market.store import get_klines, sync_historical
from app.orders.models import BacktestRun, BacktestTrade, StrategyModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class BacktestReq(BaseModel):
    strategy_id: int
    symbol: str
    tf: str = "1m"
    start: str = "7 days ago UTC"  # tải lịch sử nếu thiếu
    capital: float = 1_000.0
    market: str = "SPOT"  # SPOT | FUTURES
    leverage: int = 1  # chỉ áp cho FUTURES
    fee_rate: float | None = None  # None → lấy phí Binance theo market
    params: dict | None = None


@router.post("/backtest")
async def create_backtest(
    body: BacktestReq, session: AsyncSession = Depends(get_session)
) -> dict:
    from app.config import settings

    strat = await session.get(StrategyModel, body.strategy_id)
    if not strat:
        raise HTTPException(404, "strategy không tồn tại")
    params = body.params if body.params is not None else dict(strat.default_params)

    market = body.market.upper()
    if market not in ("SPOT", "FUTURES"):
        raise HTTPException(400, "market phải SPOT hoặc FUTURES")
    # phí khớp Binance theo thị trường (override được).
    if body.fee_rate is not None:
        fee = body.fee_rate
    else:
        fee = settings.binance_futures_fee if market == "FUTURES" else settings.binance_spot_fee
    # đòn bẩy: chỉ Futures, kẹp 1..max.
    leverage = 1
    if market == "FUTURES":
        leverage = max(1, min(body.leverage, settings.futures_max_leverage))

    # đảm bảo có dữ liệu lịch sử.
    await sync_historical(session, body.symbol, body.tf, body.start)
    candles = await get_klines(session, body.symbol, body.tf, limit=5000)
    if len(candles) < 5:
        raise HTTPException(400, "không đủ dữ liệu lịch sử để backtest")

    try:
        res = await to_thread.run_sync(
            lambda: run_backtest(
                strat.name, strat.version, params, candles,
                body.capital, fee, body.tf, leverage,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("backtest lỗi")
        raise HTTPException(500, f"backtest lỗi: {exc}") from exc

    run = BacktestRun(
        strategy_id=body.strategy_id, params=params, symbol=body.symbol, tf=body.tf,
        from_ts=_ms(res["from_ts"]), to_ts=_ms(res["to_ts"]),
        capital=body.capital, fee_rate=fee, market=market, leverage=leverage,
        pnl_pct=res["pnl_pct"], winrate=res["winrate"], max_dd=res["max_dd"],
        sharpe=res["sharpe"], n_trades=res["n_trades"], equity_curve=res["equity_curve"],
        indicators=res["indicators"],
    )
    session.add(run)
    await session.flush()
    for t in res["trades"]:
        session.add(
            BacktestTrade(
                run_id=run.id, side=t["side"],
                entry_ts=_ms(t["entry_ts"]), entry=t["entry"],
                exit_ts=_ms(t["exit_ts"]), exit=t["exit"], pnl_pct=t["pnl_pct"],
                sl=t["sl"], tp=t["tp"],
            )
        )
    await session.commit()
    return await _run_dict(session, run.id)


@router.get("/backtest/{run_id}")
async def get_backtest(run_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    return await _run_dict(session, run_id)


@router.get("/backtests")
async def list_backtests(
    limit: int = 20, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = (
        await session.execute(select(BacktestRun).order_by(BacktestRun.id.desc()).limit(limit))
    ).scalars().all()
    return [_summary(r) for r in rows]


def _ms(ms: int | None):
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ms / 1000, tz=UTC) if ms else None


def _summary(r: BacktestRun) -> dict:
    return {
        "id": r.id, "strategy_id": r.strategy_id, "symbol": r.symbol, "tf": r.tf,
        "capital": float(r.capital) if r.capital is not None else None,
        "fee_rate": float(r.fee_rate) if r.fee_rate is not None else None,
        "market": r.market, "leverage": r.leverage,
        "pnl_pct": float(r.pnl_pct) if r.pnl_pct is not None else None,
        "winrate": float(r.winrate) if r.winrate is not None else None,
        "max_dd": float(r.max_dd) if r.max_dd is not None else None,
        "sharpe": float(r.sharpe) if r.sharpe is not None else None,
        "n_trades": r.n_trades,
    }


async def _run_dict(session: AsyncSession, run_id: int) -> dict:
    run = await session.get(BacktestRun, run_id)
    if not run:
        raise HTTPException(404, "không có backtest này")
    trades = (
        await session.execute(
            select(BacktestTrade).where(BacktestTrade.run_id == run_id).order_by(BacktestTrade.id)
        )
    ).scalars().all()
    out = _summary(run)
    eq = run.equity_curve or []
    out["equity_curve"] = eq
    out["indicators"] = run.indicators or {}
    out["from_ts"] = int(run.from_ts.timestamp() * 1000) if run.from_ts else None
    out["to_ts"] = int(run.to_ts.timestamp() * 1000) if run.to_ts else None
    out["liquidated"] = bool(eq and eq[-1][1] <= 0)  # cháy tài khoản nếu equity về 0
    out["trades"] = [
        {
            "side": t.side,
            "entry_ts": int(t.entry_ts.timestamp() * 1000) if t.entry_ts else None,
            "entry": float(t.entry) if t.entry is not None else None,
            "exit_ts": int(t.exit_ts.timestamp() * 1000) if t.exit_ts else None,
            "exit": float(t.exit) if t.exit is not None else None,
            "pnl_pct": float(t.pnl_pct) if t.pnl_pct is not None else None,
            "sl": float(t.sl) if t.sl is not None else None,
            "tp": float(t.tp) if t.tp is not None else None,
        }
        for t in trades
    ]
    return out
