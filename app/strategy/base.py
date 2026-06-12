"""Interface cốt lõi cho chiến thuật — CHẠY CHUNG cả 4 mode (backtest/paper/testnet/live).

Strategy chỉ ĐỌC `Context` (engine bơm vào), trả về list `Signal`. KHÔNG gọi API,
KHÔNG đụng DB, KHÔNG biết đang ở mode nào → đổi Executor = đổi mode (chống RK-4).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Signal:
    action: str  # BUY | SELL | CLOSE | CANCEL
    symbol: str
    size: float = 0.0
    order_type: str = "MARKET"  # MARKET | LIMIT
    price: float | None = None  # cho LIMIT
    sl: float | None = None
    tp: float | None = None


@dataclass
class Position:
    symbol: str
    side: str  # LONG | SHORT
    qty: float
    entry_price: float
    sl: float | None = None
    tp: float | None = None


@dataclass
class Context:
    symbol: str
    price: float
    candles: list  # OHLCV gần nhất (cũ → mới), mỗi phần tử dict open/high/low/close/volume/ts
    position: Position | None
    indicators: dict = field(default_factory=dict)
    now: datetime | None = None


class Strategy(ABC):
    name: str = "base"
    version: str = "0"
    default_params: dict = {}
    description: str = ""  # phương pháp luận — hiển thị ở Strategy Library

    def __init__(self, params: dict | None = None) -> None:
        self.params = {**self.default_params, **(params or {})}

    @abstractmethod
    def on_candle(self, ctx: Context) -> list[Signal]:
        """Nhận Context (chỉ đọc), trả về list Signal. Gọi mỗi khi 1 nến đóng."""
        ...

    def plot(self, candles: list[dict]) -> dict[str, list]:
        """Các đường overlay trên chart (tên → list giá trị, None ở warmup, dài = len(candles)).

        Mặc định rỗng (chỉ chiến thuật overlay-được mới override). Dùng cho viz backtest.
        """
        return {}
