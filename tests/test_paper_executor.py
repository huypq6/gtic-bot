"""PaperExecutor end-to-end với DB thật (skip nếu không có DB, vd CI).

Kiểm: engine → persist (position/order) → broadcast bus. Dùng symbol sentinel để
dọn sạch sau test.
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
        pytest.skip("DB không sẵn sàng — bỏ qua test executor DB")
    sf = async_sessionmaker(engine, expire_on_commit=False)
    # dọn trước
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
    await ex.on_price(111)  # chạm TP → đóng

    # broadcast: có order + position OPEN + position CLOSED
    types = [(t, m.get("type"), m.get("status")) for t, m in bus.msgs]
    assert any(m.get("type") == "order" for _, m in bus.msgs)
    assert any(m.get("status") == "OPEN" for _, m in bus.msgs)
    closed = [m for _, m in bus.msgs if m.get("status") == "CLOSED"]
    assert closed and closed[0]["pnl"] == (110 - 100) * 2  # +20
    assert types  # không rỗng

    # DB: position đã CLOSED với pnl đúng
    async with session_factory() as s:
        rows = (
            await s.execute(select(PositionModel).where(PositionModel.symbol == TEST_SYMBOL))
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "CLOSED"
    assert float(rows[0].pnl) == 20.0
