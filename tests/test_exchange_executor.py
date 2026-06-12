"""TestnetExecutor — ánh xạ lệnh sàn (client giả), ext_id, SL/TP, auto-cancel timeout.

Không cần key thật: dùng FakeClient + FakeBus + fake session_factory (no-op DB).
"""

import asyncio

from app.execution.exchange import ExchangeExecutor
from app.strategy.base import Signal


class FakeClient:
    def __init__(self, price=100.0):
        self.price = price
        self.calls = []
        self._oid = 0

    def _id(self):
        self._oid += 1
        return f"ext{self._oid}"

    async def market_order(self, symbol, side, qty):
        self.calls.append(("market", symbol, side, qty))
        return {"orderId": self._id(), "price": self.price, "status": "FILLED", "qty": qty}

    async def limit_order(self, symbol, side, qty, price):
        self.calls.append(("limit", symbol, side, qty, price))
        return {"orderId": self._id(), "price": price, "status": "NEW", "qty": qty}

    async def cancel(self, symbol, order_id):
        self.calls.append(("cancel", symbol, order_id))


class FakeBus:
    def __init__(self):
        self.msgs = []

    async def publish(self, topic, message):
        self.msgs.append((topic, message))


class FakeSession:
    def __init__(self, store):
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def add(self, obj):
        # gán id giả cho PositionModel để flush() có id
        if not getattr(obj, "id", None):
            obj.id = 1
        self._store.append(("add", type(obj).__name__))

    async def execute(self, stmt):
        self._store.append(("execute", str(stmt.__class__.__name__)))

    async def flush(self):
        pass

    async def commit(self):
        pass


def make_sf(store):
    def sf():
        return FakeSession(store)

    return sf


def make_exec(client, timeout=None):
    bus = FakeBus()
    store: list = []
    ex = ExchangeExecutor(1, "BTCUSDT", "TESTNET", bus, make_sf(store), client, timeout=timeout)
    return ex, bus, store


async def test_market_buy_places_real_order_and_opens_position():
    client = FakeClient(price=100)
    ex, bus, store = make_exec(client)
    await ex.submit(Signal("BUY", "BTCUSDT", size=1))
    assert ("market", "BTCUSDT", "BUY", 1) in client.calls
    assert ex.engine.position is not None
    assert ex.engine.position.side == "LONG"
    # broadcast có order FILLED + position OPEN
    assert any(m.get("type") == "order" and m.get("status") == "FILLED" for _, m in bus.msgs)
    assert any(m.get("status") == "OPEN" for _, m in bus.msgs)


async def test_close_signal_places_opposite_market_order():
    client = FakeClient(price=100)
    ex, _, _ = make_exec(client)
    await ex.submit(Signal("BUY", "BTCUSDT", size=2))
    client.price = 110
    await ex.submit(Signal("CLOSE", "BTCUSDT"))
    assert ("market", "BTCUSDT", "SELL", 2) in client.calls
    assert ex.engine.position is None


async def test_sltp_hit_sends_real_close():
    client = FakeClient(price=100)
    ex, bus, _ = make_exec(client)
    await ex.submit(Signal("BUY", "BTCUSDT", size=1, sl=95, tp=120))
    client.price = 94
    await ex.on_price(94)  # chạm SL → đóng thật
    assert ("market", "BTCUSDT", "SELL", 1) in client.calls
    assert ex.engine.position is None


async def test_limit_order_placed_with_ext_id():
    client = FakeClient()
    ex, bus, _ = make_exec(client)
    await ex.submit(Signal("BUY", "BTCUSDT", size=1, order_type="LIMIT", price=95))
    assert ("limit", "BTCUSDT", "BUY", 1, 95) in client.calls
    assert ex.engine.position is None  # limit chờ trên sàn, chưa mở vị thế


async def test_limit_auto_cancel_after_timeout():
    client = FakeClient()
    ex, bus, _ = make_exec(client, timeout=0.05)
    await ex.submit(Signal("BUY", "BTCUSDT", size=1, order_type="LIMIT", price=95))
    await asyncio.sleep(0.12)  # quá timeout
    assert any(c[0] == "cancel" for c in client.calls)


async def test_manual_cancel_calls_exchange():
    client = FakeClient()
    ex, _, _ = make_exec(client)
    await ex.cancel("ext123")
    assert ("cancel", "BTCUSDT", "ext123") in client.calls
