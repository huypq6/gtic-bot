"""REST tài khoản (P9a): số dư, nạp/rút, cấu hình mô phỏng + rào chắn, sổ cái, đường vốn."""

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.risk import SIZING_METHODS
from app.db import get_session
from app.orders.models import Account, AccountTxn, Bot, PositionModel

router = APIRouter(prefix="/api")


def _f(v):
    return float(v) if v is not None else None


async def _account_dict(request: Request, session: AsyncSession, a: Account) -> dict:
    st = await request.app.state.accounts.snapshot(a.id)
    deposits = (
        await session.execute(
            select(AccountTxn.type, func.coalesce(func.sum(AccountTxn.amount), 0))
            .where(AccountTxn.account_id == a.id, AccountTxn.type.in_(("DEPOSIT", "WITHDRAW")))
            .group_by(AccountTxn.type)
        )
    ).all()
    flows = {t: float(v) for t, v in deposits}
    net_in = flows.get("DEPOSIT", 0.0) + flows.get("WITHDRAW", 0.0)
    fees = (
        await session.execute(
            select(func.coalesce(func.sum(AccountTxn.amount), 0))
            .where(AccountTxn.account_id == a.id, AccountTxn.type == "FEE")
        )
    ).scalar_one()
    n_bots = (
        await session.execute(select(func.count()).where(Bot.account_id == a.id))
    ).scalar_one()
    now = datetime.now(UTC)
    return {
        "id": a.id, "name": a.name, "mode": a.mode, "currency": a.currency,
        "status": a.status, "halted_reason": a.halted_reason,
        "halted_until": a.halted_until.isoformat() if a.halted_until else None,
        "paused_today": bool(a.halted_until and a.halted_until > now),
        "settings": {
            "leverage": _f(a.leverage), "taker_fee": _f(a.taker_fee),
            "maker_fee": _f(a.maker_fee), "slippage_bps": _f(a.slippage_bps),
            "max_risk_pct": _f(a.max_risk_pct), "max_open_risk_pct": _f(a.max_open_risk_pct),
            "max_positions": a.max_positions, "daily_loss_pct": _f(a.daily_loss_pct),
            "max_dd_pct": _f(a.max_dd_pct),
        },
        **asdict(st),
        "dd_pct": st.dd_pct,
        "daily_pnl_pct": st.daily_pnl_pct,
        "net_deposit": net_in,
        # lãi/lỗ tích lũy thật = equity − tiền đã nạp ròng (không tính nạp/rút là lãi)
        "total_pnl": st.equity - net_in,
        "total_pnl_pct": (st.equity - net_in) / net_in * 100 if net_in > 0 else None,
        "total_fees": -float(fees),
        "n_bots": n_bots,
    }


