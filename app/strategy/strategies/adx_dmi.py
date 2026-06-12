"""ADX/DMI — +DI cắt -DI, lọc theo độ mạnh xu hướng (ADX).

=== SỬA CHIẾN THUẬT Ở ĐÂY ===
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import adx_dmi


@register
class AdxDmi(Strategy):
    name = "adx"
    version = "1"
    description = "ADX/DMI — +DI cắt -DI khi ADX đủ mạnh → BUY/SELL."
    default_params = {"period": 14, "adx_min": 25, "size": 0.001}
    param_schema = {
        "period": {"type": "int", "min": 3, "max": 100, "default": 14},
        "adx_min": {"type": "int", "min": 0, "max": 60, "default": 25},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params
        d = adx_dmi(ctx.candles, p["period"])
        if d is None or d["adx"] < p["adx_min"]:
            return []
        pp, pn = d["plus_di_prev"], d["plus_di_now"]
        mp, mn = d["minus_di_prev"], d["minus_di_now"]
        if pp <= mp and pn > mn:  # +DI cắt lên -DI → xu hướng tăng mạnh
            return [Signal("BUY", ctx.symbol, p["size"])]
        if pp >= mp and pn < mn:  # +DI cắt xuống → xu hướng giảm mạnh
            return [Signal("SELL", ctx.symbol, p["size"])]
        return []
