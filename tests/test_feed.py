"""MarketFeed — parse message Binance combined stream + build stream URL + reconnect."""

import asyncio

import pytest

from app.market.bus import EventBus
from app.market.feed import MarketFeed, parse_combined

KLINE_MSG = {
    "stream": "btcusdt@kline_1m",
    "data": {
        "e": "kline",
        "s": "BTCUSDT",
        "k": {
            "t": 1718000000000,
            "i": "1m",
            "o": "100.5",
            "h": "101.0",
            "l": "100.0",
            "c": "100.8",
            "v": "12.5",
            "x": True,
        },
    },
}

TICKER_MSG = {
    "stream": "btcusdt@ticker",
    "data": {"e": "24hrTicker", "s": "BTCUSDT", "c": "100.8", "P": "1.23"},
}


def test_parse_kline():
    topic, payload = parse_combined(KLINE_MSG)
    assert topic == "kline.BTCUSDT.1m"
    assert payload["type"] == "kline"
    assert payload["symbol"] == "BTCUSDT"
    assert payload["tf"] == "1m"
    assert payload["open"] == 100.5
    assert payload["high"] == 101.0
    assert payload["low"] == 100.0
    assert payload["close"] == 100.8
    assert payload["volume"] == 12.5
    assert payload["closed"] is True
    assert payload["ts"] == 1718000000000


def test_parse_ticker():
    topic, payload = parse_combined(TICKER_MSG)
    assert topic == "ticker.BTCUSDT"
    assert payload == {"type": "ticker", "symbol": "BTCUSDT", "price": 100.8, "pct": 1.23}


def test_parse_unknown_returns_none():
    assert parse_combined({"stream": "btcusdt@depth", "data": {}}) is None
    assert parse_combined({"no_stream": 1}) is None


def test_stream_url_lowercases_and_combines():
    feed = MarketFeed(EventBus(), symbols=["BTCUSDT", "ETHUSDT"], tf="1m")
    url = feed.stream_url()
    assert "btcusdt@kline_1m" in url
    assert "btcusdt@ticker" in url
    assert "ethusdt@kline_1m" in url
    assert url.startswith("wss://")


async def test_handle_raw_publishes_to_bus():
    bus = EventBus()
    feed = MarketFeed(bus, symbols=["BTCUSDT"], tf="1m")
    sub = bus.subscribe("kline.BTCUSDT.1m")
    import json

    await feed.handle_raw(json.dumps(KLINE_MSG))
    msg = await asyncio.wait_for(sub.get(), timeout=1)
    assert msg["close"] == 100.8


async def test_run_reconnects_and_emits_feed_status():
    """Mô phỏng WS rớt 1 lần → feed phát RECONNECTING rồi OK lại."""
    bus = EventBus()
    feed_events = bus.subscribe("feed")
    attempts = {"n": 0}

    class FakeWS:
        def __init__(self, fail: bool):
            self._fail = fail

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            attempts["n"] += 1
            if self._fail:
                raise ConnectionError("dropped")
            # lần 2: gửi 1 message rồi dừng feed
            feed.stop()
            raise StopAsyncIteration

    def fake_connect(url, **kw):
        return FakeWS(fail=attempts["n"] == 0)

    feed = MarketFeed(bus, symbols=["BTCUSDT"], tf="1m", connect=fake_connect, backoff_base=0.01)
    await asyncio.wait_for(feed.run(), timeout=2)

    statuses = []
    while not feed_events.empty():
        statuses.append((await feed_events.get())["status"])
    assert "OK" in statuses
    assert "RECONNECTING" in statuses


@pytest.mark.parametrize("tf", ["1m", "5m", "1h"])
def test_stream_url_respects_tf(tf):
    feed = MarketFeed(EventBus(), symbols=["BTCUSDT"], tf=tf)
    assert f"btcusdt@kline_{tf}" in feed.stream_url()
