"""EventBus — in-memory pub/sub on asyncio.Queue (single process).

String topics: `kline.{symbol}.{tf}`, `ticker.{symbol}`, `signal`,
`order.update`, `scan`, `feed`. A subscriber registers for 1 topic → gets its own Queue.
The special topic `"*"` = firehose, receives EVERY message (used by the WSGateway to forward).

Good enough for single-user; leaves room to swap in Redis pub/sub if scaling is needed.
Backpressure: queue full → DROP the new message (never block the publisher) so the realtime
feed is not stalled by one slow subscriber.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

WILDCARD = "*"


class EventBus:
    def __init__(self, default_maxsize: int = 1000) -> None:
        self._default_maxsize = default_maxsize
        self._subs: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, topic: str, maxsize: int | None = None) -> asyncio.Queue:
        """Subscribe to 1 topic; returns a Queue receiving that topic's messages."""
        q: asyncio.Queue = asyncio.Queue(
            maxsize=self._default_maxsize if maxsize is None else maxsize
        )
        self._subs.setdefault(topic, set()).add(q)
        return q

    def unsubscribe(self, topic: str, queue: asyncio.Queue) -> None:
        subs = self._subs.get(topic)
        if subs:
            subs.discard(queue)
            if not subs:
                del self._subs[topic]

    async def publish(self, topic: str, message: Any) -> None:
        """Send a message to subscribers of `topic` and of the `"*"` firehose."""
        for t in (topic, WILDCARD):
            for q in self._subs.get(t, ()):
                _offer(q, message, topic)

    def topics(self) -> list[str]:
        return list(self._subs)


def _offer(q: asyncio.Queue, message: Any, topic: str) -> None:
    try:
        q.put_nowait(message)
    except asyncio.QueueFull:
        logger.warning("EventBus drop message on full queue (topic=%s)", topic)
