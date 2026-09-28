"""TestnetExecutor — exchange order mapping (fake client), ext_id, SL/TP, auto-cancel timeout.

No real keys needed: uses FakeClient + FakeBus + a fake session_factory (no-op DB).
"""

import asyncio

import pytest

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
        # assign a fake id to PositionModel so flush() yields an id
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
    # broadcast contains order FILLED + position OPEN
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
    await ex.on_price(94)  # SL hit → real close
    assert ("market", "BTCUSDT", "SELL", 1) in client.calls
    assert ex.engine.position is None


async def test_limit_order_placed_with_ext_id():
    client = FakeClient()
    ex, bus, _ = make_exec(client)
    await ex.submit(Signal("BUY", "BTCUSDT", size=1, order_type="LIMIT", price=95))
    assert ("limit", "BTCUSDT", "BUY", 1, 95) in client.calls
    assert ex.engine.position is None  # limit resting on the exchange, no position opened yet


async def test_limit_auto_cancel_after_timeout():
    client = FakeClient()
    ex, bus, _ = make_exec(client, timeout=0.05)
    await ex.submit(Signal("BUY", "BTCUSDT", size=1, order_type="LIMIT", price=95))
    await asyncio.sleep(0.12)  # past the timeout
    assert any(c[0] == "cancel" for c in client.calls)


async def test_manual_cancel_calls_exchange():
    client = FakeClient()
    ex, _, _ = make_exec(client)
    await ex.cancel("ext123")
    assert ("cancel", "BTCUSDT", "ext123") in client.calls


# ---- P9b: Futures client (SL/TP on the exchange, reduceOnly, position reconciliation) ----
class FakeFutures(FakeClient):
    def __init__(self, price=100.0):
        super().__init__(price)
        self.amt = 0.0  # position on the "exchange"
        self.fail_protect = False
        self.close_fill = None

    async def market_order(self, symbol, side, qty, reduce_only=False):
        self.calls.append(("market", symbol, side, qty, reduce_only))
        self.amt += qty if side == "BUY" else -qty
        return {"orderId": self._id(), "price": self.price, "status": "FILLED", "qty": qty}

    async def ensure_leverage(self, symbol, lev):
        self.calls.append(("lev", symbol, lev))

    async def protect(self, symbol, side, sl, tp):
        self.calls.append(("protect", side, sl, tp))
        if self.fail_protect:
            raise RuntimeError("algo order rejected")
        return {"sl": "a1" if sl else None, "tp": "a2" if tp else None}

    async def cancel_protection(self, symbol, ids):
        self.calls.append(("unprotect", dict(ids or {})))

    async def position(self, symbol):
        return {"amt": self.amt, "entry": 100.0}

    async def last_close_fill(self, symbol, since):
        return self.close_fill


def fx(price=100.0):
    c = FakeFutures(price)
    ex, bus, store = make_exec(c)
    ex.reconcile_every = 0  # reconcile on every tick in tests
    return c, ex, bus


async def test_futures_open_sets_leverage_and_exchange_sltp():
    c, ex, _ = fx()
    ex.engine.leverage = 5
    await ex.submit(Signal("BUY", "BTCUSDT", size=1, sl=95, tp=110))
    assert ("lev", "BTCUSDT", 5) in c.calls
    assert ("protect", "LONG", 95, 110) in c.calls
    assert ex._protect == {"sl": "a1", "tp": "a2"}


async def test_futures_no_client_close_when_exchange_protects():
    c, ex, _ = fx()
    await ex.submit(Signal("BUY", "BTCUSDT", size=1, sl=95, tp=110))
    n = len(c.calls)
    await ex.on_price(94)  # exchange holds a STOP_MARKET → app does NOT close too (no double close)
    assert not any(x[0] == "market" for x in c.calls[n:])


async def test_futures_reconcile_detects_exchange_sl_fill():
    c, ex, bus = fx()
    await ex.submit(Signal("BUY", "BTCUSDT", size=1, sl=95, tp=110))
    c.amt = 0.0  # SL filled on the exchange
    c.close_fill = {"orderId": "x9", "price": 94.9, "qty": 1, "fee": 0.05,
                    "realized": -5.1, "ts": 1}
    await ex.on_price(94.8)
    assert ex.engine.position is None
    closed = [m for _, m in bus.msgs if m.get("status") == "CLOSED"][-1]
    assert closed["reason"] == "SL" and closed["price"] == 94.9
    assert closed["pnl"] == pytest.approx(-5.1 - 0.05)  # real exchange figures
    assert ("unprotect", {"sl": "a1", "tp": "a2"}) in c.calls  # cancel the remaining TP leg


async def test_futures_flip_closes_reduce_only_then_opens():
    c, ex, _ = fx()
    await ex.submit(Signal("BUY", "BTCUSDT", size=1, sl=95))
    await ex.submit(Signal("SELL", "BTCUSDT", size=2, sl=105))
    markets = [x for x in c.calls if x[0] == "market"]
    assert markets[1] == ("market", "BTCUSDT", "SELL", 1, True)  # close LONG, reduceOnly
    assert markets[2] == ("market", "BTCUSDT", "SELL", 2, False)  # open SHORT
    assert ex.engine.position.side == "SHORT" and c.amt == -2


async def test_futures_modify_sltp_replaces_exchange_orders():
    c, ex, _ = fx()
    await ex.submit(Signal("BUY", "BTCUSDT", size=1, sl=95, tp=110))
    await ex.modify_sltp(98, 112)
    assert ("unprotect", {"sl": "a1", "tp": "a2"}) in c.calls
    assert ("protect", "LONG", 98, 112) in c.calls


async def test_futures_protect_failure_falls_back_to_client_side():
    c, ex, bus = fx()
    c.fail_protect = True
    await ex.submit(Signal("BUY", "BTCUSDT", size=1, sl=95))
    assert any(t == "risk" for t, _ in bus.msgs)  # user is warned
    await ex.on_price(94)  # no SL on the exchange → app closes it itself
    assert ("market", "BTCUSDT", "SELL", 1, True) in c.calls
    assert ex.engine.position is None
