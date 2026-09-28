"""Accounts REST (P9a): balance, deposit/withdraw, sim config + guardrails, ledger, equity."""

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.risk import SIZING_METHODS
from app.account.service import is_exchange
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
        # true cumulative PnL = equity − net deposits (deposits/withdrawals aren't profit)
        "total_pnl": st.equity - net_in,
        "total_pnl_pct": (st.equity - net_in) / net_in * 100 if net_in > 0 else None,
        "total_fees": -float(fees),
        "n_bots": n_bots,
        "market": a.market,
        "is_exchange": is_exchange(a),
        "last_sync_at": a.last_sync_at.isoformat() if a.last_sync_at else None,
        "sync_error": a.sync_error,
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
        raise HTTPException(404, "account not found")
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
    mode: str = "PAPER"  # PAPER | TESTNET | LIVE
    initial_balance: float | None = Field(None, gt=0)  # PAPER: required; exchange: from Binance
    confirm: str | None = None  # LIVE: must type "LIVE"


class PatchAccount(Settings):
    name: str | None = Field(None, min_length=1, max_length=60)
    # guardrail fields sent as null DISABLE them → need to know which fields are in the body
    model_config = {"extra": "forbid"}


_DEFAULT_LIMITS = {"max_risk_pct": 2, "max_open_risk_pct": 6, "daily_loss_pct": 3,
                   "max_dd_pct": 15}


@router.post("/accounts")
async def create_account(
    body: CreateAccount, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    mode = body.mode.upper()
    if mode not in ("PAPER", "TESTNET", "LIVE"):
        raise HTTPException(400, f"invalid mode {mode}")
    if mode == "PAPER" and not body.initial_balance:
        raise HTTPException(422, "a paper account requires an initial balance")
    if mode != "PAPER":
        from app.execution.clients import check_mode

        try:
            check_mode(mode)  # LIVE: ENABLE_LIVE; both: key present in .env
        except ValueError as e:
            raise HTTPException(403 if mode == "LIVE" else 400, str(e)) from e
        if mode == "LIVE" and body.confirm != "LIVE":
            raise HTTPException(400, "a LIVE account (real money) requires typing 'LIVE'")
        exists = (await session.execute(select(Account.id).where(Account.mode == mode))).first()
        if exists:
            raise HTTPException(409, f"a {mode} account already exists (1 key pair per mode)")
    vals = {k: v for k, v in body.model_dump().items()
            if k not in ("name", "initial_balance", "mode", "confirm") and v is not None}
    a = Account(
        name=body.name, mode=mode, balance=0, peak_equity=0,
        **{**_DEFAULT_LIMITS, **vals},
    )
    session.add(a)
    await session.commit()
    await request.app.state.order_manager.write_audit(
        source="MANUAL", action="ACCOUNT_CREATE", mode=mode,
        detail={"account_id": a.id, "name": a.name, "initial_balance": body.initial_balance},
    )
    if mode == "PAPER":
        await request.app.state.accounts.deposit(a.id, body.initial_balance, "Initial balance")
    else:  # read the real balance now (connection error → sync_error, account still created)
        await request.app.state.accounts.sync_exchange(a.id)
    await session.refresh(a)
    return await _account_dict(request, session, a)


@router.patch("/accounts/{account_id}")
async def patch_account(
    account_id: int, body: PatchAccount, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    a = await session.get(Account, account_id)
    if not a:
        raise HTTPException(404, "account not found")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        if k in ("name", "leverage", "taker_fee", "maker_fee", "slippage_bps") and v is None:
            continue  # required fields cannot be disabled
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
        raise HTTPException(404, "account not found")
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


@router.post("/accounts/{account_id}/sync")
async def sync_now(
    account_id: int, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    """Sync balance/ledger from Binance now (TESTNET/LIVE accounts)."""
    accounts = request.app.state.accounts
    a = await accounts.get(account_id)
    if not a:
        raise HTTPException(404, "account not found")
    if not is_exchange(a):
        raise HTTPException(400, "paper accounts do not need syncing")
    await accounts.sync_exchange(account_id)
    a = await session.get(Account, account_id)
    await session.refresh(a)
    return await _account_dict(request, session, a)


@router.post("/accounts/{account_id}/resume")
async def resume(account_id: int, request: Request) -> dict:
    """Unlock a HALTED account (drawdown/daily loss) — the user has reviewed it."""
    a = await request.app.state.accounts.get(account_id)
    if not a:
        raise HTTPException(404, "account not found")
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
    """Wallet balance curve from the ledger + current equity point. The 'equity' chart (excluding
    deposits/withdrawals) = balance − cumulative net deposits → reflects trading PnL only."""
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
        t = int(ts.timestamp()) * 1000  # bucket per second: chart needs strictly increasing time
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
