"""Executor interface — đổi adapter = đổi mode, strategy không biết.

Paper: khớp nội bộ theo giá WS. Testnet/Live (P6/P8): python-binance.
"""

from abc import ABC, abstractmethod

from app.strategy.base import Position, Signal


class Executor(ABC):
    def current_position(self) -> Position | None:
        """Vị thế hiện tại để strategy đọc qua Context. Mặc định None."""
        return None

    @abstractmethod
    async def submit(self, signal: Signal) -> None:
        """Nhận Signal từ strategy/tay → đặt/đóng/hủy lệnh."""
        ...

    @abstractmethod
    async def cancel(self, order_id: str | None = None) -> None:
        """Hủy lệnh chờ (limit)."""
        ...

    @abstractmethod
    async def modify_sltp(self, sl: float | None, tp: float | None) -> None:
        """Sửa SL/TP của vị thế hiện tại."""
        ...

    async def on_price(self, price: float) -> None:
        """Mỗi tick giá. Paper override để check SL/TP/limit. Mặc định no-op."""
        return None
