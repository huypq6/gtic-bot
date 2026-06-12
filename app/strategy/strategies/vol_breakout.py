"""Volatility Breakout (Larry Williams k-range) — intraday daily-range breakout.

=== SỬA CHIẾN THUẬT Ở ĐÂY === (xem vol_breakout.md)

Ý tưởng (Larry Williams, phổ biến trong giới quant crypto Hàn Quốc): ngày biến động mạnh
thường TIẾP DIỄN sau khi giá thoát khỏi vùng mở cửa một đoạn bằng k×range hôm trước.
- LONG khi close vượt `open_ngày + k × (high_hômqua − low_hômqua)`.
- SHORT (tùy chọn) khi close thủng `open_ngày − k × range_hômqua`.
- Thoát ở nến ĐẦU ngày kế tiếp (giữ tối đa ~1 ngày, không qua đêm nhiều ngày).
- SL tùy chọn: về open ngày (sl_mode=1) hoặc ATR (sl_mode=2). 1 entry/ngày/chiều.
- Lọc trend EMA (trend_len>0): chỉ LONG khi close>EMA, chỉ SHORT khi close<EMA.

Ngày tính theo UTC (crypto 24/7). Chạy tốt nhất trên nến 15m–1h (fill intraday).
"""

from datetime import datetime, timezone

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import atr, ema