@router.get("/accounts")
async def list_accounts(
    request: Request, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = (await session.execute(select(Account).order_by(Account.id))).scalars().all()
    return [await _account_dict(request, session, a) for a in rows]


@router.get("/accounts/sizing-methods")
async def sizing_methods() -> dict:
    return SIZING_METHODS


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: int, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    a = await session.get(Account, account_id)
    if not a:
        raise HTTPException(404, "tài khoản không tồn tại")
    return await _account_dict(request, session, a)


class Settings(BaseModel):
    leverage: float | None = Field(None, ge=1, le=20)
    taker_fee: float | None = Field(None, ge=0, le=0.01)
    maker_fee: float | None = Field(None, ge=0, le=0.01)
    slippage_bps: float | None = Field(None, ge=0, le=100)
    max_risk_pct: float | None = Field(None, gt=0, le=100)
    max_open_risk_pct: float | None = Field(None, gt=0, le=100)
    max_positions: int | None = Field(None, ge=1)
    daily_loss_pct: float | None = Field(None, gt=0, le=100)
    max_dd_pct: float | None = Field(None, gt=0, le=100)


class CreateAccount(Settings):
    name: str = Field(min_length=1, max_length=60)
    initial_balance: float = Field(gt=0)


class PatchAccount(Settings):
    name: str | None = Field(None, min_length=1, max_length=60)
    # các trường rào chắn gửi null để TẮT → cần biết trường nào có mặt trong body
    model_config = {"extra": "forbid"}


_DEFAULT_LIMITS = {"max_risk_pct": 2, "max_open_risk_pct": 6, "daily_loss_pct": 3,
                   "max_dd_pct": 15}


@router.post("/accounts")
async def create_account(
    body: CreateAccount, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    vals = {k: v for k, v in body.model_dump().items()
            if k not in ("name", "initial_balance") and v is not None}
    a = Account(
        name=body.name, mode="PAPER", balance=0, peak_equity=0,
        **{**_DEFAULT_LIMITS, **vals},
    )
    session.add(a)
    await session.commit()
    await request.app.state.accounts.deposit(a.id, body.initial_balance, "Vốn ban đầu")
    await request.app.state.order_manager.write_audit(
        source="MANUAL", action="ACCOUNT_CREATE", mode="PAPER",
        detail={"account_id": a.id, "name": a.name, "initial_balance": body.initial_balance},
    )
    await session.refresh(a)
    return await _account_dict(request, session, a)


@router.patch("/accounts/{account_id}")
async def patch_account(
    account_id: int, body: PatchAccount, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    a = await session.get(Account, account_id)
    if not a:
        raise HTTPException(404, "tài khoản không tồn tại")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        if k in ("name", "leverage", "taker_fee", "maker_fee", "slippage_bps") and v is None:
            continue  # không cho tắt các trường bắt buộc
        setattr(a, k, v)
    await session.commit()
    await request.app.state.order_manager.write_audit(
        source="MANUAL", action="ACCOUNT_SETTINGS", mode=a.mode,
        detail={"account_id": account_id, **changes},
    )
    await session.refresh(a)
    request.app.state.bot_manager.refresh_account(a)
    return await _account_dict(request, session, a)


class Money(BaseModel):
    amount: float = Field(gt=0)
    note: str | None = Field(None, max_length=200)


async def _move(request: Request, account_id: int, body: Money, kind: str) -> dict:
    accounts = request.app.state.accounts
    a = await accounts.get(account_id)
    if not a:
        raise HTTPException(404, "tài khoản không tồn tại")
    await request.app.state.order_manager.write_audit(
        source="MANUAL", action=kind, mode=a.mode,
        detail={"account_id": account_id, "amount": body.amount, "note": body.note},
    )
    try:
        fn = accounts.deposit if kind == "DEPOSIT" else accounts.withdraw
        bal = await fn(account_id, body.amount, body.note)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"account_id": account_id, "balance": bal}


@router.post("/accounts/{account_id}/deposit")
async def deposit(account_id: int, body: Money, request: Request) -> dict:
    return await _move(request, account_id, body, "DEPOSIT")


@router.post("/accounts/{account_id}/withdraw")
async def withdraw(account_id: int, body: Money, request: Request) -> dict:
    return await _move(request, account_id, body, "WITHDRAW")


@router.post("/accounts/{account_id}/resume")
async def resume(account_id: int, request: Request) -> dict:
    """Mở khóa tài khoản bị DỪNG (sụt vốn/lỗ ngày) — người dùng đã xem xét."""
    a = await request.app.state.accounts.get(account_id)
    if not a:
        raise HTTPException(404, "tài khoản không tồn tại")
    await request.app.state.order_manager.write_audit(
        source="MANUAL", action="ACCOUNT_RESUME", mode=a.mode,
        detail={"account_id": account_id, "was": a.halted_reason},
    )
    await request.app.state.accounts.resume(account_id)
    return {"resumed": account_id}


@router.get("/accounts/{account_id}/ledger")
async def ledger(
    account_id: int, limit: int = 200, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = (
        await session.execute(
            select(AccountTxn).where(AccountTxn.account_id == account_id)
            .order_by(AccountTxn.id.desc()).limit(min(limit, 2000))
        )
    ).scalars().all()
    return [
        {
            "id": t.id, "ts": int(t.ts.timestamp() * 1000), "type": t.type,
            "amount": float(t.amount), "balance_after": float(t.balance_after),
            "position_id": t.position_id, "bot_id": t.bot_id, "symbol": t.symbol,
            "note": t.note,
        }
        for t in rows
    ]


@router.get("/accounts/{account_id}/equity")
async def equity_curve(
    account_id: int, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    """Đường số dư ví theo sổ cái + điểm equity hiện tại. Đồ thị 'vốn' (loại trừ nạp/rút)
    = số dư − tiền nạp ròng lũy kế → chỉ phản ánh lãi/lỗ giao dịch."""
    rows = (
        await session.execute(
            select(AccountTxn.ts, AccountTxn.type, AccountTxn.amount, AccountTxn.balance_after)
            .where(AccountTxn.account_id == account_id).order_by(AccountTxn.ts, AccountTxn.id)
        )
    ).all()
    balance: list[list[float]] = []
    pnl: list[list[float]] = []
    net_in = 0.0
    for ts, typ, amt, bal in rows:
        if typ in ("DEPOSIT", "WITHDRAW"):
            net_in += float(amt)
        t = int(ts.timestamp()) * 1000  # gộp theo giây: chart cần thời gian tăng ngặt
        if balance and balance[-1][0] >= t:
            balance[-1][1], pnl[-1][1] = float(bal), float(bal) - net_in
        else:
            balance.append([t, float(bal)])
            pnl.append([t, float(bal) - net_in])
    st = await request.app.state.accounts.snapshot(account_id)
    now = int(datetime.now(UTC).timestamp()) * 1000
    if balance and balance[-1][0] >= now:
        balance.pop()
        pnl.pop()
    balance.append([now, st.equity])
    pnl.append([now, st.equity - net_in])
    return {"balance": balance, "pnl": pnl}


@router.get("/accounts/{account_id}/positions")
async def account_positions(
    account_id: int, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = (
        await session.execute(
            select(PositionModel).where(
                PositionModel.account_id == account_id, PositionModel.status == "OPEN"
            )
        )
    ).scalars().all()
    return [
        {
            "id": p.id, "bot_id": p.bot_id, "symbol": p.symbol, "side": p.side,
            "qty": float(p.qty), "entry_price": float(p.entry_price), "sl": _f(p.sl),
            "tp": _f(p.tp), "margin": _f(p.margin), "risk_amount": _f(p.risk_amount),
            "fee": _f(p.fee),
        }
        for p in rows
    ]
