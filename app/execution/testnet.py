"""Factory cho mode TESTNET — ExchangeExecutor + Binance USDⓈ-M Futures testnet.

Cần `BINANCE_TESTNET_KEY/SECRET` (tạo ở testnet.binancefuture.com). Lệnh thật trên
môi trường giả (không tiền thật).
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
