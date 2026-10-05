"""PaperExecutor end-to-end with a real DB (skipped without a DB, e.g. CI).

Checks: engine → persist (position/order) → bus broadcast. Uses a sentinel symbol to
clean up after the test.
"""

import os

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.execution.paper import PaperExecutor
from app.orders.models import OrderModel, PositionModel
from app.strategy.base import Signal

TEST_SYMBOL = "TESTPAPER"
DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://botuser:botpass@localhost:5432/tradingbot"
)


class FakeBus:
    def __init__(self):
        self.msgs = []

    async def publish(self, topic, message):
        self.msgs.append((topic, message))


@pytest.fixture
async def session_factory():
    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect():
            pass
    except Exception:
        pytest.skip("DB not available — skipping executor DB test")
    sf = async_sessionmaker(engine, expire_on_commit=False)
    # clean up first
    async with sf() as s:
        await s.execute(delete(OrderModel).where(OrderModel.symbol == TEST_SYMBOL))
        await s.execute(delete(PositionModel).where(PositionModel.symbol == TEST_SYMBOL))
        await s.commit()
    yield sf
    async with sf() as s:
        await s.execute(delete(OrderModel).where(OrderModel.symbol == TEST_SYMBOL))
        await s.execute(delete(PositionModel).where(PositionModel.symbol == TEST_SYMBOL))
        await s.commit()
    await engine.dispose()


async def test_buy_then_tp_persists_and_broadcasts(session_factory):
    bus = FakeBus()
    ex = PaperExecutor(None, TEST_SYMBOL, "PAPER", bus, session_factory)

    await ex.on_price(100)  # set last price
    await ex.submit(Signal("BUY", TEST_SYMBOL, size=2, tp=110, sl=90))
    await ex.on_price(111)  # TP hit → close

    # broadcast: has order + position OPEN + position CLOSED
    types = [(t, m.get("type"), m.get("status")) for t, m in bus.msgs]
    assert any(m.get("type") == "order" for _, m in bus.msgs)
    assert any(m.get("status") == "OPEN" for _, m in bus.msgs)
    closed = [m for _, m in bus.msgs if m.get("status") == "CLOSED"]
    assert closed and closed[0]["pnl"] == (110 - 100) * 2  # +20
    assert types  # not empty

    # DB: position is CLOSED with the correct pnl
    async with session_factory() as s:
        rows = (
            await s.execute(select(PositionModel).where(PositionModel.symbol == TEST_SYMBOL))
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "CLOSED"
    assert float(rows[0].pnl) == 20.0
    # review: exit reason + initial SL (the 1R reference) are stored
    assert rows[0].exit_reason == "TP"
    assert float(rows[0].init_sl) == 90.0

    # 1 trade = 2 fills, both linked to the position: entry (OPEN) + exit (CLOSE)
    async with session_factory() as s:
        orders = (
            await s.execute(
                select(OrderModel).where(OrderModel.symbol == TEST_SYMBOL).order_by(OrderModel.id)
            )
        ).scalars().all()
    assert [(o.side, o.intent, o.position_id) for o in orders] == [
        ("BUY", "OPEN", rows[0].id),
        ("SELL", "CLOSE", rows[0].id),
    ]


async def test_position_snapshot_survives_bot_meta(session_factory):
    """Strategy/tf/params snapshot written to the position at open (kept if the bot is deleted)."""
    ex = PaperExecutor(None, TEST_SYMBOL, "PAPER", FakeBus(), session_factory)
    ex.trade_meta = {"strategy": "demo v1", "tf": "15m", "params": {"size": 1}}
    await ex.on_price(100)
    await ex.submit(Signal("SELL", TEST_SYMBOL, size=1, sl=105))
    async with session_factory() as s:
        row = (
            await s.execute(select(PositionModel).where(PositionModel.symbol == TEST_SYMBOL))
        ).scalar_one()
    assert (row.strategy, row.tf, row.params) == ("demo v1", "15m", {"size": 1})
    assert row.source == "MANUAL" and row.bot_ref is None
