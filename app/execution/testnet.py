"""Factory for TESTNET mode — ExchangeExecutor + Binance USDⓈ-M Futures testnet.

Requires `BINANCE_TESTNET_KEY/SECRET` (created at testnet.binancefuture.com). Real orders on a
simulated environment (no real money).
"""

from app.config import Settings
from app.execution.clients import exchange_client
from app.execution.exchange import ExchangeExecutor


async def make_testnet_executor(
    bot_id: int | None, symbol: str, bus, session_factory, settings: Settings,
    timeout: float | None = None,
) -> ExchangeExecutor:
    client = await exchange_client("TESTNET", settings)
    return ExchangeExecutor(
        bot_id, symbol, "TESTNET", bus, session_factory, client, timeout=timeout
    )
