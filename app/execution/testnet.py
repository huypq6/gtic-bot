"""Factory cho mode TESTNET — ExchangeExecutor + Binance testnet client.

Cần `BINANCE_TESTNET_KEY/SECRET`. Lệnh thật trên môi trường giả (không tiền thật).
"""

from app.config import Settings
from app.execution.binance_client import BinanceClient
from app.execution.exchange import ExchangeExecutor


async def make_testnet_executor(
    bot_id: int | None, symbol: str, bus, session_factory, settings: Settings,
    timeout: float | None = None,
) -> ExchangeExecutor:
    if not settings.binance_testnet_key or not settings.binance_testnet_secret:
        raise ValueError("cần BINANCE_TESTNET_KEY/SECRET trong .env để chạy mode TESTNET")
    client = await BinanceClient.create(
        settings.binance_testnet_key, settings.binance_testnet_secret, testnet=True
    )
    return ExchangeExecutor(
        bot_id, symbol, "TESTNET", bus, session_factory, client, timeout=timeout
    )
