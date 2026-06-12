"""Ichimoku Kinko Hyo — Tenkan/Kijun cross lọc theo mây (Kumo).

=== SỬA CHIẾN THUẬT Ở ĐÂY ===
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import ichimoku


@register
class Ichimoku(Strategy):
    name = "ichimoku"
    version = "1"
    description = "Ichimoku — Tenkan cắt Kijun + giá trên/dưới mây Kumo (BUY/SELL)."
    default_params = {"conv": 9, "base": 26, "span_b": 52, "size": 0.001}
    param_schema = {
        "conv": {"type": "int", "min": 2, "max": 60, "default": 9},
        "base": {"type": "int", "min": 5, "max": 120, "default": 26},
        "span_b": {"type": "int", "min": 10, "max": 240, "default": 52},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params
        ich = ichimoku(ctx.candles, p["conv"], p["base"], p["span_b"], p["base"])
        if ich is None:
            return []
        price = ctx.price
        tp, tn = ich["tenkan_prev"], ich["tenkan_now"]
        kp, kn = ich["kijun_prev"], ich["kijun_now"]
        cross_up = tp <= kp and tn > kn
        cross_down = tp >= kp and tn < kn
        if cross_up and price > ich["cloud_top"]:      # cắt lên + trên mây → tăng
            return [Signal("BUY", ctx.symbol, p["size"])]
        if cross_down and price < ich["cloud_bottom"]:  # cắt xuống + dưới mây → giảm
            return [Signal("SELL", ctx.symbol, p["size"])]
        return []