def _utc(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


@register
class VolBreakout(Strategy):
    name = "vol_breakout"
    version = "1"
    description = (
        "Volatility Breakout (Larry Williams): LONG khi close vượt open_ngày + k×range_hômqua "
        "(SHORT đối xứng, tùy chọn), thoát đầu ngày kế tiếp. SL về open ngày hoặc ATR; "
        "lọc trend EMA; 1 entry/ngày/chiều. Intraday 15m–1h, ngày UTC."
    )
    default_params = {
        "k": 0.5,            # hệ số range hôm trước (k_mode=0)
        "k_mode": 0,         # 0=k cố định · 1=k thích ứng noise ratio (systrader79):
                             #   k = TB(1 − |open−close|/(high−low)) của noise_len ngày trước
        "noise_len": 20,
        "direction": 1,      # 0=long-only · 1=cả hai chiều
        "trend_len": 0,      # EMA lọc trend trên TF hiện tại (0=tắt)
        "sl_mode": 3,        # 0=không SL · 1=SL về open ngày · 2=SL theo ATR · 3=SL % cố định
        "sl_pct": 2.5,       # sl_mode=3: cap lỗ %/lệnh (chẩn đoán: cải thiện bền cả 2 nửa 180d)
        "atr_len": 14,
        "atr_mult": 1.5,
        "entry_cutoff_h": 22,  # không vào lệnh MỚI sau giờ này (UTC) — lệnh muộn giữ quá ngắn
        # --- circuit breaker (cổng regime tự tham chiếu, 0=tắt) ---
        "cb_thresh_pct": 0.0,  # PnL lăn (tổng %/lệnh) trong cb_window_d ≤ −ngưỡng → ngừng vào lệnh
        "cb_window_d": 30,
        "cb_pause_d": 14,
        "size": 0.001,
    }
    param_schema = {
        "k": {"type": "float", "min": 0.1, "max": 2.0, "default": 0.5},
        "k_mode": {"type": "int", "min": 0, "max": 1, "default": 0},
        "noise_len": {"type": "int", "min": 5, "max": 60, "default": 20},
        "direction": {"type": "int", "min": 0, "max": 1, "default": 1},
        "trend_len": {"type": "int", "min": 0, "max": 2000, "default": 0},
        "sl_mode": {"type": "int", "min": 0, "max": 3, "default": 3},
        "sl_pct": {"type": "float", "min": 0.3, "max": 10.0, "default": 2.5},
        "atr_len": {"type": "int", "min": 2, "max": 100, "default": 14},
        "atr_mult": {"type": "float", "min": 0.3, "max": 6.0, "default": 1.5},
        "entry_cutoff_h": {"type": "int", "min": 1, "max": 23, "default": 22},
        "cb_thresh_pct": {"type": "float", "min": 0.0, "max": 50.0, "default": 0.0},
        "cb_window_d": {"type": "int", "min": 5, "max": 90, "default": 30},
        "cb_pause_d": {"type": "int", "min": 1, "max": 60, "default": 14},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._day = None
        self._day_open: float | None = None
        self._prev_hi: float | None = None
        self._prev_lo: float | None = None
        self._cur_hi: float | None = None
        self._cur_lo: float | None = None
        self._cur_close: float | None = None
        self._days: list[tuple] = []    # (open, high, low, close) các ngày đã đóng — cho noise k
        self._side: str | None = None   # LONG | SHORT
        self._sl: float | None = None
        self._done_long = False         # đã vào (hoặc bị SL) chiều này hôm nay
        self._done_short = False
        self._entry_price: float | None = None
        self._closed: list[tuple] = []  # (ts_ms, pnl%) lệnh đã đóng — cho circuit breaker
        self._pause_until: int = 0      # ts_ms: ngừng vào lệnh đến lúc này

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params
        candles = ctx.candles
        if not candles:
            return []
        cur = candles[-1]
        day = _utc(cur["ts"]).date()
        hour = _utc(cur["ts"]).hour
        out: list[Signal] = []

        if day != self._day:
            # sang ngày mới: chốt range hôm qua, reset trạng thái ngày, thoát lệnh đang giữ.
            if self._cur_hi is not None and self._day_open is not None:
                self._days.append((self._day_open, self._cur_hi, self._cur_lo, self._cur_close))
                self._days = self._days[-max(p["noise_len"], 1) :]
            self._prev_hi, self._prev_lo = self._cur_hi, self._cur_lo
            self._cur_hi = self._cur_lo = None
            self._day = day
            self._day_open = cur["open"]
            self._done_long = self._done_short = False
            if self._side is not None:
                out.append(Signal("CLOSE", ctx.symbol))
                self._record_close(cur["ts"], cur["close"])
                self._side = self._sl = self._entry_price = None

        self._cur_hi = cur["high"] if self._cur_hi is None else max(self._cur_hi, cur["high"])
        self._cur_lo = cur["low"] if self._cur_lo is None else min(self._cur_lo, cur["low"])
        self._cur_close = cur["close"]

        # quản lý SL của lệnh đang giữ (engine không tự thực thi SL → kiểm theo close).
        if self._side is not None and self._sl is not None:
            if (self._side == "LONG" and cur["close"] <= self._sl) or (
                self._side == "SHORT" and cur["close"] >= self._sl
            ):
                out.append(Signal("CLOSE", ctx.symbol))
                self._record_close(cur["ts"], cur["close"])
                self._side = self._sl = self._entry_price = None
                return out

        if self._side is not None:  # đang giữ lệnh — không vào thêm
            return out
        if self._prev_hi is None or self._prev_lo is None or self._day_open is None:
            return out
        if hour >= p["entry_cutoff_h"]:
            return out
        if cur["ts"] < self._pause_until:  # circuit breaker đang kích hoạt
            return out

        rng = self._prev_hi - self._prev_lo
        if rng <= 0:
            return out
        k = p["k"]
        if p["k_mode"] == 1:
            k = self._noise_k()
            if k is None:
                return out
        up = self._day_open + k * rng
        dn = self._day_open - k * rng
        close = cur["close"]

        trend_ok_long = trend_ok_short = True
        if p["trend_len"] > 0 and len(candles) >= p["trend_len"]:
            e = ema([c["close"] for c in candles], p["trend_len"])[-1]
            trend_ok_long, trend_ok_short = close > e, close < e

        if not self._done_long and close > up and trend_ok_long:
            sl = self._make_sl("LONG", close, candles)
            self._side, self._sl, self._entry_price = "LONG", sl, close
            self._done_long = True
            out.append(Signal("BUY", ctx.symbol, p["size"], sl=sl))
        elif p["direction"] == 1 and not self._done_short and close < dn and trend_ok_short:
            sl = self._make_sl("SHORT", close, candles)
            self._side, self._sl, self._entry_price = "SHORT", sl, close
            self._done_short = True
            out.append(Signal("SELL", ctx.symbol, p["size"], sl=sl))
        return out

    def _record_close(self, ts_ms: int, exit_price: float) -> None:
        """Ghi PnL lệnh vừa đóng (xấp xỉ fill close, trừ phí 2 chiều) → kích circuit breaker."""
        p = self.params
        if p["cb_thresh_pct"] <= 0 or self._entry_price is None or self._side is None:
            return
        sign = 1.0 if self._side == "LONG" else -1.0
        pnl = sign * (exit_price / self._entry_price - 1.0) * 100 - 0.1
        self._closed.append((ts_ms, pnl))
        win_ms = p["cb_window_d"] * 86_400_000
        self._closed = [(t, v) for t, v in self._closed if t > ts_ms - win_ms]
        if sum(v for _, v in self._closed) <= -p["cb_thresh_pct"]:
            self._pause_until = ts_ms + p["cb_pause_d"] * 86_400_000
            self._closed = []  # reset sau khi kích — đếm lại từ đầu sau pause

    def _noise_k(self) -> float | None:
        """k = TB(1 − |open−close|/(high−low)) các ngày đã đóng (cần ≥5 ngày), kẹp [0.3, 0.9]."""
        vals = [
            1 - abs(o - c) / (h - lo)
            for o, h, lo, c in self._days
            if h is not None and lo is not None and h > lo and c is not None
        ]
        if len(vals) < 5:
            return None
        return min(max(sum(vals) / len(vals), 0.3), 0.9)

    def _make_sl(self, side: str, close: float, candles: list[dict]) -> float | None:
        p = self.params
        if p["sl_mode"] == 1:
            return self._day_open
        if p["sl_mode"] == 2:
            a = atr(candles, p["atr_len"])
            if a is None:
                return None
            return close - p["atr_mult"] * a if side == "LONG" else close + p["atr_mult"] * a
        if p["sl_mode"] == 3:
            d = close * p["sl_pct"] / 100
            return close - d if side == "LONG" else close + d
        return None

    def plot(self, candles: list[dict]) -> dict[str, list]:
        """Vẽ mức breakout LONG/SHORT của từng ngày."""
        n = len(candles)
        up: list = [None] * n
        dn: list = [None] * n
        day = None
        day_open = prev_hi = prev_lo = cur_hi = cur_lo = None
        k = self.params["k"]
        for i, c in enumerate(candles):
            d = _utc(c["ts"]).date()
            if d != day:
                prev_hi, prev_lo = cur_hi, cur_lo
                cur_hi = cur_lo = None
                day, day_open = d, c["open"]
            cur_hi = c["high"] if cur_hi is None else max(cur_hi, c["high"])
            cur_lo = c["low"] if cur_lo is None else min(cur_lo, c["low"])
            if prev_hi is not None and prev_lo is not None:
                rng = prev_hi - prev_lo
                up[i] = day_open + k * rng
                dn[i] = day_open - k * rng
        return {"Mức LONG": up, "Mức SHORT": dn}
