"""Parabolic SAR — trailing stop & reverse theo xu hướng (Wilder).

=== SỬA CHIẾN THUẬT Ở ĐÂY ===
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import psar


@register
class ParabolicSar(Strategy):
    name = "psar"
    version = "1"
    description = "Parabolic SAR — SAR đảo lên (BUY), đảo xuống (SELL)."
    default_params = {"step": 0.02, "max_af": 0.2, "size": 0.001}
    param_schema = {
        "step": {"type": "float", "min": 0.001, "max": 0.5, "default": 0.02},
        "max_af": {"type": "float", "min": 0.05, "max": 1.0, "default": 0.2},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        dirs = psar(ctx.candles, self.params["step"], self.params["max_af"])
        if len(dirs) < 2:
            return []
        prev, now = dirs[-2], dirs[-1]
        if prev == -1 and now == 1:
            return [Signal("BUY", ctx.symbol, self.params["size"])]
        if prev == 1 and now == -1:
            return [Signal("SELL", ctx.symbol, self.params["size"])]
        return []
