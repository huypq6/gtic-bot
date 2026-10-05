"""Application settings — read from .env via pydantic-settings.

NEVER hardcode secrets. Every key/environment variable is declared here and read from .env.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---
    database_url: str = "postgresql+asyncpg://botuser:botpass@localhost:5432/tradingbot"

    # --- Binance Testnet ---
    binance_testnet_key: str = ""
    binance_testnet_secret: str = ""
    # Which sandbox the TESTNET keys belong to. Binance moved the futures testnet to Demo Trading
    # (testnet.binancefuture.com → demo.binance.com): "demo" = demo-fapi.binance.com (default),
    # "testnet" = legacy testnet.binancefuture.com. Both serve the same market today.
    binance_testnet_endpoint: str = "demo"

    # --- Binance Live (only used when ENABLE_LIVE=1) ---
    binance_key: str = ""
    binance_secret: str = ""

    # --- Live safety: must be True to allow LIVE mode ---
    enable_live: bool = False

    # --- App ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    # CORS: origins allowed to call the API (single-user self-hosted → all origins by default).
    # Set CORS_ORIGINS="http://tsp32:8000,http://192.168.1.x" to restrict.
    cors_origins: list[str] = ["*"]

    # --- Market feed (P1+): default watched symbols/timeframes ---
    default_symbols: list[str] = ["BTCUSDT", "ETHUSDT"]
    default_tf: str = "1m"
    # Disable to avoid connecting to Binance WS during tests/CI.
    feed_autostart: bool = True

    # --- Scanner (P7) ---
    scan_symbols: list[str] = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
    scan_tf: str = "15m"
    scan_interval_sec: int = 60
    # ATR-based suggested SL/TP: SL = entry ∓ sl×ATR, TP = entry ± tp×ATR.
    scan_sl_atr: float = 1.5
    scan_tp_atr: float = 2.0

    # --- Binance fees (taker, VIP 0) — used for backtests ---
    binance_spot_fee: float = 0.001  # Spot 0.10%
    binance_futures_fee: float = 0.0005  # Futures (USDⓈ-M) 0.05%
    futures_max_leverage: int = 50


@lru_cache
def get_settings() -> Settings:
    """Singleton settings (cache)."""
    return Settings()


settings = get_settings()
