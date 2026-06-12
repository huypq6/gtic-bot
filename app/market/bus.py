"""EventBus — pub/sub in-memory trên asyncio.Queue (single process).

Topic dạng chuỗi: `kline.{symbol}.{tf}`, `ticker.{symbol}`, `signal`,
`order.update`, `scan`, `feed`. Subscriber đăng ký 1 topic → nhận Queue riêng.
Topic đặc biệt `"*"` = firehose, nhận MỌI message (dùng cho WSGateway forward).

Đủ cho single-user; chừa cửa thay bằng Redis pub/sub nếu cần scale.
Backpressure: queue đầy → DROP message mới (không block publisher) để feed
realtime không bị một subscriber chậm làm nghẽn.
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
        """Đăng ký 1 topic, trả về Queue nhận message của topic đó."""
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
        """Gửi message tới subscriber của `topic` và của firehose `"*"`."""
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
