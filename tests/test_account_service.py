"""P9a end-to-end with a real DB (skipped without a DB): runner sizes by equity →
PaperExecutor simulates fees/slippage → ledger matches balance → daily-loss guard → restore."""

import os

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.account.service import AccountService
from app.execution.paper import PaperExecutor
from app.orders.models import Account, AccountTxn, OrderModel, PositionModel
from app.strategy.base import Signal
from app.strategy.runner import StrategyRunner

SYM = "TESTACCT"
DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://botuser:botpass@localhost:5432/tradingbot"
)


class FakeBus:
    def __init__(self):
        self.msgs = []

    async def publish(self, topic, message):
        self.msgs.append((topic, message))


async def _clean(sf):
    async with sf() as s:
        await s.execute(delete(OrderModel).where(OrderModel.symbol == SYM))
        await s.execute(delete(PositionModel).where(PositionModel.symbol == SYM))
        await s.execute(delete(Account).where(Account.name == "__test_acct__"))
        await s.commit()


@pytest.fixture
async def env():
    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect():
            pass
    except Exception:
        pytest.skip("DB not available")
    sf = async_sessionmaker(engine, expire_on_commit=False)
    await _clean(sf)
    async with sf() as s:
        a = Account(name="__test_acct__", balance=0, peak_equity=0, taker_fee=0.0005,
                    maker_fee=0.0002, slippage_bps=2, leverage=1, max_risk_pct=2,
                    daily_loss_pct=1)
        s.add(a)
        await s.commit()
    svc = AccountService(sf)
    await svc.deposit(a.id, 1000, "capital")
    bus = FakeBus()
    ex = PaperExecutor(None, SYM, "PAPER", bus, sf)
    ex.attach_account(await svc.get(a.id), svc)
    runner = StrategyRunner(
        99, None, ex, bus, SYM, "1m", sf, accounts=svc, account_id=a.id,
        sizing={"method": "risk_pct", "value": 1},
    )
    yield sf, svc, a.id, ex, runner, bus
    await _clean(sf)
    await engine.dispose()


async def _ledger_sum(sf, aid):
    async with sf() as s:
        return float((await s.execute(
            select(func.sum(AccountTxn.amount)).where(AccountTxn.account_id == aid)
        )).scalar_one())


async def test_sized_trade_fees_ledger_and_daily_halt(env):
    sf, svc, aid, ex, runner, bus = env
    await ex.on_price(100)
    await runner._dispatch(Signal("BUY", SYM, size=0.001, sl=98), 100)

    p = ex.engine.position
    assert p.qty == pytest.approx(5)  # 1% × 1000 / (100 − 98), not the strategy's 0.001
    assert p.entry_price == pytest.approx(100.02)  # 2 bps slippage

    st = await svc.snapshot(aid)
    assert st.used_margin == pytest.approx(5 * 100.02)
    assert st.balance == pytest.approx(1000 - 0.0005 * 100.02 * 5)  # entry fee deducted

    await ex.on_price(97)  # gaps past SL 98 → fills at 97 (gap) minus slippage
    assert ex.engine.position is None
    async with sf() as s:
        q = select(PositionModel).where(PositionModel.symbol == SYM)
        pos = (await s.execute(q)).scalar_one()
        acc = await s.get(Account, aid)
    exit_px = 97 * (1 - 0.0002)
    gross = (exit_px - 100.02) * 5
    fees = 0.0005 * 5 * (100.02 + exit_px)
    assert float(pos.exit_price) == pytest.approx(exit_px)
    assert float(pos.pnl) == pytest.approx(gross - fees)
    assert float(pos.fee) == pytest.approx(fees)
    # the ledger is the source of truth: balance = sum of all rows
    assert float(acc.balance) == pytest.approx(1000 + gross - fees)
    assert await _ledger_sum(sf, aid) == pytest.approx(float(acc.balance))

    # loss ~1.5% > 1% daily limit → paused until end of day, new orders blocked
    assert acc.halted_until is not None
    await runner._dispatch(Signal("SELL", SYM, sl=102), 97)
    assert ex.engine.position is None
    assert any(t == "risk" for t, _ in bus.msgs)


async def test_withdraw_limited_by_margin_and_deposit(env):
    sf, svc, aid, ex, runner, _ = env
    await ex.on_price(100)
    await runner._dispatch(Signal("BUY", SYM, sl=98), 100)  # locks ~500 margin
    st = await svc.snapshot(aid)
    with pytest.raises(ValueError, match="at most"):
        await svc.withdraw(aid, st.available + 1)
    await svc.withdraw(aid, 100)
    await svc.deposit(aid, 50)
    async with sf() as s:
        acc = await s.get(Account, aid)
    assert await _ledger_sum(sf, aid) == pytest.approx(float(acc.balance))


async def test_restore_open_position_after_restart(env):
    sf, svc, aid, ex, runner, bus = env
    await ex.on_price(100)
    await runner._dispatch(Signal("SELL", SYM, sl=102), 100)
    # "restart": new executor, reload from DB then SL hit still closes + books correctly
    ex2 = PaperExecutor(None, SYM, "PAPER", bus, sf)
    ex2.attach_account(await svc.get(aid), svc)
    assert await ex2.restore_open()
    assert ex2.engine.position.side == "SHORT"
    await ex2.on_price(103)
    async with sf() as s:
        q = select(PositionModel).where(PositionModel.symbol == SYM)
        pos = (await s.execute(q)).scalar_one()
        acc = await s.get(Account, aid)
    assert pos.status == "CLOSED" and pos.exit_reason == "SL"
    assert await _ledger_sum(sf, aid) == pytest.approx(float(acc.balance))
