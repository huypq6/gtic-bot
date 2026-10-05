"""Shared exchange clients per mode (one key pair per mode in .env) — executor + balance sync.

The LIVE guard lives here (one place): without ENABLE_LIVE a live client is never created.
"""

import asyncio
import logging

from app.config import Settings, settings

logger = logging.getLogger(__name__)

_clients: dict[str, object] = {}
_lock = asyncio.Lock()


def keys_for(mode: str, s: Settings = settings) -> tuple[str, str]:
    if mode == "TESTNET":
        return s.binance_testnet_key, s.binance_testnet_secret
    if mode == "LIVE":
        return s.binance_key, s.binance_secret
    raise ValueError(f"mode {mode} does not use the exchange")


def check_mode(mode: str, s: Settings = settings) -> None:
    """Raise ValueError (a user-facing message) if the mode cannot be used yet."""
    if mode == "LIVE" and not s.enable_live:
        raise ValueError("LIVE mode is locked — requires ENABLE_LIVE=1 in .env")
    k, sec = keys_for(mode, s)
    if not k or not sec:
        env = "BINANCE_TESTNET_KEY/SECRET" if mode == "TESTNET" else "BINANCE_KEY/SECRET"
        raise ValueError(f"{env} is required in .env to use {mode} mode")


async def exchange_client(mode: str, s: Settings = settings):
    """Binance USDⓈ-M Futures client for the mode (created once, reused)."""
    check_mode(mode, s)
    async with _lock:
        if mode not in _clients:
            from app.execution.binance_futures import BinanceFuturesClient

            k, sec = keys_for(mode, s)
            _clients[mode] = await BinanceFuturesClient.create(
                k, sec, testnet=mode == "TESTNET", endpoint=s.binance_testnet_endpoint
            )
            if mode == "LIVE":
                logger.warning("⚠️  BINANCE LIVE CLIENT CREATED (REAL MONEY)")
            else:
                await _testnet_one_way(_clients[mode])
        return _clients[mode]


async def _testnet_one_way(client) -> None:
    """Orders are sent without positionSide → Hedge mode would reject them (-4061). TESTNET only:
    switch to One-way on first connect. LIVE account settings are never changed by the app."""
    try:
        if await client.hedge_mode():
            await client.set_one_way()
            logger.info("TESTNET position mode: Hedge → One-way")
    except Exception as e:  # noqa: BLE001 — e.g. open positions; Check connection reports it
        logger.warning("TESTNET position mode check failed: %s", e)


def set_client(mode: str, client) -> None:
    """Test: attach a fake client."""
    _clients[mode] = client


async def close_all() -> None:
    for c in list(_clients.values()):
        try:
            await c.close()
        except Exception:  # noqa: BLE001
            logger.exception("failed to close exchange client")
    _clients.clear()
