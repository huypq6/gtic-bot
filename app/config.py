"""Cấu hình ứng dụng — đọc từ .env qua pydantic-settings.

KHÔNG hardcode secret. Mọi key/biến môi trường khai báo ở đây, đọc từ .env.
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

    # --- Binance Live (chỉ dùng khi ENABLE_LIVE=1) ---
    binance_key: str = ""
    binance_secret: str = ""

    # --- An toàn Live: phải =True mới cho phép mode LIVE ---
    enable_live: bool = False

    # --- App ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # --- Market feed (P1+): danh sách symbol/tf theo dõi mặc định ---
    default_symbols: list[str] = ["BTCUSDT", "ETHUSDT"]
    default_tf: str = "1m"
    # Tắt để không kết nối Binance WS khi chạy test/CI.
    feed_autostart: bool = True

    # --- Scanner (P7) ---
    scan_symbols: list[str] = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
    scan_tf: str = "15m"
    scan_interval_sec: int = 60
    # SL/TP đề xuất theo ATR: SL = entry ∓ sl×ATR, TP = entry ± tp×ATR.
    scan_sl_atr: float = 1.5
    scan_tp_atr: float = 2.0

    # --- Phí Binance (taker, VIP 0) — dùng cho backtest ---
    binance_spot_fee: float = 0.001  # Spot 0.10%
    binance_futures_fee: float = 0.0005  # Futures (USDⓈ-M) 0.05%
    futures_max_leverage: int = 50


@lru_cache
def get_settings() -> Settings:
    """Singleton settings (cache)."""
    return Settings()


settings = get_settings()
