"""Backtest REST: POST /backtest (run + save), GET /backtest/{id}."""

import logging

from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtest.engine import run_backtest
from app.db import get_session
from app.market.store import ensure_history, get_klines
from app.orders.models import BacktestRun, BacktestTrade, StrategyModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
CHART_BARS = 5000  # = BacktestChart's loadRange limit


class SizingVariant(BaseModel):
    method: str = "risk_pct"
    value: float = 1.0
    leverage: float | None = None  # None = use the request's leverage


class BacktestReq(BaseModel):
    strategy_id: int
    symbol: str
    tf: str = "1m"
    start: str = "7 days ago UTC"  # download history if missing
    capital: float = 1_000.0
    market: str = "SPOT"  # SPOT | FUTURES
    leverage: int = 1  # FUTURES only
    fee_rate: float | None = None  # None → use Binance fee for the market
    params: dict | None = None
    # P9c — ACCOUNT engine: simulates the account like paper (equity-based sizing, intrabar SL)
    engine: str = "VBT"  # VBT | ACCOUNT
    sizing: SizingVariant | None = None
    maker_fee: float | None = None
    slippage_bps: float = 2.0
    max_risk_pct: float | None = None
    max_open_risk_pct: float | None = None
    daily_loss_pct: float | None = None
    max_dd_pct: float | None = None
    compare: list[SizingVariant] = []  # run additional sizing configs for comparison


