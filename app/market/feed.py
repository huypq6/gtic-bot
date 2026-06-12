"""MarketFeed — Binance WS combined stream → EventBus.

Kết nối 1 WebSocket combined cho mọi (symbol, tf) cấu hình: kline + ticker.
Parse → publish lên bus (`kline.{symbol}.{tf}`, `ticker.{symbol}`).
Mất kết nối → auto-reconnect backoff, phát `feed` status (OK/RECONNECTING/DOWN).

`connect` được inject để test (mặc định websockets.connect). Feed CHỈ phụ thuộc
bus + websockets, không đụng DB (persistence tách ở market/store.py).
"""

import asyncio
import json
import logging
from collections.abc import Callable

import websockets

logger = logging.getLogger(__name__)

BINANCE_WS_BASE = "wss://stream.binance.com:9443/stream?streams="


def parse_combined(msg: dict) -> tuple[str, dict] | None:
    """Parse 1 message combined-stream → (topic, payload) hoặc None nếu bỏ qua."""
    stream = msg.get("stream")
    data = msg.get("data")
    if not stream or not isinstance(data, dict):
        return None

    if "@kline_" in stream:
        k = data.get("k", {})
        symbol = data["s"]
        tf = k["i"]
        payload = {
            "type": "kline",
            "symbol": symbol,
            "tf": tf,
            "ts": k["t"],
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "closed": bool(k["x"]),
        }
        return f"kline.{symbol}.{tf}", payload

    if stream.endswith("@ticker"):
        symbol = data["s"]
        payload = {
            "type": "ticker",
            "symbol": symbol,
            "price": float(data["c"]),
            "pct": float(data["P"]),
        }
        return f"ticker.{symbol}", payload

    return None


class MarketFeed:
    def __init__(
        self,
        bus,
        symbols: list[str],
        tf: str,
        connect: Callable = websockets.connect,
        base_url: str = BINANCE_WS_BASE,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
    ) -> None:
        self._bus = bus
        self._symbols = symbols
        self._tf = tf
        self._connect = connect
        self._base_url = base_url
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._running = False

    def stream_url(self) -> str:
        streams = []
        for sym in self._symbols:
            s = sym.lower()
            streams.append(f"{s}@kline_{self._tf}")
            streams.append(f"{s}@ticker")
        return self._base_url + "/".join(streams)

    def stop(self) -> None:
        self._running = False

    async def handle_raw(self, raw: str | bytes) -> None:
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            logger.debug("feed: bỏ qua message không phải JSON")
            return
        parsed = parse_combined(msg)
        if parsed:
            topic, payload = parsed
            await self._bus.publish(topic, payload)

    async def run(self) -> None:
        """Vòng đời feed: connect → consume → reconnect khi lỗi (đến khi stop())."""
        self._running = True
        backoff = self._backoff_base
        while self._running:
            try:
                async with self._connect(self.stream_url()) as ws:
                    backoff = self._backoff_base
                    await self._bus.publish("feed", {"status": "OK"})
                    async for raw in ws:
                        await self.handle_raw(raw)
                # iterator kết thúc bình thường (vd test) → thoát nếu đã stop
                if not self._running:
                    break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — mọi lỗi WS đều reconnect
                if not self._running:
                    break
                logger.warning("feed mất kết nối: %s → reconnect sau %.1fs", exc, backoff)
                await self._bus.publish("feed", {"status": "RECONNECTING"})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._backoff_max)
        await self._bus.publish("feed", {"status": "DOWN"})
