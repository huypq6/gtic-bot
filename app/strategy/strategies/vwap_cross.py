"""VWAP Cross — giá cắt đường VWAP (giá trung bình theo khối lượng).

=== SỬA CHIẾN THUẬT Ở ĐÂY ===
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import vwap


@register
class VwapCross(Strategy):
    name = "vwap"
    version = "1"
    description = "VWAP cross — giá cắt LÊN VWAP (BUY), cắt XUỐNG (SELL)."
    default_params = {"period": 20, "size": 0.001}
    param_schema = {
        "period": {"type": "int", "min": 5, "max": 500, "default": 20},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params["period"]
        if len(ctx.candles) < p + 1:
            return []
        vw_now = vwap(ctx.candles, p)
        vw_prev = vwap(ctx.candles[:-1], p)
        if vw_now is None or vw_prev is None:
            return []
        price_now = ctx.price
        price_prev = ctx.candles[-2]["close"]
        if price_prev <= vw_prev and price_now > vw_now:
            return [Signal("BUY", ctx.symbol, self.params["size"])]
        if price_prev >= vw_prev and price_now < vw_now:
            return [Signal("SELL", ctx.symbol, self.params["size"])]
        return []
