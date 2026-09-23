"""MarketFeed — parse message Binance combined stream + build stream URL + reconnect."""

import asyncio
import json

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


class _CtrlWS:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(json.loads(data))


async def test_add_symbol_subscribes_runtime():
    feed = MarketFeed(EventBus(), symbols=["BTCUSDT"], tf="1m")
    ws = _CtrlWS()
    feed._ws = ws  # giả lập đang kết nối
    await feed.add_symbol("ethusdt")
    assert "ETHUSDT" in feed._symbols
    assert "ethusdt@kline_1m" in feed.stream_url()
    assert ws.sent[0]["method"] == "SUBSCRIBE"
    assert "ethusdt@ticker" in ws.sent[0]["params"]


async def test_remove_symbol_unsubscribes_runtime():
    feed = MarketFeed(EventBus(), symbols=["BTCUSDT", "ETHUSDT"], tf="1m")
    ws = _CtrlWS()
    feed._ws = ws
    await feed.remove_symbol("ETHUSDT")
    assert "ETHUSDT" not in feed._symbols
    assert ws.sent[0]["method"] == "UNSUBSCRIBE"


async def test_add_duplicate_noop():
    feed = MarketFeed(EventBus(), symbols=["BTCUSDT"], tf="1m")
    feed._ws = _CtrlWS()
    await feed.add_symbol("BTCUSDT")  # đã có
    assert feed._symbols == ["BTCUSDT"]
    assert feed._ws.sent == []


# --- stream kline theo bot (symbol, tf) — bug: bot 15m không nhận nến khi feed tf=1m ---


async def test_ensure_kline_adds_bot_tf_to_url():
    feed = MarketFeed(EventBus(), symbols=["BTCUSDT"], tf="1m")
    await feed.ensure_kline("dogeusdt", "15m")  # chưa nối WS → chỉ vào URL
    url = feed.stream_url()
    assert "dogeusdt@kline_15m" in url
    assert "btcusdt@kline_1m" in url


async def test_ensure_kline_subscribes_runtime_once():
    feed = MarketFeed(EventBus(), symbols=["BTCUSDT"], tf="1m")
    feed._ws = _CtrlWS()
    await feed.ensure_kline("BTCUSDT", "15m")
    await feed.ensure_kline("BTCUSDT", "15m")
    assert len(feed._ws.sent) == 1
    assert feed._ws.sent[0] == {"method": "SUBSCRIBE", "params": ["btcusdt@kline_15m"], "id": 1}


async def test_ensure_kline_default_tf_no_duplicate_stream():
    feed = MarketFeed(EventBus(), symbols=["BTCUSDT"], tf="1m")
    feed._ws = _CtrlWS()
    await feed.ensure_kline("BTCUSDT", "1m")  # đã có trong stream mặc định
    assert feed._ws.sent == []
    assert feed.stream_url().count("btcusdt@kline_1m") == 1


async def test_remove_symbol_keeps_bot_stream():
    feed = MarketFeed(EventBus(), symbols=["BTCUSDT", "ETHUSDT"], tf="15m")
    feed._ws = _CtrlWS()
    await feed.ensure_kline("ETHUSDT", "15m")
    await feed.remove_symbol("ETHUSDT")
    assert feed._ws.sent[-1]["params"] == ["ethusdt@ticker"]
    assert "ethusdt@kline_15m" in feed.stream_url()


async def test_run_subscribes_streams_added_during_handshake():
    """ensure_kline gọi khi đang connect (URL đã dựng, _ws None) → phải SUBSCRIBE bù."""
    bus = EventBus()
    sent = []

    class FakeWS:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def send(self, data):
            sent.append(json.loads(data))

        def __aiter__(self):
            return self

        async def __anext__(self):
            feed.stop()
            raise StopAsyncIteration

    def fake_connect(url, **kw):
        # mô phỏng bot đăng ký stream trong lúc bắt tay
        feed._bot_klines.add(("DOGEUSDT", "15m"))
        return FakeWS()

    feed = MarketFeed(bus, symbols=["BTCUSDT"], tf="1m", connect=fake_connect)
    await asyncio.wait_for(feed.run(), timeout=2)
    assert sent and sent[0]["params"] == ["dogeusdt@kline_15m"]
