"""Supertrend — theo xu hướng dựa trên ATR; vào lệnh khi đường đổi chiều.

=== SỬA CHIẾN THUẬT Ở ĐÂY ===
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import supertrend


@register
class Supertrend(Strategy):
    name = "supertrend"
    version = "1"
    description = "Supertrend (ATR) — đảo lên xu hướng tăng (BUY), đảo xuống (SELL)."
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
        if prev == -1 and now == 1:  # đảo lên xu hướng tăng
            return [Signal("BUY", ctx.symbol, p["size"])]
        if prev == 1 and now == -1:  # đảo xuống xu hướng giảm
            return [Signal("SELL", ctx.symbol, p["size"])]
        return []
