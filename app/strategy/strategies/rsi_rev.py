"""RSI reversal — RSI < oversold → BUY (bắt đáy), RSI > overbought → SELL.

=== SỬA CHIẾN THUẬT Ở ĐÂY ===
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import rsi


@register
class RsiReversal(Strategy):
    name = "rsi_rev"
    version = "1"
    default_params = {"period": 14, "oversold": 30, "overbought": 70, "size": 0.001}
    param_schema = {
        "period": {"type": "int", "min": 2, "max": 100, "default": 14},
        "oversold": {"type": "int", "min": 1, "max": 50, "default": 30},
        "overbought": {"type": "int", "min": 50, "max": 99, "default": 70},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params
        closes = [c["close"] for c in ctx.candles]
        series = rsi(closes, p["period"])
        if not series:
            return []
        last = series[-1]
        if last < p["oversold"]:
            return [Signal("BUY", ctx.symbol, p["size"])]
        if last > p["overbought"]:
            return [Signal("SELL", ctx.symbol, p["size"])]
        return []
