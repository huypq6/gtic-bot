"""Client sàn dùng chung theo mode (1 cặp key/mode trong .env) — executor + đồng bộ số dư.

Rào chắn LIVE nằm ở đây (1 chỗ): không ENABLE_LIVE → không bao giờ tạo client live.
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
    raise ValueError(f"mode {mode} không dùng sàn")


def check_mode(mode: str, s: Settings = settings) -> None:
    """Raise ValueError (thông báo cho người dùng) nếu mode chưa dùng được."""
    if mode == "LIVE" and not s.enable_live:
        raise ValueError("mode LIVE bị khóa — cần ENABLE_LIVE=1 trong .env")
    k, sec = keys_for(mode, s)
    if not k or not sec:
        env = "BINANCE_TESTNET_KEY/SECRET" if mode == "TESTNET" else "BINANCE_KEY/SECRET"
        raise ValueError(f"cần {env} trong .env để dùng mode {mode}")


async def exchange_client(mode: str, s: Settings = settings):
    """Client Binance USDⓈ-M Futures cho mode (tạo 1 lần, dùng lại)."""
    check_mode(mode, s)
    async with _lock:
        if mode not in _clients:
            from app.execution.binance_futures import BinanceFuturesClient

            k, sec = keys_for(mode, s)
            _clients[mode] = await BinanceFuturesClient.create(k, sec, testnet=mode == "TESTNET")
            if mode == "LIVE":
                logger.warning("⚠️  ĐÃ TẠO CLIENT BINANCE LIVE (TIỀN THẬT)")
        return _clients[mode]


def set_client(mode: str, client) -> None:
    """Test: gắn client giả."""
    _clients[mode] = client


async def close_all() -> None:
    for c in list(_clients.values()):
        try:
            await c.close()
        except Exception:  # noqa: BLE001
            logger.exception("đóng client sàn lỗi")
    _clients.clear()