@router.post("/backtest")
async def create_backtest(
    body: BacktestReq, session: AsyncSession = Depends(get_session)
) -> dict:
    from app.config import settings

    strat = await session.get(StrategyModel, body.strategy_id)
    if not strat:
        raise HTTPException(404, "strategy not found")
    params = body.params if body.params is not None else dict(strat.default_params)

    market = body.market.upper()
    if market not in ("SPOT", "FUTURES"):
        raise HTTPException(400, "market must be SPOT or FUTURES")
    # Binance fill fee per market (overridable).
    if body.fee_rate is not None:
        fee = body.fee_rate
    else:
        fee = settings.binance_futures_fee if market == "FUTURES" else settings.binance_spot_fee
    # leverage: Futures only, clamped to 1..max.
    leverage = 1
    if market == "FUTURES":
        leverage = max(1, min(body.leverage, settings.futures_max_leverage))

    # Filter by start — the DB may hold much more history than the range the user picked
    # (without filtering, "Days" has no effect: always the latest 5000 candles).
    import dateparser

    start_dt = dateparser.parse(body.start, settings={"RETURN_AS_TIMEZONE_AWARE": True})
    if start_dt is None:
        raise HTTPException(400, f"cannot parse start time '{body.start}'")
    # ensure historical data exists (download only the missing part).
    await ensure_history(session, body.symbol, body.tf, start_dt)
    engine = body.engine.upper()
    # ACCOUNT is fast (pure Python, O(n)) → allow longer ranges (≈ 1 year of 15m).
    limit = 40_000 if engine == "ACCOUNT" else 5000
    candles = await get_klines(session, body.symbol, body.tf, start=start_dt, limit=limit)
    if len(candles) < 5:
        raise HTTPException(400, "not enough historical data to backtest")
    if engine == "ACCOUNT":
        return await _account_backtest(session, body, strat, params, candles, fee, leverage)

    try:
        res = await to_thread.run_sync(
            lambda: run_backtest(
                strat.name, strat.version, params, candles,
                body.capital, fee, body.tf, leverage,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("backtest failed")
        raise HTTPException(500, f"backtest failed: {exc}") from exc

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


async def _account_backtest(session, body, strat, params, candles, fee, leverage) -> dict:
    from app.account.risk import SIZING_METHODS
    from app.backtest.sim import SimConfig, simulate

    variants = [body.sizing or SizingVariant()] + list(body.compare[:8])
    for v in variants:
        if v.method not in SIZING_METHODS:
            raise HTTPException(422, f"invalid sizing method '{v.method}'")

    def cfg_for(v: SizingVariant) -> SimConfig:
        lev = v.leverage if v.leverage is not None else leverage
        if body.market.upper() == "SPOT":
            lev = 1
        return SimConfig(
            capital=body.capital, sizing={"method": v.method, "value": v.value},
            leverage=max(1.0, float(lev)), taker_fee=fee,
            maker_fee=body.maker_fee if body.maker_fee is not None else fee,
            slippage_bps=body.slippage_bps, max_risk_pct=body.max_risk_pct,
            max_open_risk_pct=body.max_open_risk_pct, daily_loss_pct=body.daily_loss_pct,
            max_dd_pct=body.max_dd_pct,
        )

    def run_all() -> list[dict]:
        return [
            simulate(strat.name, strat.version, params, candles, cfg_for(v), body.tf,
                     body.symbol)
            for v in variants
        ]

    try:
        results = await to_thread.run_sync(run_all)
    except Exception as exc:  # noqa: BLE001
        logger.exception("backtest failed")
        raise HTTPException(500, f"backtest failed: {exc}") from exc

    res, main_cfg = results[0], cfg_for(variants[0])
    stat_keys = ("cagr_pct", "longest_dd_days", "calmar", "profit_factor", "avg_r", "best_r",
                 "worst_r", "max_loss_streak", "total_fees", "fees_pct_of_capital", "day_halts",
                 "dd_halt_ts", "liquidated", "rejects", "capped", "avg_notional_pct", "monthly",
                 "positive_months")
    stats = {k: res[k] for k in stat_keys}
    stats["compare"] = [
        {
            "sizing": {"method": v.method, "value": v.value},
            "leverage": cfg_for(v).leverage,
            **{k: r[k] for k in ("final_equity", "pnl_pct", "cagr_pct", "max_dd", "calmar",
                                 "sharpe", "winrate", "n_trades", "profit_factor", "avg_r",
                                 "total_fees", "day_halts", "dd_halt_ts", "liquidated",
                                 "avg_notional_pct", "capped", "rejects", "positive_months")},
            "n_months": len(r["monthly"]),
            "equity_curve": r["equity_curve"],
        }
        for v, r in zip(variants, results, strict=True)
    ]
    settings_used = {
        "leverage": main_cfg.leverage, "taker_fee": main_cfg.taker_fee,
        "maker_fee": main_cfg.maker_fee, "slippage_bps": main_cfg.slippage_bps,
        "max_risk_pct": main_cfg.max_risk_pct, "max_open_risk_pct": main_cfg.max_open_risk_pct,
        "daily_loss_pct": main_cfg.daily_loss_pct, "max_dd_pct": main_cfg.max_dd_pct,
    }
    # indicators for charting like the VBT engine — the chart only loads the last 5000
    # candles (loadRange) → return only that part (1 year of 15m = 35k points/series
    # ≈ 3 MB JSON, freezes the browser).
    indicators: dict = {}
    try:
        from app.strategy.registry import get

        inst = get(strat.name, strat.version)(params)
        pane_map = inst.plot_pane()
        first = max(0, len(candles) - CHART_BARS)
        for name, series in inst.plot(candles).items():
            indicators[name] = {
                "pane": int(pane_map.get(name, 0)),
                "data": [[candles[i]["ts"], round(float(series[i]), 6)]
                         for i in range(first, len(series)) if series[i] is not None],
            }
    except Exception:  # noqa: BLE001
        indicators = {}

    run = BacktestRun(
        strategy_id=body.strategy_id, params=params, symbol=body.symbol, tf=body.tf,
        from_ts=_ms(res["from_ts"]), to_ts=_ms(res["to_ts"]),
        capital=body.capital, fee_rate=fee, market=body.market.upper(),
        leverage=int(main_cfg.leverage), pnl_pct=res["pnl_pct"], winrate=res["winrate"],
        max_dd=res["max_dd"], sharpe=res["sharpe"], n_trades=res["n_trades"],
        equity_curve=res["equity_curve"], indicators=indicators, engine="ACCOUNT",
        sizing=main_cfg.sizing, settings=settings_used, stats=stats,
        final_equity=res["final_equity"],
    )
    session.add(run)
    await session.flush()
    for t in res["trades"]:
        session.add(BacktestTrade(
            run_id=run.id, side=t["side"], entry_ts=_ms(t["entry_ts"]), entry=t["entry"],
            exit_ts=_ms(t["exit_ts"]), exit=t["exit"], pnl_pct=t["pnl_pct"], sl=t["sl"],
            tp=t["tp"], qty=t["qty"], pnl=t["pnl"], fee=t["fee"], r=t["r"],
            reason=t["reason"], mfe_r=t["mfe_r"], mae_r=t["mae_r"],
        ))
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


def _fl(v) -> float | None:
    return float(v) if v is not None else None


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
        "engine": r.engine or "VBT",
        "sizing": r.sizing,
        "final_equity": float(r.final_equity) if r.final_equity is not None else None,
    }


async def _run_dict(session: AsyncSession, run_id: int) -> dict:
    run = await session.get(BacktestRun, run_id)
    if not run:
        raise HTTPException(404, "backtest not found")
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
    out["liquidated"] = bool(eq and eq[-1][1] <= 0)  # account liquidated if equity hits 0
    out["settings"] = run.settings
    out["stats"] = run.stats
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
            "qty": _fl(t.qty), "pnl": _fl(t.pnl), "fee": _fl(t.fee), "r": _fl(t.r),
            "reason": t.reason, "mfe_r": _fl(t.mfe_r), "mae_r": _fl(t.mae_r),
        }
        for t in trades
    ]
    return out
