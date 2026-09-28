"""Core strategy interface — SHARED by all 4 modes (backtest/paper/testnet/live).

A strategy only READS the `Context` (injected by the engine) and returns a list of `Signal`.
It does NOT call APIs, does NOT touch the DB, and does NOT know which mode it runs in →
swapping the Executor = swapping the mode (mitigates RK-4).
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
    price: float | None = None  # for LIMIT
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
    candles: list  # most recent OHLCV (old → new), each item a dict open/high/low/close/volume/ts
    position: Position | None
    indicators: dict = field(default_factory=dict)
    now: datetime | None = None


class Strategy(ABC):
    name: str = "base"
    version: str = "0"
    default_params: dict = {}
    description: str = ""  # methodology — shown in the Strategy Library

    def __init__(self, params: dict | None = None) -> None:
        self.params = {**self.default_params, **(params or {})}

    @abstractmethod
    def on_candle(self, ctx: Context) -> list[Signal]:
        """Receives the (read-only) Context, returns a list of Signal. Called on candle close."""
        ...

    def plot(self, candles: list[dict]) -> dict[str, list]:
        """Chart overlay lines (name → list of values, None during warmup, length = len(candles)).

        Empty by default (only overlay-capable strategies override it). Used for backtest charts.
        """
        return {}

    def plot_pane(self) -> dict[str, int]:
        """Series name → pane: 0 = overlay on price (default), 1 = secondary pane for oscillators.

        Oscillators (RSI/ADX/Stoch/MACD) on a 0–100 or small scale → put in their own pane so
        they do not squash the price scale. Undeclared series → pane 0.
        """
        return {}
