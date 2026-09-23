"""StrategyRunner + BotManager: bot nhận nến đúng tf, chống trùng nến, đăng ký stream với feed."""

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
    await bus.publish(topic, _k(900_000))       # trùng nến cuối → thay, không nhân đôi
    await bus.publish(topic, _k(0))             # nến cũ → bỏ
    await bus.publish(topic, _k(1_800_000, closed=False))  # chưa đóng → không gọi strategy
    await bus.publish(topic, _k(1_800_000))
    await bus.publish("kline.BTCUSDT.1m", _k(1_860_000, tf="1m"))  # tf khác → không nghe
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
