"""WSGateway — đẩy realtime (kline/ticker/feed/...) từ EventBus xuống frontend.

Mỗi client subscribe firehose `"*"` (single-user, ít symbol → đơn giản, frontend
tự lọc theo symbol đang xem). Khi connect gửi ngay 1 message `feed` trạng thái
hiện tại để UI không phải chờ tick kế tiếp.
"""

import asyncio
import logging

from fastapi import WebSocket

from app.market.bus import EventBus

logger = logging.getLogger(__name__)


class WSGateway:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._last_feed_status: str = "DOWN"
        self._status_sub = bus.subscribe("feed")

    async def track_feed_status(self) -> None:
        """Task nền: nhớ trạng thái feed mới nhất để gửi cho client vừa kết nối."""
        while True:
            msg = await self._status_sub.get()
            self._last_feed_status = msg.get("status", self._last_feed_status)

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        sub = self._bus.subscribe("*")
        try:
            await websocket.send_json({"type": "feed", "status": self._last_feed_status})
            while True:
                msg = await sub.get()
                await websocket.send_json(msg)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — client đóng/ngắt (disconnect, going away)
            logger.debug("WS client ngắt kết nối")
        finally:
            self._bus.unsubscribe("*", sub)
