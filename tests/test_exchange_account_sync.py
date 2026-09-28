"""P9b: sync the exchange account into the ledger (real DB, fake client; skips without a DB)."""

import os

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.account.service import AccountService
from app.orders.models import Account, AccountTxn

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://botuser:botpass@localhost:5432/tradingbot"
)
NAME = "__test_exch__"


class FakeEx:
    def __init__(self):
        self.snap = {"wallet": 500.0, "equity": 495.0, "unrealized": -5.0, "margin": 100.0,
                     "available": 395.0}
        self.rows = []
        self.fail = None

    async def account(self):
        if self.fail:
            raise RuntimeError(self.fail)
        return dict(self.snap)

    async def income(self, since):
        return [r for r in self.rows if r["ts"] >= since]


@pytest.fixture
async def env():
    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect():
            pass
    except Exception:
        pytest.skip("DB not available")
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s:
        await s.execute(delete(Account).where(Account.name == NAME))
        a = Account(name=NAME, mode="TESTNET", balance=0, peak_equity=0, max_dd_pct=15)
        s.add(a)
        await s.commit()
    yield sf, AccountService(sf), a.id
    async with sf() as s:
        await s.execute(delete(Account).where(Account.name == NAME))
        await s.commit()
    await engine.dispose()


async def ledger(sf, aid):
    async with sf() as s:
        rows = (await s.execute(
            select(AccountTxn).where(AccountTxn.account_id == aid).order_by(AccountTxn.id)
        )).scalars().all()
        acc = await s.get(Account, aid)
    return rows, acc


async def test_first_sync_then_income_import_dedup_and_reconcile(env):
    sf, svc, aid = env
    ex = FakeEx()
    await svc.sync_exchange(aid, ex)
    rows, acc = await ledger(sf, aid)
    assert [(r.type, float(r.amount)) for r in rows] == [("ADJUST", 500.0)]
    assert float(acc.peak_equity) == 500  # the initial balance doesn't count as profit
    st = await svc.snapshot(aid)
    assert (st.equity, st.used_margin, st.available) == (495, 100, 395)  # EXCHANGE figures

    c = int(acc.income_cursor)
    ex.rows = [
        {"ext_id": "1:REALIZED_PNL", "type": "REALIZED_PNL", "amount": 12.0, "asset": "USDT",
         "symbol": "BTCUSDT", "ts": c + 10},
        {"ext_id": "1:COMMISSION", "type": "COMMISSION", "amount": -0.6, "asset": "USDT",
         "symbol": "BTCUSDT", "ts": c + 10},
        {"ext_id": "2:FUNDING_FEE", "type": "FUNDING_FEE", "amount": -0.4, "asset": "USDT",
         "symbol": "BTCUSDT", "ts": c + 20},
        {"ext_id": "3:TRANSFER", "type": "TRANSFER", "amount": 100.0, "asset": "USDT",
         "symbol": None, "ts": c + 30},
        {"ext_id": "4:COMMISSION", "type": "COMMISSION", "amount": -1.0, "asset": "BNB",
         "symbol": "BTCUSDT", "ts": c + 40},  # fee paid in BNB → not booked to the USDT ledger
    ]
    ex.snap["wallet"] = 611.0  # = 500 + 12 − 0.6 − 0.4 + 100
    await svc.sync_exchange(aid, ex)
    await svc.sync_exchange(aid, ex)  # 2nd run: no duplicate imports
    rows, acc = await ledger(sf, aid)
    assert [r.type for r in rows] == ["ADJUST", "REALIZED_PNL", "FEE", "FUNDING", "DEPOSIT"]
    assert float(acc.balance) == pytest.approx(611.0)
    async with sf() as s:
        total = (await s.execute(
            select(func.sum(AccountTxn.amount)).where(AccountTxn.account_id == aid)
        )).scalar_one()
    assert float(total) == pytest.approx(611.0)

    # exchange wallet differs from ledger (e.g. income not arrived yet) → ADJUST reconciliation row
    ex.snap["wallet"] = 610.0
    await svc.sync_exchange(aid, ex)
    rows, acc = await ledger(sf, aid)
    assert rows[-1].type == "ADJUST" and float(rows[-1].amount) == pytest.approx(-1.0)
    assert float(acc.balance) == pytest.approx(610.0)


async def test_sync_error_recorded_and_no_deposit(env):
    sf, svc, aid = env
    ex = FakeEx()
    ex.fail = "APIError(code=-2015): Invalid API-key"
    await svc.sync_exchange(aid, ex)
    _, acc = await ledger(sf, aid)
    assert "Invalid API-key" in acc.sync_error and acc.last_sync_at is not None
    with pytest.raises(ValueError, match="on Binance"):
        await svc.deposit(aid, 100)
    with pytest.raises(ValueError, match="on Binance"):
        await svc.withdraw(aid, 10)
