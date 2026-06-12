"""Grid (lưới) — mua thấp/bán cao quanh một mốc tham chiếu (SMA).

=== SỬA CHIẾN THUẬT Ở ĐÂY ===
Lưu ý: engine 1 bot = 1 vị thế, nên đây là bản grid "1 nấc/1 vị thế": vào lệnh khi
giá lệch `step_pct` khỏi mốc, chốt khi giá quay về mốc, rồi lặp lại.
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import sma


@register
class Grid(Strategy):
    name = "grid"
    version = "1"
    description = "Grid quanh SMA — giá xuống 1 nấc BUY / lên 1 nấc SELL, chốt khi về mốc."
    default_params = {"period": 20, "step_pct": 1.0, "size": 0.001}
    param_schema = {
        "period": {"type": "int", "min": 2, "max": 200, "default": 20},
        "step_pct": {"type": "float", "min": 0.1, "max": 20.0, "default": 1.0},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        period, step, size = self.params["period"], self.params["step_pct"], self.params["size"]
        closes = [c["close"] for c in ctx.candles]
        ref = sma(closes, period)
        if ref is None:
            return []
        lower, upper = ref * (1 - step / 100), ref * (1 + step / 100)
        price = ctx.price
        pos = ctx.position
        if pos is None:
            if price <= lower:
                return [Signal("BUY", ctx.symbol, size)]   # giá xuống 1 nấc → mua
            if price >= upper:
                return [Signal("SELL", ctx.symbol, size)]  # giá lên 1 nấc → bán khống
            return []
        # đang có vị thế → chốt khi giá quay về mốc tham chiếu
        if pos.side == "LONG" and price >= ref:
            return [Signal("CLOSE", ctx.symbol)]
        if pos.side == "SHORT" and price <= ref:
            return [Signal("CLOSE", ctx.symbol)]
        return []

    def plot(self, candles):
        closes = [c["close"] for c in candles]
        p, step, n = self.params["period"], self.params["step_pct"], len(candles)
        mid: list = [None] * n
        up: list = [None] * n
        lo: list = [None] * n
        for i in range(p - 1, n):
            m = sum(closes[i - p + 1 : i + 1]) / p
            mid[i], up[i], lo[i] = m, m * (1 + step / 100), m * (1 - step / 100)
        return {"Mốc (SMA)": mid, "Nấc trên": up, "Nấc dưới": lo}
