"""Donchian Breakout — price channel breakout (trend-following).

=== EDIT THE STRATEGY HERE ===
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register


@register
class DonchianBreakout(Strategy):
    name = "donchian"
    version = "1"
    description = (
        "Donchian price channel breakout — trend-following: LONG above the channel top, "
        "SHORT below the channel bottom."
    )
    default_params = {"period": 20, "size": 0.001, "sl_pct": 0.0, "tp_pct": 0.0}
    param_schema = {
        "period": {"type": "int", "min": 5, "max": 200, "default": 20},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
        "sl_pct": {"type": "float", "min": 0.0, "max": 50.0, "default": 0.0},
        "tp_pct": {"type": "float", "min": 0.0, "max": 100.0, "default": 0.0},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params["period"]
        if len(ctx.candles) < p + 1:
            return []
        window = ctx.candles[-(p + 1) : -1]  # p candles BEFORE the current candle (avoid lookahead)
        highest = max(c["high"] for c in window)
        lowest = min(c["low"] for c in window)
        price = ctx.price

        if price > highest:
            return [self._signal(ctx.symbol, "BUY", price)]
        if price < lowest:
            return [self._signal(ctx.symbol, "SELL", price)]
        return []

    def plot(self, candles):
        p, n = self.params["period"], len(candles)
        up: list = [None] * n
        lo: list = [None] * n
        for i in range(p, n):
            w = candles[i - p : i]
            up[i] = max(c["high"] for c in w)
            lo[i] = min(c["low"] for c in w)
        return {"Upper channel": up, "Lower channel": lo}

    def _signal(self, symbol: str, action: str, price: float) -> Signal:
        size = self.params["size"]
        sl_pct, tp_pct = self.params["sl_pct"], self.params["tp_pct"]
        long = action == "BUY"
        sl = tp = None
        if sl_pct > 0:
            sl = price * (1 - sl_pct / 100) if long else price * (1 + sl_pct / 100)
        if tp_pct > 0:
            tp = price * (1 + tp_pct / 100) if long else price * (1 - tp_pct / 100)
        return Signal(action, symbol, size, sl=sl, tp=tp)
