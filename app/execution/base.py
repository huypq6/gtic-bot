"""Executor interface — swap the adapter = swap the mode; the strategy doesn't know.

Paper: internal matching on WS prices. Testnet/Live (P6/P8): python-binance.
"""

from abc import ABC, abstractmethod

from app.strategy.base import Position, Signal


class Executor(ABC):
    # Bot snapshot at runtime (strategy/tf/params) — written to the position on open so
    # reviews stay correct after the bot's params are edited or it is deleted. Set by BotManager.
    trade_meta: dict = {}
    # Account sizing of the order being submitted (set by the runner) — stored on the position it
    # opens so Trade results can show requested vs actual risk and why the size was reduced.
    pending_sizing: dict | None = None

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

    async def publish_trade(self, event: str, **data) -> None:
        """'open' / 'close' of a position → bus topic "trade" (Telegram notifier, …).
        Never raises: a notification problem must not affect trading."""
        bus = getattr(self, "_bus", None)
        if bus is None:
            return
        try:
            await bus.publish("trade", {
                "event": event, "mode": getattr(self, "mode", None),
                "bot_id": getattr(self, "bot_id", None), "symbol": getattr(self, "symbol", None),
                "strategy": (self.trade_meta or {}).get("strategy"), **data,
            })
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).exception("publish trade event failed")

    async def on_price(self, price: float) -> None:
        """Called on every price tick. Paper overrides it to check SL/TP/limit. Default: no-op."""
        return None
