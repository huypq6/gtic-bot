"""EventBus — pub/sub in-memory trên asyncio.Queue."""

import asyncio

import pytest

from app.market.bus import EventBus


async def test_subscribe_receives_published_message():
    bus = EventBus()
    sub = bus.subscribe("kline.BTCUSDT.1m")
    await bus.publish("kline.BTCUSDT.1m", {"close": 100})
    msg = await asyncio.wait_for(sub.get(), timeout=1)
    assert msg == {"close": 100}


async def test_only_matching_topic_receives():
    bus = EventBus()
    btc = bus.subscribe("ticker.BTCUSDT")
    eth = bus.subscribe("ticker.ETHUSDT")
    await bus.publish("ticker.BTCUSDT", {"price": 1})
    assert (await asyncio.wait_for(btc.get(), timeout=1)) == {"price": 1}
    assert eth.empty()


async def test_wildcard_firehose_receives_all():
    bus = EventBus()
    fire = bus.subscribe("*")
    await bus.publish("ticker.BTCUSDT", {"price": 1})
    await bus.publish("feed", {"status": "OK"})
    got = [await asyncio.wait_for(fire.get(), timeout=1) for _ in range(2)]
    assert {"price": 1} in got and {"status": "OK"} in got


async def test_multiple_subscribers_same_topic():
    bus = EventBus()
    a = bus.subscribe("feed")
    b = bus.subscribe("feed")
    await bus.publish("feed", {"status": "DOWN"})
    assert (await asyncio.wait_for(a.get(), timeout=1)) == {"status": "DOWN"}
    assert (await asyncio.wait_for(b.get(), timeout=1)) == {"status": "DOWN"}


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    sub = bus.subscribe("feed")
    bus.unsubscribe("feed", sub)
    await bus.publish("feed", {"status": "OK"})
    assert sub.empty()


async def test_publish_no_subscribers_is_noop():
    bus = EventBus()
    await bus.publish("nobody", {"x": 1})  # không raise


async def test_full_queue_drops_without_blocking():
    bus = EventBus()
    sub = bus.subscribe("feed", maxsize=1)
    await bus.publish("feed", {"n": 1})
    await bus.publish("feed", {"n": 2})  # queue đầy → drop, không treo
    assert (await asyncio.wait_for(sub.get(), timeout=1)) == {"n": 1}
    assert sub.empty()


@pytest.mark.parametrize("n", [5])
async def test_pubsub_throughput(n):
    bus = EventBus()
    sub = bus.subscribe("kline.X.1m")
    for i in range(n):
        await bus.publish("kline.X.1m", {"i": i})
    got = [await asyncio.wait_for(sub.get(), timeout=1) for _ in range(n)]
    assert [m["i"] for m in got] == list(range(n))
