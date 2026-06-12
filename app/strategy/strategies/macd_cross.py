"""MACD Crossover — giao cắt MACD line và signal line (trend/momentum).

=== SỬA CHIẾN THUẬT Ở ĐÂY ===
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import macd


@register
class MacdCross(Strategy):
    name = "macd"
    version = "1"
    description = "MACD crossover — MACD cắt LÊN signal (BUY), cắt XUỐNG (SELL)."
    default_params = {"fast": 12, "slow": 26, "signal": 9, "size": 0.001}
    param_schema = {
        "fast": {"type": "int", "min": 2, "max": 100, "default": 12},
        "slow": {"type": "int", "min": 3, "max": 200, "default": 26},
        "signal": {"type": "int", "min": 2, "max": 50, "default": 9},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params
        closes = [c["close"] for c in ctx.candles]
        m, s = macd(closes, p["fast"], p["slow"], p["signal"])
        if len(m) < 2 or len(s) < 2:
            return []
        m = m[-len(s) :]  # căn đuôi MACD line theo signal
        mp, mn, sp, sn = m[-2], m[-1], s[-2], s[-1]
        if mp <= sp and mn > sn:
            return [Signal("BUY", ctx.symbol, p["size"])]
        if mp >= sp and mn < sn:
            return [Signal("SELL", ctx.symbol, p["size"])]
        return []
