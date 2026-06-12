"""REST: strategies, bots (CRUD + pause/resume/stop), positions. (SRS §5)"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.orders.models import Bot, OrderModel, PositionModel, StrategyModel
from app.strategy.registry import all_strategies, discover, sync_to_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ---------------- strategies ----------------
@router.get("/strategies")
async def list_strategies(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Quét file registry → sync DB → trả về (kèm id DB + param_schema cho UI)."""
    discover()
    await sync_to_db(session)
    schema_by_key = {
        (c.name, c.version): getattr(c, "param_schema", {}) for c in all_strategies()
    }
    q = select(StrategyModel).where(StrategyModel.is_active)
    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "version": r.version,
            "default_params": r.default_params,
            "param_schema": schema_by_key.get((r.name, r.version), {}),
        }
        for r in rows
    ]


# ---------------- bots ----------------
class CreateBot(BaseModel):
    strategy_id: int
    symbol: str
    tf: str = "1m"
    mode: str = "PAPER"
    params: dict = {}


class PatchBot(BaseModel):
    status: str | None = None  # RUNNING | PAUSED | STOPPED
    params: dict | None = None


async def _bot_dict(session: AsyncSession, bot: Bot) -> dict:
    strat = await session.get(StrategyModel, bot.strategy_id)
    return {
        "id": bot.id, "strategy_id": bot.strategy_id,
        "strategy": f"{strat.name} v{strat.version}" if strat else None,
        "symbol": bot.symbol, "tf": bot.tf, "mode": bot.mode,
        "params": bot.params, "status": bot.status,
    }


@router.get("/bots")
async def list_bots(session: AsyncSession = Depends(get_session)) -> list[dict]:
    bots = (await session.execute(select(Bot).order_by(Bot.id))).scalars().all()
    return [await _bot_dict(session, b) for b in bots]


@router.post("/bots")
async def create_bot(
    body: CreateBot, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    strat = await session.get(StrategyModel, body.strategy_id)
    if not strat:
        raise HTTPException(404, "strategy không tồn tại")
    if body.mode != "PAPER":
        raise HTTPException(400, f"mode {body.mode} chưa hỗ trợ (P2: PAPER)")
    bot = Bot(
        strategy_id=body.strategy_id, symbol=body.symbol, tf=body.tf,
        mode=body.mode, params=body.params, status="RUNNING",
    )
    session.add(bot)
    await session.commit()
    await session.refresh(bot)

    await request.app.state.bot_manager.start_bot(
        bot.id, strat.name, strat.version, bot.params, bot.symbol, bot.tf, bot.mode
    )
    return await _bot_dict(session, bot)


@router.patch("/bots/{bot_id}")
async def patch_bot(
    bot_id: int, body: PatchBot, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    bot = await session.get(Bot, bot_id)
    if not bot:
        raise HTTPException(404, "bot không tồn tại")
    mgr = request.app.state.bot_manager

    if body.params is not None:
        bot.params = body.params
    if body.status is not None:
        if body.status not in ("RUNNING", "PAUSED", "STOPPED"):
            raise HTTPException(400, "status không hợp lệ")
        bot.status = body.status
        if body.status == "STOPPED":
            await mgr.stop_bot(bot_id)
        elif not mgr.is_running(bot_id):
            strat = await session.get(StrategyModel, bot.strategy_id)
            await mgr.start_bot(
                bot.id, strat.name, strat.version, bot.params, bot.symbol, bot.tf, bot.mode
            )
            mgr.set_status(bot_id, body.status)
        else:
            mgr.set_status(bot_id, body.status)
    await session.commit()
    return await _bot_dict(session, bot)


@router.delete("/bots/{bot_id}")
async def delete_bot(
    bot_id: int, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    bot = await session.get(Bot, bot_id)
    if not bot:
        raise HTTPException(404, "bot không tồn tại")
    await request.app.state.bot_manager.stop_bot(bot_id)
    # Giữ lịch sử order/position (orphan bot_id NULL) → tránh vi phạm FK khi xóa bot.
    await session.execute(
        update(OrderModel).where(OrderModel.bot_id == bot_id).values(bot_id=None)
    )
    await session.execute(
        update(PositionModel).where(PositionModel.bot_id == bot_id).values(bot_id=None)
    )
    await session.delete(bot)
    await session.commit()
    return {"deleted": bot_id}


# ---------------- positions ----------------
@router.get("/positions")
async def list_positions(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (
        await session.execute(
            select(PositionModel).where(PositionModel.status == "OPEN").order_by(PositionModel.id)
        )
    ).scalars().all()
    return [
        {
            "id": p.id, "bot_id": p.bot_id, "mode": p.mode, "symbol": p.symbol,
            "side": p.side, "qty": float(p.qty), "entry_price": float(p.entry_price),
            "sl": float(p.sl) if p.sl is not None else None,
            "tp": float(p.tp) if p.tp is not None else None,
        }
        for p in rows
    ]


@router.get("/orders")
async def list_orders(
    limit: int = 50, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = (
        await session.execute(select(OrderModel).order_by(OrderModel.id.desc()).limit(limit))
    ).scalars().all()
    return [
        {
            "id": o.id, "bot_id": o.bot_id, "mode": o.mode, "symbol": o.symbol,
            "side": o.side, "type": o.type, "qty": float(o.qty),
            "price": float(o.price) if o.price is not None else None, "status": o.status,
        }
        for o in rows
    ]
