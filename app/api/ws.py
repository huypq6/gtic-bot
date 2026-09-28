"""WSGateway — pushes realtime data (kline/ticker/feed/...) from the EventBus to the frontend.

Each client subscribes to the `"*"` firehose (single-user, few symbols → simple; the frontend
filters by the symbol being viewed). On connect, a `feed` message with the current status
is sent immediately so the UI does not have to wait for the next tick.
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
        """Background task: remember the latest feed status to send to newly connected clients."""
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
        except Exception:  # noqa: BLE001 — client closed/dropped (disconnect, going away)
            logger.debug("WS client disconnected")
        finally:
            self._bus.unsubscribe("*", sub)
