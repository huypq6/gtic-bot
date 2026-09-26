"""REST: strategies, bots (CRUD + pause/resume/stop), positions. (SRS §5)"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.market.store import get_klines
from app.orders.models import BacktestRun, Bot, OrderModel, PositionModel, StrategyModel
from app.orders.trades import excursion, infer_reason, summarize
from app.strategy.base import Signal
from app.strategy.params import ParamError, validate_params
from app.strategy.registry import all_strategies, discover, get, sync_to_db


def _schema_for(strat: StrategyModel) -> dict:
    discover()
    try:
        return getattr(get(strat.name, strat.version), "param_schema", {})
    except KeyError:
        return {}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ---------------- strategies ----------------
@router.get("/strategies")
async def list_strategies(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Quét file registry → sync DB → trả về (kèm id DB + param_schema cho UI)."""
    discover()
    await sync_to_db(session)
    by_key = {(c.name, c.version): c for c in all_strategies()}
    q = select(StrategyModel).where(StrategyModel.is_active)
    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "version": r.version,
            "default_params": r.default_params,
            "param_schema": getattr(by_key.get((r.name, r.version)), "param_schema", {}),
            "description": getattr(by_key.get((r.name, r.version)), "description", ""),
            "source_file": r.source_file,
        }
        for r in rows
    ]


@router.get("/strategies/{name}/doc")
async def strategy_doc(name: str) -> dict:
    """Tài liệu phương pháp luận (markdown) của strategy — đọc app/strategy/strategies/<name>.md."""
    import re
    from pathlib import Path

    from app.strategy import strategies as strat_pkg

    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise HTTPException(404, "tên không hợp lệ")
    f = Path(strat_pkg.__path__[0]) / f"{name}.md"
    if not f.is_file():
        return {"name": name, "markdown": "_Chưa có tài liệu phương pháp luận cho strategy này._"}
    return {"name": name, "markdown": f.read_text(encoding="utf-8")}


