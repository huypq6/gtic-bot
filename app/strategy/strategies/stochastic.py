"""Stochastic Oscillator — %K quá bán/quá mua (mean-reversion).

=== SỬA CHIẾN THUẬT Ở ĐÂY ===
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import stochastic_k, stochastic_series


@register
class Stochastic(Strategy):
    name = "stoch"
    version = "1"
    description = "Stochastic — %K quá bán (BUY), quá mua (SELL)."
    default_params = {"period": 14, "oversold": 20, "overbought": 80, "size": 0.001}
    param_schema = {
        "period": {"type": "int", "min": 2, "max": 100, "default": 14},
        "oversold": {"type": "int", "min": 1, "max": 50, "default": 20},
        "overbought": {"type": "int", "min": 50, "max": 99, "default": 80},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params
        k = stochastic_k(ctx.candles, p["period"])
        if k is None:
            return []
        if k < p["oversold"]:
            return [Signal("BUY", ctx.symbol, p["size"])]
        if k > p["overbought"]:
            return [Signal("SELL", ctx.symbol, p["size"])]
        return []

    def plot(self, candles):
        return {"%K": stochastic_series(candles, self.params["period"])}

    def plot_pane(self):
        return {"%K": 1}  # oscillator 0–100 → pane phụ
