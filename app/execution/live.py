"""Factory for LIVE mode — REAL MONEY (Binance USDⓈ-M Futures). Multi-layer GUARDS.

ONLY initialized when `ENABLE_LIVE=1` + `BINANCE_KEY/SECRET` are set (checked in
clients.check_mode).
Typing "LIVE" to confirm is handled by the API/UI (modal). Live keys should have withdrawals
disabled + a VPS IP whitelist (configured on the exchange, outside the app).
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
    logger.warning("⚠️  INITIALIZING LIVE EXECUTOR (REAL MONEY) bot=%s %s", bot_id, symbol)
    return ExchangeExecutor(bot_id, symbol, "LIVE", bus, session_factory, client, timeout=timeout)
