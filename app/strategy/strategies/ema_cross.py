"""EMA crossover — golden cross → LONG, death cross → SHORT.

=== EDIT THE STRATEGY HERE === (file-based: edit outside the app, then reload)
Bump `version` when the logic changes; the DB stores the version + params of running instances.
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import ema, pad_left


def _ema_plot(closes: list[float], fast: int, slow: int) -> dict[str, list]:
    n = len(closes)
    return {
        f"EMA {fast}": pad_left(ema(closes, fast), n),
        f"EMA {slow}": pad_left(ema(closes, slow), n),
    }


@register
class EmaCross(Strategy):
    name = "ema_cross"
    version = "1"
    description = "Fast/slow EMA crossover — trend-following: golden cross LONG, death cross SHORT."
    default_params = {"fast": 9, "slow": 21, "size": 0.001}
    # Schema used by the UI to render the params form (P5).
    param_schema = {
        "fast": {"type": "int", "min": 2, "max": 100, "default": 9},
        "slow": {"type": "int", "min": 3, "max": 200, "default": 21},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        fast, slow, size = self.params["fast"], self.params["slow"], self.params["size"]
        closes = [c["close"] for c in ctx.candles]
        ef, es = ema(closes, fast), ema(closes, slow)
        if len(ef) < 2 or len(es) < 2:
            return []
        # align the tails of the 2 series (different lengths) to check for a cross.
        fp, fn = ef[-2], ef[-1]
        sp, sn = es[-2], es[-1]
        if fp <= sp and fn > sn:
            return [Signal("BUY", ctx.symbol, size)]
        if fp >= sp and fn < sn:
            return [Signal("SELL", ctx.symbol, size)]
        return []

    def plot(self, candles):
        return _ema_plot([c["close"] for c in candles], self.params["fast"], self.params["slow"])


@register
class EmaCrossV2(Strategy):
    """v2: adds a distance filter (gap %) to reduce noisy entries on low timeframes."""

    name = "ema_cross"
    version = "2"
    description = "EMA cross + gap% filter — fewer noisy trades (weak crosses) on low timeframes."
    default_params = {"fast": 9, "slow": 21, "size": 0.001, "gap_pct": 0.1}
    param_schema = {
        "fast": {"type": "int", "min": 2, "max": 100, "default": 9},
        "slow": {"type": "int", "min": 3, "max": 200, "default": 21},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
        "gap_pct": {"type": "float", "min": 0.0, "max": 5.0, "default": 0.1},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params
        closes = [c["close"] for c in ctx.candles]
        ef, es = ema(closes, p["fast"]), ema(closes, p["slow"])
        if len(ef) < 2 or len(es) < 2:
            return []
        fp, fn, sp, sn = ef[-2], ef[-1], es[-2], es[-1]
        # only enter when the distance between the 2 EMAs is large enough (gap %).
        gap_ok = sn > 0 and abs(fn - sn) / sn * 100 >= p["gap_pct"]
        if not gap_ok:
            return []
        if fp <= sp and fn > sn:
            return [Signal("BUY", ctx.symbol, p["size"])]
        if fp >= sp and fn < sn:
            return [Signal("SELL", ctx.symbol, p["size"])]
        return []

    def plot(self, candles):
        return _ema_plot([c["close"] for c in candles], self.params["fast"], self.params["slow"])
