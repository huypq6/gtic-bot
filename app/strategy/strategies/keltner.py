"""Keltner Channel Breakout — vượt dải EMA ± ATR (trend/momentum).

=== SỬA CHIẾN THUẬT Ở ĐÂY ===
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import atr, ema


@register
class KeltnerBreakout(Strategy):
    name = "keltner"
    version = "1"
    description = "Keltner breakout — vượt dải trên (BUY), thủng dải dưới (SELL)."
    default_params = {"period": 20, "mult": 2.0, "size": 0.001}
    param_schema = {
        "period": {"type": "int", "min": 5, "max": 200, "default": 20},
        "mult": {"type": "float", "min": 0.5, "max": 6.0, "default": 2.0},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        period, mult, size = self.params["period"], self.params["mult"], self.params["size"]
        closes = [c["close"] for c in ctx.candles]
        mid_series = ema(closes, period)
        a = atr(ctx.candles, period)
        if not mid_series or a is None:
            return []
        mid = mid_series[-1]
        upper, lower = mid + mult * a, mid - mult * a
        if ctx.price > upper:
            return [Signal("BUY", ctx.symbol, size)]   # bứt phá lên
        if ctx.price < lower:
            return [Signal("SELL", ctx.symbol, size)]  # bứt phá xuống
        return []
