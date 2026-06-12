"""Factory cho mode LIVE — TIỀN THẬT. RÀO CHẮN nhiều lớp.

CHỈ khởi tạo khi `ENABLE_LIVE=1` + có `BINANCE_KEY/SECRET`. Việc xác nhận gõ "LIVE"
do API/UI lo (modal). Key live nên tắt quyền rút tiền + whitelist IP VPS (cấu hình
ở sàn, ngoài app).
"""

import logging

from app.config import Settings
from app.execution.binance_client import BinanceClient
from app.execution.exchange import ExchangeExecutor

logger = logging.getLogger(__name__)


async def make_live_executor(
    bot_id: int | None, symbol: str, bus, session_factory, settings: Settings,
    timeout: float | None = None,
) -> ExchangeExecutor:
    if not settings.enable_live:
        raise ValueError("mode LIVE bị khóa — cần ENABLE_LIVE=1 trong .env")
    if not settings.binance_key or not settings.binance_secret:
        raise ValueError("cần BINANCE_KEY/SECRET trong .env để chạy mode LIVE")
    client = await BinanceClient.create(
        settings.binance_key, settings.binance_secret, testnet=False
    )
    logger.warning("⚠️  KHỞI TẠO LIVE EXECUTOR (TIỀN THẬT) bot=%s %s", bot_id, symbol)
    return ExchangeExecutor(bot_id, symbol, "LIVE", bus, session_factory, client, timeout=timeout)