@router.get("/strategies/{name}/compare")
async def compare_versions(
    name: str, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """So sánh hiệu năng các version (gộp backtest_run) theo version (US-08)."""
    strats = (
        await session.execute(
            select(StrategyModel).where(StrategyModel.name == name).order_by(StrategyModel.version)
        )
    ).scalars().all()
    out = []
    for s in strats:
        runs = (
            await session.execute(
                select(BacktestRun)
                .where(BacktestRun.strategy_id == s.id)
                .order_by(BacktestRun.id.desc())
            )
        ).scalars().all()
        best = max((float(r.pnl_pct) for r in runs if r.pnl_pct is not None), default=None)
        last = runs[0] if runs else None
        out.append(
            {
                "version": s.version,
                "runs": len(runs),
                "best_pnl_pct": best,
                "last_pnl_pct": float(last.pnl_pct) if last and last.pnl_pct is not None else None,
                "last_winrate": float(last.winrate) if last and last.winrate is not None else None,
                "last_max_dd": float(last.max_dd) if last and last.max_dd is not None else None,
                "last_n_trades": last.n_trades if last else None,
            }
        )
    return out


# ---------------- bots ----------------
class Sizing(BaseModel):
    method: str = "risk_pct"  # xem app.account.risk.SIZING_METHODS
    value: float = 1.0


class CreateBot(BaseModel):
    strategy_id: int
    symbol: str
    tf: str = "1m"
    mode: str = "PAPER"
    params: dict = {}
    confirm: str | None = None  # mode LIVE bắt buộc = "LIVE"
    account_id: int | None = None  # PAPER: bỏ trống = tài khoản paper mặc định
    sizing: Sizing | None = None


class PatchBot(BaseModel):
    status: str | None = None  # RUNNING | PAUSED | STOPPED
    params: dict | None = None
    sizing: Sizing | None = None
    account_id: int | None = None


def _check_sizing(sz: Sizing | None) -> dict | None:
    from app.account.risk import SIZING_METHODS

    if sz is None:
        return None
    if sz.method not in SIZING_METHODS:
        raise HTTPException(422, f"phương pháp khối lượng '{sz.method}' không hợp lệ")
    if sz.value < 0 or (sz.method != "fixed_qty" and sz.value == 0):
        raise HTTPException(422, "giá trị khối lượng phải > 0")
    if sz.method == "risk_pct" and sz.value > 10:
        raise HTTPException(422, "rủi ro > 10% vốn/lệnh — quá liều, không cho phép")
    return sz.model_dump()


async def _check_account(session: AsyncSession, account_id: int | None, mode: str) -> int | None:
    from app.orders.models import Account

    if account_id is None:  # mặc định: tài khoản đầu tiên cùng mode (sàn: duy nhất)
        acc = (
            await session.execute(
                select(Account).where(Account.mode == mode).order_by(Account.id).limit(1)
            )
        ).scalar_one_or_none()
        return acc.id if acc else None
    acc = await session.get(Account, account_id)
    if not acc:
        raise HTTPException(404, "tài khoản không tồn tại")
    if acc.mode != mode:
        raise HTTPException(400, f"tài khoản {acc.mode} không dùng được cho bot {mode}")
    return acc.id


async def _bot_dict(session: AsyncSession, bot: Bot) -> dict:
    strat = await session.get(StrategyModel, bot.strategy_id)
    return {
        "id": bot.id, "strategy_id": bot.strategy_id,
        "strategy": f"{strat.name} v{strat.version}" if strat else None,
        "symbol": bot.symbol, "tf": bot.tf, "mode": bot.mode,
        "params": bot.params, "status": bot.status,
        "account_id": bot.account_id, "sizing": bot.sizing,
    }


@router.get("/bots")
async def list_bots(
    request: Request, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    bots = (await session.execute(select(Bot).order_by(Bot.id))).scalars().all()
    mgr = getattr(request.app.state, "bot_manager", None)
    out = []
    for b in bots:
        d = await _bot_dict(session, b)
        # open-time nến đóng cuối runner nhận — None = chưa nhận nến live nào (feed chưa stream).
        d["last_candle"] = mgr.last_candle_ts(b.id) if mgr else None
        out.append(d)
    return out


@router.post("/bots")
async def create_bot(
    body: CreateBot, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    strat = await session.get(StrategyModel, body.strategy_id)
    if not strat:
        raise HTTPException(404, "strategy không tồn tại")
    if body.mode not in ("PAPER", "TESTNET", "LIVE"):
        raise HTTPException(400, f"mode {body.mode} không hợp lệ")
    if body.mode == "LIVE":
        # Rào chắn: cờ env + xác nhận gõ "LIVE" (NFR an toàn).
        if not settings.enable_live:
            raise HTTPException(403, "mode LIVE bị khóa — cần ENABLE_LIVE=1")
        if body.confirm != "LIVE":
            raise HTTPException(400, "mode LIVE cần xác nhận gõ 'LIVE'")
    try:
        params = validate_params(_schema_for(strat), body.params)
    except ParamError as e:
        raise HTTPException(422, str(e)) from e
    account_id = await _check_account(session, body.account_id, body.mode)
    sizing = _check_sizing(body.sizing) or (
        {"method": "risk_pct", "value": 1.0} if account_id else None
    )
    bot = Bot(
        strategy_id=body.strategy_id, symbol=body.symbol, tf=body.tf,
        mode=body.mode, params=params, status="RUNNING",
        account_id=account_id, sizing=sizing,
    )
    session.add(bot)
    await session.commit()
    await session.refresh(bot)

    try:
        await request.app.state.bot_manager.start_bot(
            bot.id, strat.name, strat.version, bot.params, bot.symbol, bot.tf, bot.mode,
            account_id=bot.account_id, sizing=bot.sizing,
        )
    except ValueError as e:  # vd thiếu key testnet
        await session.delete(bot)
        await session.commit()
        raise HTTPException(400, str(e)) from e
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
        strat = await session.get(StrategyModel, bot.strategy_id)
        try:
            bot.params = validate_params(_schema_for(strat), body.params)
        except ParamError as e:
            raise HTTPException(422, str(e)) from e
    restart = False
    if body.sizing is not None:
        bot.sizing = _check_sizing(body.sizing)
        r = mgr._runners.get(bot_id)
        if r:
            r.sizing = bot.sizing  # áp cho lệnh kế tiếp, không cần restart
    if body.account_id is not None and body.account_id != bot.account_id:
        has_open = (
            await session.execute(
                select(PositionModel.id).where(
                    PositionModel.bot_id == bot_id, PositionModel.status == "OPEN"
                )
            )
        ).first()
        if has_open:
            raise HTTPException(409, "bot đang có lệnh mở — đóng lệnh trước khi đổi tài khoản")
        bot.account_id = await _check_account(session, body.account_id, bot.mode)
        restart = mgr.is_running(bot_id)
    if restart:
        strat = await session.get(StrategyModel, bot.strategy_id)
        await mgr.stop_bot(bot_id)
        await mgr.start_bot(
            bot.id, strat.name, strat.version, bot.params, bot.symbol, bot.tf, bot.mode,
            account_id=bot.account_id, sizing=bot.sizing,
        )
        mgr.set_status(bot_id, bot.status)
    if body.status is not None:
        if body.status not in ("RUNNING", "PAUSED", "STOPPED"):
            raise HTTPException(400, "status không hợp lệ")
        bot.status = body.status
        if body.status == "STOPPED":
            await mgr.stop_bot(bot_id)
        elif not mgr.is_running(bot_id):
            strat = await session.get(StrategyModel, bot.strategy_id)
            await mgr.start_bot(
                bot.id, strat.name, strat.version, bot.params, bot.symbol, bot.tf, bot.mode,
                account_id=bot.account_id, sizing=bot.sizing,
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
    strat = await session.get(StrategyModel, bot.strategy_id)
    await request.app.state.order_manager.write_audit(
        source="MANUAL", action="DELETE_BOT", mode=bot.mode, bot_id=bot_id, symbol=bot.symbol,
        detail={
            "strategy": f"{strat.name} v{strat.version}" if strat else None,
            "tf": bot.tf, "params": bot.params,
        },
    )
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
    limit: int = 200,
    mode: str | None = None,
    source: str | None = None,
    status: str | None = None,
    symbol: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    q = select(OrderModel).order_by(OrderModel.id.desc())
    if mode:
        q = q.where(OrderModel.mode == mode)
    if source:
        q = q.where(OrderModel.source == source)
    if status:
        q = q.where(OrderModel.status == status)
    if symbol:
        q = q.where(OrderModel.symbol == symbol)
    rows = (await session.execute(q.limit(limit))).scalars().all()

    def f(v):
        return float(v) if v is not None else None

    return [
        {
            "id": o.id, "bot_id": o.bot_id, "ext_id": o.ext_id, "source": o.source,
            "mode": o.mode, "symbol": o.symbol, "side": o.side, "type": o.type,
            "qty": f(o.qty), "price": f(o.price), "sl": f(o.sl), "tp": f(o.tp),
            "filled_qty": f(o.filled_qty), "avg_price": f(o.avg_price), "fee": f(o.fee),
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in rows
    ]


# ---------------- review lệnh ----------------
_TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}


async def _hold_bars(
    session: AsyncSession, symbol: str, tf: str | None, start: datetime, end: datetime
) -> list[dict]:
    """Nến trong thời gian giữ lệnh: ưu tiên 1m (MFE/MAE sát nhất), đủ ≤ 5000 nến."""
    span = (end - start).total_seconds() * 1000
    tfs = [t for t in ("1m", "5m", "15m", "1h", "4h") if span / _TF_MS[t] <= 5000]
    if tf and tf in _TF_MS and tf not in tfs:
        tfs.append(tf)
    s0 = datetime.fromtimestamp(start.timestamp() // 60 * 60, tz=UTC)  # nến chứa lúc vào
    for t in tfs:
        bars = await get_klines(session, symbol, t, s0, end, limit=5000)
        if bars:
            return bars
    return []


@router.get("/trades")
async def list_trades(
    limit: int = 100,
    mode: str | None = None,
    symbol: str | None = None,
    bot_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Mỗi vị thế = 1 lệnh để review: chiến lược, kết quả, PnL, R, MFE/MAE."""
    q = (
        select(PositionModel, Bot, StrategyModel)
        .outerjoin(Bot, Bot.id == PositionModel.bot_id)
        .outerjoin(StrategyModel, StrategyModel.id == Bot.strategy_id)
        .order_by(PositionModel.opened_at.desc(), PositionModel.id.desc())
    )
    if mode:
        q = q.where(PositionModel.mode == mode)
    if symbol:
        q = q.where(PositionModel.symbol == symbol)
    if bot_id is not None:
        q = q.where(func.coalesce(PositionModel.bot_ref, PositionModel.bot_id) == bot_id)
    rows = (await session.execute(q.limit(limit))).all()

    def f(v):
        return float(v) if v is not None else None

    out = []
    now = datetime.now(UTC)
    for p, bot, strat in rows:
        entry, qty = float(p.entry_price), float(p.qty)
        end = p.closed_at or now
        bars = await _hold_bars(
            session, p.symbol, p.tf or (bot.tf if bot else None), p.opened_at, end
        )
        reason = p.exit_reason or (
            infer_reason(f(p.exit_price), f(p.sl), f(p.tp)) if p.status == "CLOSED" else None
        )
        exc = excursion(p.side, entry, bars, reason, f(p.exit_price))
        stats = summarize(
            side=p.side, qty=qty, entry=entry, exit_price=f(p.exit_price), pnl=f(p.pnl),
            risk_sl=f(p.init_sl) if p.init_sl is not None else f(p.sl), exc=exc,
            mark=bars[-1]["close"] if bars else None,
        )
        out.append({
            "id": p.id, "bot_id": p.bot_id, "mode": p.mode, "symbol": p.symbol,
            "side": p.side, "qty": qty, "entry_price": entry, "exit_price": f(p.exit_price),
            "sl": f(p.sl), "tp": f(p.tp), "init_sl": f(p.init_sl), "status": p.status,
            "exit_reason": reason,
            "account_id": p.account_id, "fee": f(p.fee), "margin": f(p.margin),
            # snapshot lúc mở (còn nguyên khi bot bị xóa); vị thế cũ chưa có → bot hiện tại.
            "strategy": p.strategy or (f"{strat.name} v{strat.version}" if strat else None),
            "tf": p.tf or (bot.tf if bot else None),
            "params": p.params if p.params is not None else (bot.params if bot else None),
            "source": p.source or ("BOT" if p.bot_id is not None else "MANUAL"),
            "bot_ref": p.bot_ref if p.bot_ref is not None else p.bot_id,
            "bot_deleted": bot is None and (p.bot_ref is not None),
            "opened_at": int(p.opened_at.timestamp() * 1000),
            "closed_at": int(p.closed_at.timestamp() * 1000) if p.closed_at else None,
            **stats,
        })
    return out


# ---------------- can thiệp tay (P3) ----------------
def _route_executor(request: Request, bot_id: int | None, symbol: str):
    """Tìm executor giữ vị thế: bot đang chạy → bot executor; ngược lại → manual."""
    if bot_id is not None:
        ex = request.app.state.bot_manager.get_executor(bot_id)
        if ex:
            return ex
    return request.app.state.manual_trader.executor_for(symbol)


class CloseBody(BaseModel):
    ref_price: float | None = None  # giá tham chiếu nếu bot đã dừng (đóng DB)


@router.post("/positions/{pos_id}/close")
async def close_position(
    pos_id: int, body: CloseBody, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    pos = await session.get(PositionModel, pos_id)
    if not pos or pos.status != "OPEN":
        raise HTTPException(404, "vị thế không mở")
    om = request.app.state.order_manager
    ex = _route_executor(request, pos.bot_id, pos.symbol)

    async def do():
        if ex:
            await ex.close("MANUAL")  # engine đóng + persist + broadcast
        else:
            await _db_close(session, pos, body.ref_price, request.app.state.accounts)

    await om.execute(
        source="MANUAL", action="CLOSE", mode=pos.mode, bot_id=pos.bot_id,
        symbol=pos.symbol, detail={"position_id": pos_id}, do=do,
    )
    return {"closed": pos_id}


class SLTPBody(BaseModel):
    sl: float | None = None
    tp: float | None = None


@router.patch("/positions/{pos_id}/sltp")
async def edit_sltp(
    pos_id: int, body: SLTPBody, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    pos = await session.get(PositionModel, pos_id)
    if not pos or pos.status != "OPEN":
        raise HTTPException(404, "vị thế không mở")
    om = request.app.state.order_manager
    ex = _route_executor(request, pos.bot_id, pos.symbol)

    async def do():
        if ex:
            await ex.modify_sltp(body.sl, body.tp)
        else:
            pos.sl, pos.tp = body.sl, body.tp
            await session.commit()

    await om.execute(
        source="MANUAL", action="EDIT_SLTP", mode=pos.mode, bot_id=pos.bot_id,
        symbol=pos.symbol, detail={"position_id": pos_id, "sl": body.sl, "tp": body.tp}, do=do,
    )
    return {"updated": pos_id}


class ManualOrder(BaseModel):
    symbol: str
    side: str  # BUY | SELL
    type: str = "MARKET"  # MARKET | LIMIT
    qty: float
    price: float | None = None  # cho LIMIT
    sl: float | None = None
    tp: float | None = None
    ref_price: float | None = None  # giá hiện tại cho MARKET
    mode: str = "PAPER"


@router.post("/orders")
async def manual_order(body: ManualOrder, request: Request) -> dict:
    if body.mode != "PAPER":
        raise HTTPException(400, f"mode {body.mode} chưa hỗ trợ (P3: PAPER)")
    if body.side not in ("BUY", "SELL"):
        raise HTTPException(400, "side phải BUY/SELL")
    om = request.app.state.order_manager
    ex = await request.app.state.manual_trader.ensure(body.symbol, body.mode)
    if ex.account_id is not None:  # đủ ký quỹ mới cho vào lệnh (như sàn)
        accounts = request.app.state.accounts
        acc = await accounts.get(ex.account_id)
        st = await accounts.snapshot(ex.account_id)
        px = body.price if body.type == "LIMIT" and body.price else (body.ref_price or 0)
        cost = body.qty * px / float(acc.leverage) + body.qty * px * float(acc.taker_fee)
        freed = ex.engine.margin() if ex.engine.position else 0.0
        if px and cost > st.available + freed:
            raise HTTPException(
                400,
                f"không đủ số dư: cần ~{cost:.2f} USDT ký quỹ+phí, khả dụng "
                f"{max(0.0, st.available + freed):.2f} USDT",
            )

    async def do():
        if body.type == "MARKET" and body.ref_price:
            await ex.seed_price(body.ref_price)
        await ex.submit(
            Signal(
                action=body.side, symbol=body.symbol, size=body.qty,
                order_type=body.type, price=body.price, sl=body.sl, tp=body.tp,
            )
        )

    await om.execute(
        source="MANUAL", action="OPEN", mode=body.mode, symbol=body.symbol,
        detail={"side": body.side, "type": body.type, "qty": body.qty}, do=do,
    )
    return {"submitted": True, "symbol": body.symbol}


@router.delete("/orders/{order_id}")
async def cancel_order(
    order_id: int, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    o = await session.get(OrderModel, order_id)
    if not o or o.status != "NEW":
        raise HTTPException(404, "không có lệnh chờ để hủy")
    om = request.app.state.order_manager
    ex = _route_executor(request, o.bot_id, o.symbol)

    async def do():
        if ex:
            await ex.cancel()  # hủy pending của symbol → mark CANCELLED + broadcast
        else:
            o.status = "CANCELLED"
            await session.commit()

    await om.execute(
        source="MANUAL", action="CANCEL", mode=o.mode, bot_id=o.bot_id,
        symbol=o.symbol, detail={"order_id": order_id}, do=do,
    )
    return {"cancelled": order_id}


@router.get("/audit")
async def list_audit(request: Request, limit: int = 100) -> list[dict]:
    return await request.app.state.order_manager.list_audit(limit)


async def _db_close(
    session: AsyncSession, pos: PositionModel, ref_price: float | None, accounts=None
) -> None:
    """Đóng vị thế ở mức DB khi bot đã dừng (không còn engine)."""
    if ref_price is None:
        raise HTTPException(400, "cần ref_price để đóng vị thế của bot đã dừng")
    entry = float(pos.entry_price)
    qty = float(pos.qty)
    pnl = (ref_price - entry) * qty if pos.side == "LONG" else (entry - ref_price) * qty
    pos.status = "CLOSED"
    pos.exit_price = ref_price
    exit_fee = 0.0
    if accounts and pos.account_id is not None:
        acc = await accounts.get(pos.account_id)
        exit_fee = float(acc.taker_fee) * ref_price * qty if acc else 0.0
    pos.pnl = pnl - float(pos.fee or 0) - exit_fee
    pos.fee = float(pos.fee or 0) + exit_fee
    pos.exit_reason = "MANUAL"
    pos.closed_at = datetime.now(UTC)
    await session.commit()
    if accounts and pos.account_id is not None:
        await accounts.record_close(
            pos.account_id, gross=pnl, exit_fee=exit_fee, position_id=pos.id,
            bot_id=pos.bot_id, symbol=pos.symbol, reason="MANUAL",
        )
