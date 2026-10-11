"""StrategyRunner + BotManager: bot receives candles of the right tf, dedupes candles,
registers streams with the feed."""

import asyncio

from app.market.bus import EventBus
from app.market.feed import MarketFeed
from app.strategy.base import Strategy
from app.strategy.runner import BotManager, StrategyRunner


class _Count(Strategy):
    name = "count"
    version = "1"
    default_params = {}

    def __init__(self, params=None):
        super().__init__(params)
        self.seen = []

    def on_candle(self, ctx):
        self.seen.append([c["ts"] for c in ctx.candles])
        return []


class _Exec:
    async def on_price(self, price):
        pass

    def current_position(self):
        return None


def _k(ts, closed=True, tf="15m"):
    return {"type": "kline", "symbol": "BTCUSDT", "tf": tf, "ts": ts, "open": 1.0,
            "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0, "closed": closed}


async def _drain(bus):
    for _ in range(20):
        await asyncio.sleep(0)


async def test_runner_dedupes_and_skips_stale_candles():
    bus = EventBus()
    strat = _Count()
    r = StrategyRunner(1, strat, _Exec(), bus, "BTCUSDT", "15m", session_factory=None)
    r._candles.extend([_k(0), _k(900_000)])
    task = asyncio.create_task(r.run())
    await _drain(bus)
    topic = "kline.BTCUSDT.15m"
    await bus.publish(topic, _k(900_000))       # same as last candle → replace, no dup
    await bus.publish(topic, _k(0))             # stale candle → skip
    await bus.publish(topic, _k(1_800_000, closed=False))  # not closed yet → strategy not called
    await bus.publish(topic, _k(1_800_000))
    await bus.publish("kline.BTCUSDT.1m", _k(1_860_000, tf="1m"))  # different tf → not listened to
    await _drain(bus)
    task.cancel()
    assert strat.seen == [[0, 900_000], [0, 900_000, 1_800_000]]
    assert r.last_candle_ts == 1_800_000


async def test_bot_manager_registers_bot_stream_with_feed(monkeypatch):
    bus = EventBus()
    feed = MarketFeed(bus, symbols=["BTCUSDT"], tf="1m")
    mgr = BotManager(bus, session_factory=None, feed=feed)

    async def _noop_start(self):
        pass

    monkeypatch.setattr(StrategyRunner, "start", _noop_start)
    monkeypatch.setattr("app.strategy.runner.get", lambda n, v: _Count)

    async def _mk(*a, **kw):
        return _Exec()

    monkeypatch.setattr(mgr, "_make_executor", _mk)
    await mgr.start_bot(7, "count", "1", {}, "DOGEUSDT", "15m", "PAPER")
    assert "dogeusdt@kline_15m" in feed.stream_url()
    assert mgr.last_candle_ts(7) is None


async def test_runner_survives_a_rejected_order():
    """An exchange rejection must not end the runner (it used to stop silently while the UI
    still said RUNNING): the error is alerted and the next candle is processed."""
    from app.strategy.base import Signal

    class _Buy(_Count):
        def on_candle(self, ctx):
            super().on_candle(ctx)
            return [Signal("BUY", "BTCUSDT", size=1)]

    class _Rejecting(_Exec):
        def __init__(self):
            self.tries = 0

        async def submit(self, sig):
            self.tries += 1
            raise RuntimeError("order notional 0.01 < minimum 5 USDT")

    bus = EventBus()
    risk = bus.subscribe("risk")
    strat, ex = _Buy(), _Rejecting()
    r = StrategyRunner(1, strat, ex, bus, "BTCUSDT", "15m", session_factory=None)
    task = asyncio.create_task(r.run())
    await _drain(bus)
    await bus.publish("kline.BTCUSDT.15m", _k(0))
    await bus.publish("kline.BTCUSDT.15m", _k(900_000))
    await _drain(bus)
    task.cancel()
    assert ex.tries == 2 and len(strat.seen) == 2  # still alive after the first failure
    alert = risk.get_nowait()
    assert "order failed" in alert["reason"] and "minimum" in alert["reason"]
