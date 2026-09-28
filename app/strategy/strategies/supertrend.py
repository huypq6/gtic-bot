"""Supertrend — ATR-based trend following; enters when the line flips direction.

=== EDIT THE STRATEGY HERE ===
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import supertrend, supertrend_line


@register
class Supertrend(Strategy):
    name = "supertrend"
    version = "1"
    description = "Supertrend (ATR) — flips to uptrend (BUY), flips to downtrend (SELL)."
    default_params = {"period": 10, "mult": 3.0, "size": 0.001}
    param_schema = {
        "period": {"type": "int", "min": 3, "max": 100, "default": 10},
        "mult": {"type": "float", "min": 0.5, "max": 10.0, "default": 3.0},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params
        dirs = supertrend(ctx.candles, p["period"], p["mult"])
        if len(dirs) < 2:
            return []
        prev, now = dirs[-2], dirs[-1]
        if prev == -1 and now == 1:  # flipped to uptrend
            return [Signal("BUY", ctx.symbol, p["size"])]
        if prev == 1 and now == -1:  # flipped to downtrend
            return [Signal("SELL", ctx.symbol, p["size"])]
        return []

    def plot(self, candles):
        p = self.params
        return {f"Supertrend {p['period']}": supertrend_line(candles, p["period"], p["mult"])}
