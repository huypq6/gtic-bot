"""Ichimoku v2 — v1 + ATR trailing stop (ghìm max DD, vẫn để lời chạy theo trend).

=== SỬA CHIẾN THUẬT Ở ĐÂY ===
Khác v1: thêm stop bám theo giá (trailing). LONG: stop dời LÊN theo `price − atr_mult×ATR`
(chỉ tăng), thủng stop → CLOSE. SHORT đối xứng. Vẫn đảo chiều khi có tín hiệu Ichimoku ngược.
Mục tiêu: cắt DD lúc đảo chiều nhưng giữ phần lớn lợi nhuận trend (xem strategy-research).
"""

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import atr, ichimoku, ichimoku_lines


@register
class IchimokuTrail(Strategy):
    name = "ichimoku"
    version = "2"
    description = (
        "[v2] Ichimoku + ATR trailing stop — như v1 (Tenkan×Kijun + mây) nhưng có stop bám giá "
        "để ghìm max DD, vẫn để lời chạy theo trend. So với v1 (thô) để chọn bản tốt hơn."
    )
    default_params = {
        "conv": 9, "base": 52, "span_b": 52,  # bộ tốt nhất từ sweep v1
        "atr_len": 14, "atr_mult": 2.0,        # trailing stop = atr_mult × ATR
        "size": 0.001,
    }
    param_schema = {
        "conv": {"type": "int", "min": 2, "max": 60, "default": 9},
        "base": {"type": "int", "min": 5, "max": 120, "default": 52},
        "span_b": {"type": "int", "min": 10, "max": 240, "default": 52},
        "atr_len": {"type": "int", "min": 2, "max": 100, "default": 14},
        "atr_mult": {"type": "float", "min": 0.5, "max": 8.0, "default": 2.0},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._side = None    # "LONG" | "SHORT" | None
        self._stop = None    # mức trailing stop hiện tại

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params
        price = ctx.price
        candles = ctx.candles
        a = atr(candles, int(p["atr_len"]))
        m = float(p["atr_mult"])

        # 1) Quản trailing stop nếu đang có lệnh (chỉ dời theo hướng có lợi).
        if self._side == "LONG":
            if a:
                self._stop = max(self._stop, price - m * a)
            if self._stop is not None and price <= self._stop:
                self._side = self._stop = None
                return [Signal("CLOSE", ctx.symbol)]
        elif self._side == "SHORT":
            if a:
                self._stop = min(self._stop, price + m * a)
            if self._stop is not None and price >= self._stop:
                self._side = self._stop = None
                return [Signal("CLOSE", ctx.symbol)]

        # 2) Tín hiệu Ichimoku (cần ATR để đặt stop).
        ich = ichimoku(candles, p["conv"], p["base"], p["span_b"], p["base"])
        if ich is None or not a:
            return []
        tp_, tn = ich["tenkan_prev"], ich["tenkan_now"]
        kp, kn = ich["kijun_prev"], ich["kijun_now"]
        cross_up = tp_ <= kp and tn > kn
        cross_down = tp_ >= kp and tn < kn
        if cross_up and price > ich["cloud_top"] and self._side != "LONG":
            self._side, self._stop = "LONG", price - m * a
            return [Signal("BUY", ctx.symbol, p["size"])]
        if cross_down and price < ich["cloud_bottom"] and self._side != "SHORT":
            self._side, self._stop = "SHORT", price + m * a
            return [Signal("SELL", ctx.symbol, p["size"])]
        return []

    def plot(self, candles):
        p = self.params
        return ichimoku_lines(candles, p["conv"], p["base"], p["span_b"], p["base"])
