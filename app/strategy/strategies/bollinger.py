"""Bollinger Bands Reversion — hồi quy về trung bình.

=== SỬA CHIẾN THUẬT Ở ĐÂY ===
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import sma, stdev


@register
class BollingerReversion(Strategy):
    name = "bollinger"
    version = "1"
    description = "Bollinger Bands reversion — chạm dải dưới (BUY), chạm dải trên (SELL)."
    default_params = {"period": 20, "mult": 2.0, "size": 0.001}
    param_schema = {
        "period": {"type": "int", "min": 5, "max": 200, "default": 20},
        "mult": {"type": "float", "min": 0.5, "max": 5.0, "default": 2.0},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        p, mult, size = self.params["period"], self.params["mult"], self.params["size"]
        closes = [c["close"] for c in ctx.candles]
        mid = sma(closes, p)
        sd = stdev(closes, p)
        if mid is None or sd is None:
            return []
        upper, lower = mid + mult * sd, mid - mult * sd
        if ctx.price <= lower:
            return [Signal("BUY", ctx.symbol, size)]   # quá bán → bật về mid
        if ctx.price >= upper:
            return [Signal("SELL", ctx.symbol, size)]  # quá mua → rơi về mid
        return []
