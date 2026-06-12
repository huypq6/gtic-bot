"""Donchian v2 — breakout kênh + ATR trailing (chandelier) + lọc ADX/cuối tuần.

=== SỬA CHIẾN THUẬT Ở ĐÂY === (xem donchian.md)

Nâng cấp v1 theo hướng "intraday trend-following 1h" (nghiên cứu Concretum/turtle):
- Entry như v1: close vượt đỉnh kênh `period` nến trước → LONG; thủng đáy → SHORT.
- Exit chủ động (v1 chỉ đảo chiều khi breakout ngược):
  - `exit_mode=0`: ATR trailing (chandelier) — trail = cực trị close kể từ entry ∓ mult×ATR.
  - `exit_mode=1`: kênh ngược ngắn `exit_period` (kiểu turtle: long thoát khi thủng đáy M nến).
  - `exit_mode=2`: cái nào chạm trước (mặc định).
- Lọc ADX (`adx_min`>0): chỉ vào khi ADX ≥ ngưỡng — tránh whipsaw lúc không có trend.
- Lọc cuối tuần (`dow_filter=1`): không vào lệnh MỚI từ thứ Bảy 00:00 → Chủ nhật 20:00 UTC
  (vùng mean-reverting/chop theo nghiên cứu Concretum 2018–2025); lệnh đang giữ vẫn quản lý.

Breakout ngược kênh `period` luôn ĐẢO CHIỀU vị thế (giữ tính trend-following của v1).
"""

from datetime import datetime, timezone

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import adx_dmi, atr


def _utc(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


@register
class DonchianV2(Strategy):
    name = "donchian"
    version = "2"
    description = (
        "[v2] Donchian breakout + ATR trailing stop (chandelier) hoặc/và kênh-thoát ngắn "
        "(turtle), lọc ADX + lọc cuối tuần (chop Sat→Sun 20h UTC). Trend-following 1h."
    )
    default_params = {
        "period": 20,
        "exit_period": 10,   # kênh ngược để thoát (turtle)
        "exit_mode": 2,      # 0=ATR trail · 1=kênh ngược · 2=cả hai (chạm trước)
        "atr_len": 14,
        "atr_mult": 2.5,
        "adx_min": 0,        # 0=tắt lọc ADX
        "adx_len": 14,
        "dow_filter": 0,     # 1=không entry mới Sat 00:00 → Sun 20:00 UTC
        "size": 0.001,
    }
    param_schema = {
        "period": {"type": "int", "min": 5, "max": 200, "default": 20},
        "exit_period": {"type": "int", "min": 2, "max": 100, "default": 10},
        "exit_mode": {"type": "int", "min": 0, "max": 2, "default": 2},
        "atr_len": {"type": "int", "min": 2, "max": 100, "default": 14},
        "atr_mult": {"type": "float", "min": 0.3, "max": 99.0, "default": 2.5},
        "adx_min": {"type": "int", "min": 0, "max": 99, "default": 0},
        "adx_len": {"type": "int", "min": 2, "max": 100, "default": 14},
        "dow_filter": {"type": "int", "min": 0, "max": 1, "default": 0},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._side: str | None = None  # LONG | SHORT
        self._ext: float | None = None  # cực trị close kể từ entry (trail ratchet)

    @staticmethod
    def _weekend(dt: datetime) -> bool:
        return dt.weekday() == 5 or (dt.weekday() == 6 and dt.hour < 20)

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params
        candles = ctx.candles
        if len(candles) < p["period"] + 1:
            return []
        cur = candles[-1]
        close = cur["close"]
        window = candles[-(p["period"] + 1) : -1]
        highest = max(c["high"] for c in window)
        lowest = min(c["low"] for c in window)

        # --- quản lý lệnh đang giữ: trail + kênh-thoát + đảo chiều ---
        if self._side is not None:
            self._ext = (
                max(self._ext, close) if self._side == "LONG" else min(self._ext, close)
            )
            # breakout ngược kênh chính → đảo chiều (ưu tiên hơn exit thường).
            if self._side == "LONG" and close < lowest:
                return self._enter("SHORT", ctx, close)
            if self._side == "SHORT" and close > highest:
                return self._enter("LONG", ctx, close)

            exit_hit = False
            if p["exit_mode"] in (0, 2):
                a = atr(candles, p["atr_len"])
                if a is not None:
                    trail = (
                        self._ext - p["atr_mult"] * a
                        if self._side == "LONG"
                        else self._ext + p["atr_mult"] * a
                    )
                    exit_hit = close < trail if self._side == "LONG" else close > trail
            if not exit_hit and p["exit_mode"] in (1, 2) and len(candles) > p["exit_period"]:
                w = candles[-(p["exit_period"] + 1) : -1]
                if self._side == "LONG":
                    exit_hit = close < min(c["low"] for c in w)
                else:
                    exit_hit = close > max(c["high"] for c in w)
            if exit_hit:
                self._side = self._ext = None
                return [Signal("CLOSE", ctx.symbol)]
            return []

        # --- đang flat: tìm entry ---
        if p["dow_filter"] == 1 and self._weekend(_utc(cur["ts"])):
            return []
        if p["adx_min"] > 0:
            d = adx_dmi(candles, p["adx_len"])
            if d is None or d["adx"] < p["adx_min"]:
                return []
        if close > highest:
            return self._enter("LONG", ctx, close)
        if close < lowest:
            return self._enter("SHORT", ctx, close)
        return []

    def _enter(self, side: str, ctx: Context, close: float) -> list[Signal]:
        self._side, self._ext = side, close
        action = "BUY" if side == "LONG" else "SELL"
        return [Signal(action, ctx.symbol, self.params["size"])]

    def plot(self, candles: list[dict]) -> dict[str, list]:
        p, n = self.params["period"], len(candles)
        up: list = [None] * n
        lo: list = [None] * n
        for i in range(p, n):
            w = candles[i - p : i]
            up[i] = max(c["high"] for c in w)
            lo[i] = min(c["low"] for c in w)
        return {"Kênh trên": up, "Kênh dưới": lo}
