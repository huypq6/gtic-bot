"""EMA crossover — golden cross → LONG, death cross → SHORT.

=== SỬA CHIẾN THUẬT Ở ĐÂY === (file-based, sửa ngoài app rồi reload)
Tăng `version` khi đổi logic; DB lưu version + params instance đang chạy.
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import ema


@register
class EmaCross(Strategy):
    name = "ema_cross"
    version = "1"
    description = "Giao cắt EMA nhanh/chậm — trend-following: golden cross LONG, death cross SHORT."
    default_params = {"fast": 9, "slow": 21, "size": 0.001}
    # Schema cho UI render form params (P5).
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
        # so khớp đuôi 2 series (khác độ dài) để xét giao cắt.
        fp, fn = ef[-2], ef[-1]
        sp, sn = es[-2], es[-1]
        if fp <= sp and fn > sn:
            return [Signal("BUY", ctx.symbol, size)]
        if fp >= sp and fn < sn:
            return [Signal("SELL", ctx.symbol, size)]
        return []


@register
class EmaCrossV2(Strategy):
    """v2: thêm bộ lọc khoảng cách (gap %) để giảm vào lệnh nhiễu trên khung nhỏ."""

    name = "ema_cross"
    version = "2"
    description = "EMA cross + bộ lọc gap% — giảm lệnh nhiễu (giao cắt yếu) trên khung nhỏ."
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
        # chỉ vào lệnh khi khoảng cách 2 EMA đủ lớn (gap %).
        gap_ok = sn > 0 and abs(fn - sn) / sn * 100 >= p["gap_pct"]
        if not gap_ok:
            return []
        if fp <= sp and fn > sn:
            return [Signal("BUY", ctx.symbol, p["size"])]
        if fp >= sp and fn < sn:
            return [Signal("SELL", ctx.symbol, p["size"])]
        return []
