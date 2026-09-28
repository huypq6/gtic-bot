"""MarketFeed — Binance WS combined stream → EventBus.

Opens 1 combined WebSocket for all configured (symbol, tf): kline + ticker.
Parse → publish to the bus (`kline.{symbol}.{tf}`, `ticker.{symbol}`).
Connection lost → auto-reconnect with backoff, emits `feed` status (OK/RECONNECTING/DOWN).

`connect` is injected for testing (defaults to websockets.connect). The feed depends ONLY on
the bus + websockets, never the DB (persistence lives in market/store.py).
"""

import asyncio
import json
import logging
from collections.abc import Callable

import websockets

logger = logging.getLogger(__name__)

BINANCE_WS_BASE = "wss://stream.binance.com:9443/stream?streams="


def parse_combined(msg: dict) -> tuple[str, dict] | None:
    """Parse 1 combined-stream message → (topic, payload), or None if ignored."""
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
        self._symbols = [s.upper() for s in symbols]
        self._tf = tf
        self._connect = connect
        self._base_url = base_url
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._running = False
        self._ws = None  # currently open WS (for runtime SUBSCRIBE/UNSUBSCRIBE)
        self._msg_id = 0
        # Kline streams bots need (symbol, tf) — independent of the chart's watchlist/default tf.
        # Without this, a 15m bot only hears candles when the default tf = 15m → silent forever.
        self._bot_klines: set[tuple[str, str]] = set()

    def _streams_for(self, symbol: str) -> list[str]:
        s = symbol.lower()
        return [f"{s}@kline_{self._tf}", f"{s}@ticker"]

    def _all_streams(self) -> list[str]:
        streams: list[str] = []
        for sym in self._symbols:
            streams += self._streams_for(sym)
        for sym, tf in sorted(self._bot_klines):
            streams.append(f"{sym.lower()}@kline_{tf}")
        return list(dict.fromkeys(streams))  # dedupe, keep order

    def stream_url(self) -> str:
        return self._base_url + "/".join(self._all_streams())

    async def ensure_kline(self, symbol: str, tf: str) -> None:
        """Ensure the feed streams `kline.{symbol}.{tf}` for a bot (runtime SUBSCRIBE if live)."""
        key = (symbol.upper(), tf)
        if key in self._bot_klines:
            return
        already = key[0] in self._symbols and tf == self._tf
        self._bot_klines.add(key)
        if not already and self._ws:
            self._msg_id += 1
            await self._ws.send(json.dumps({
                "method": "SUBSCRIBE",
                "params": [f"{key[0].lower()}@kline_{tf}"],
                "id": self._msg_id,
            }))

    def stop(self) -> None:
        self._running = False

    async def _control(self, method: str, symbol: str) -> None:
        if not self._ws:
            return
        params = self._streams_for(symbol)
        if method == "UNSUBSCRIBE":  # keep streams a bot still needs
            bot = {f"{s.lower()}@kline_{tf}" for s, tf in self._bot_klines}
            params = [p for p in params if p not in bot]
        self._msg_id += 1
        await self._ws.send(json.dumps({"method": method, "params": params, "id": self._msg_id}))

    async def add_symbol(self, symbol: str) -> None:
        """Add a pair + realtime SUBSCRIBE (no reconnect needed)."""
        s = symbol.upper()
        if s in self._symbols:
            return
        self._symbols.append(s)
        await self._control("SUBSCRIBE", s)

    async def remove_symbol(self, symbol: str) -> None:
        s = symbol.upper()
        if s not in self._symbols:
            return
        self._symbols.remove(s)
        await self._control("UNSUBSCRIBE", s)

    async def handle_raw(self, raw: str | bytes) -> None:
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            logger.debug("feed: skipping non-JSON message")
            return
        parsed = parse_combined(msg)
        if parsed:
            topic, payload = parsed
            await self._bus.publish(topic, payload)

    async def run(self) -> None:
        """Feed lifecycle: connect → consume → reconnect on error (until stop())."""
        self._running = True
        backoff = self._backoff_base
        while self._running:
            try:
                url_streams = self._all_streams()
                async with self._connect(self._base_url + "/".join(url_streams)) as ws:
                    self._ws = ws
                    backoff = self._backoff_base
                    # Streams added during the handshake (URL built, _ws still None) → catch up.
                    missing = [x for x in self._all_streams() if x not in url_streams]
                    if missing:
                        self._msg_id += 1
                        await ws.send(json.dumps(
                            {"method": "SUBSCRIBE", "params": missing, "id": self._msg_id}
                        ))
                    await self._bus.publish("feed", {"status": "OK"})
                    async for raw in ws:
                        await self.handle_raw(raw)
                self._ws = None
                # iterator ended normally (e.g. tests) → exit if stopped
                if not self._running:
                    break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — every WS error triggers a reconnect
                self._ws = None
                if not self._running:
                    break
                logger.warning("feed disconnected: %s → reconnecting in %.1fs", exc, backoff)
                await self._bus.publish("feed", {"status": "RECONNECTING"})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._backoff_max)
        await self._bus.publish("feed", {"status": "DOWN"})
