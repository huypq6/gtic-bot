"""Factory cho mode LIVE — TIỀN THẬT (Binance USDⓈ-M Futures). RÀO CHẮN nhiều lớp.

CHỈ khởi tạo khi `ENABLE_LIVE=1` + có `BINANCE_KEY/SECRET` (kiểm ở clients.check_mode).
Việc xác nhận gõ "LIVE" do API/UI lo (modal). Key live nên tắt quyền rút tiền +
whitelist IP VPS (cấu hình ở sàn, ngoài app).
"""

import logging

from app.config import Settings
from app.execution.clients import exchange_client
from app.execution.exchange import ExchangeExecutor

logger = logging.getLogger(__name__)


async def make_live_executor(
    bot_id: int | None, symbol: str, bus, session_factory, settings: Settings,
    timeout: float | None = None,
) -> ExchangeExecutor:
    client = await exchange_client("LIVE", settings)
    logger.warning("⚠️  KHỞI TẠO LIVE EXECUTOR (TIỀN THẬT) bot=%s %s", bot_id, symbol)
    return ExchangeExecutor(bot_id, symbol, "LIVE", bus, session_factory, client, timeout=timeout)
