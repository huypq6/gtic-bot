"""Executor interface — swap the adapter = swap the mode; the strategy doesn't know.

Paper: internal matching on WS prices. Testnet/Live (P6/P8): python-binance.
"""

from abc import ABC, abstractmethod

from app.strategy.base import Position, Signal


class Executor(ABC):
    # Bot snapshot at runtime (strategy/tf/params) — written to the position on open so
    # reviews stay correct after the bot's params are edited or it is deleted. Set by BotManager.
    trade_meta: dict = {}

    def current_position(self) -> Position | None:
        """Current position for the strategy to read via Context. Defaults to None."""
        return None

    @abstractmethod
    async def submit(self, signal: Signal) -> None:
        """Receive a Signal from a strategy/manual action → place/close/cancel orders."""
        ...

    @abstractmethod
    async def cancel(self, order_id: str | None = None) -> None:
        """Cancel a pending (limit) order."""
        ...

    @abstractmethod
    async def modify_sltp(self, sl: float | None, tp: float | None) -> None:
        """Modify SL/TP of the current position."""
        ...

    async def on_price(self, price: float) -> None:
        """Called on every price tick. Paper overrides it to check SL/TP/limit. Default: no-op."""
        return None
