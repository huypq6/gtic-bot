"""ICT PO3 v4 — sửa 4 lỗi MÔ HÌNH của v3 (không phải tinh chỉnh tham số).

=== SỬA CHIẾN THUẬT Ở ĐÂY === (xem ict_po3.md)

Chẩn đoán trên dữ liệu thật (ETH 15m, 181 ngày): 54% "sweep" của v3 là nến ĐÓNG NGOÀI range
(breakout thật) → v3 fade trend hơn nửa số ngày. v4 sửa:
1. **Rejection sweep** (`reject_sweep`): sweep chỉ hợp lệ khi nến quét ĐÓNG NGƯỢC vào trong
   range Asia (wick ra ngoài, close vào trong = SFP). Đóng ngoài range = breakout → KHÔNG fade.
2. **Displacement MSS** (`disp_mult`): nến phá cấu trúc phải có THÂN ≥ disp_mult×ATR
   (cú đẩy có lực, đúng ICT) — loại MSS yếu giữa chop.
3. **Giờ vào lệnh cuối** (`entry_cutoff_h`): không vào lệnh mới sau giờ này — lệnh vào muộn
   chỉ còn 1–2h trước flatten, chết vì hết giờ chứ không phải sai hướng.
4. **R:R tối thiểu** (`min_rr`, với tp_mode=1): bỏ entry nếu TP (thanh khoản đối diện) gần hơn
   min_rr×risk; chờ retest sâu hơn (R:R tự cải thiện khi entry thấp hơn).

Kế thừa v3: Asia range → sweep → MSS swing (CHoCH) → retest FVG, bias EMA HTF, SL theo ATR,
TP rr/thanh-khoản, lọc tin, 1 lệnh/thời điểm, flatten cuối ngày (UTC, không qua đêm).
"""

from datetime import datetime, timezone

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import atr, ema, pad_left


def _utc(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


@register
class IctPo3V4(Strategy):
    name = "ict_po3"
    version = "4"
    description = (
        "[v4] ICT PO3 — sửa lỗi mô hình: sweep phải REJECTION (đóng ngược vào range, không fade "
        "breakout), MSS cần DISPLACEMENT (thân ≥ k×ATR), giờ-vào-cuối, lọc R:R tối thiểu. "
        "Nền v3 (retest FVG + ATR SL + bias + lọc tin). Intraday 15m/5m."
    )
    default_params = {
        "bias_mode": 1, "bias_len": 100,
        "confluence": 2,        # 1=MSS-breakout · 2=retest FVG · 3=+OrderBlock
        "mss_lookback": 2, "swing": 1,
        "tp_mode": 1, "rr_target": 2.0,
        "sl_mode": 1, "atr_len": 14, "atr_mult": 1.0, "sl_buffer_pct": 0.05,
        "asia_end_h": 8, "flatten_h": 21,
        "news_filter": 2, "news_start_h": 12, "news_end_h": 14,
        "max_per_day": 0,
        # --- v4: sửa mô hình ---
        "reject_sweep": 1,      # 1=sweep phải đóng ngược vào range (SFP) · 0=như v3
        "disp_mult": 0.5,       # thân nến MSS ≥ disp_mult×ATR (0=tắt)
        "entry_cutoff_h": 15,   # không vào lệnh MỚI sau giờ này (UTC) — bộ thắng walk-forward tuần
        "min_rr": 0.0,          # tp_mode=1: bỏ entry nếu TP gần hơn min_rr×risk (0=tắt)
        "size": 0.001,
    }
    param_schema = {
        "bias_mode": {"type": "int", "min": 0, "max": 1, "default": 1},
        "bias_len": {"type": "int", "min": 10, "max": 1000, "default": 100},
        "confluence": {"type": "int", "min": 1, "max": 3, "default": 2},
        "mss_lookback": {"type": "int", "min": 1, "max": 20, "default": 2},
        "swing": {"type": "int", "min": 1, "max": 10, "default": 1},
        "tp_mode": {"type": "int", "min": 0, "max": 1, "default": 1},
        "rr_target": {"type": "float", "min": 0.5, "max": 10.0, "default": 2.0},
        "sl_mode": {"type": "int", "min": 0, "max": 1, "default": 1},
        "atr_len": {"type": "int", "min": 2, "max": 100, "default": 14},
        "atr_mult": {"type": "float", "min": 0.3, "max": 6.0, "default": 1.0},
        "sl_buffer_pct": {"type": "float", "min": 0.0, "max": 2.0, "default": 0.05},
        "asia_end_h": {"type": "int", "min": 1, "max": 23, "default": 8},
        "flatten_h": {"type": "int", "min": 1, "max": 23, "default": 21},
        "news_filter": {"type": "int", "min": 0, "max": 2, "default": 2},
        "news_start_h": {"type": "int", "min": 0, "max": 23, "default": 12},
        "news_end_h": {"type": "int", "min": 0, "max": 23, "default": 14},
        "max_per_day": {"type": "int", "min": 0, "max": 10, "default": 0},
        "reject_sweep": {"type": "int", "min": 0, "max": 1, "default": 1},
        "disp_mult": {"type": "float", "min": 0.0, "max": 3.0, "default": 0.5},
        "entry_cutoff_h": {"type": "int", "min": 8, "max": 23, "default": 15},
        "min_rr": {"type": "float", "min": 0.0, "max": 5.0, "default": 0.0},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._day = None
        self._asia_high = None
        self._asia_low = None
        self._sweep = None            # "HIGH" (→SHORT) | "LOW" (→LONG)
        self._sweep_extreme = None
        self._sweep_i = None
        self._since = 0
        self._armed = False
        self._armed_dir = None
        self._fvg_prox = None
        self._n_today = 0
        self._side = None
        self._sl = None
        self._tp = None

    def _reset_day(self, day) -> None:
        self._day = day
        self._asia_high = self._asia_low = None
        self._n_today = 0
        self._reset_setup()

    def _reset_setup(self) -> None:
        self._sweep = self._sweep_extreme = self._sweep_i = None
        self._since = 0
        self._armed = False
        self._armed_dir = self._fvg_prox = None

    def _clear_trade(self) -> None:
        self._side = self._sl = self._tp = None

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params
        candles = ctx.candles
        if not candles:
            return []
        cur = candles[-1]
        cur_i = len(candles) - 1
        dt = _utc(cur["ts"])
        day, hour = dt.date(), dt.hour
        asia_end_h, flatten_h = int(p["asia_end_h"]), int(p["flatten_h"])
        out: list[Signal] = []

        # 1. Sang ngày mới → đóng lệnh treo rồi reset.
        if self._day != day:
            if self._side is not None:
                out.append(Signal("CLOSE", ctx.symbol))
                self._clear_trade()
            self._reset_day(day)

        # 2. Phiên Asia: gom range.
        if hour < asia_end_h:
            self._asia_high = cur["high"] if self._asia_high is None else max(self._asia_high, cur["high"])
            self._asia_low = cur["low"] if self._asia_low is None else min(self._asia_low, cur["low"])
            return out

        # 3. Đang có lệnh: quản SL/TP + flatten (kiểm theo close).
        if self._side is not None:
            close = cur["close"]
            hit = (
                close <= self._sl or close >= self._tp
                if self._side == "LONG"
                else close >= self._sl or close <= self._tp
            )
            if hit or hour >= flatten_h:
                out.append(Signal("CLOSE", ctx.symbol))
                self._clear_trade()
                self._reset_setup()
            return out

        # 4. Guard vào lệnh mới: hết cửa sổ / chưa có range / quá max_per_day /
        #    quá giờ-vào-cuối (v4) / khung giờ tin.
        mpd = int(p.get("max_per_day", 0))
        if hour >= flatten_h or self._asia_high is None or self._asia_low is None:
            return out
        if mpd > 0 and self._n_today >= mpd:
            return out
        if hour >= int(p["entry_cutoff_h"]):  # v4: lệnh vào muộn chết vì hết giờ
            return out
        if self._news_blocked(dt, hour, p):
            return out

        close = cur["close"]

        # 4b. Đã vũ trang: huỷ nếu phá sweep, fill khi retest FVG.
        if self._armed:
            if self._armed_dir == "LONG":
                if cur["low"] < self._sweep_extreme:
                    self._reset_setup()
                    return out
                if cur["low"] <= self._fvg_prox:
                    sig = self._open(ctx, "LONG", close, p)
                    if sig:
                        out.append(sig)
            else:
                if cur["high"] > self._sweep_extreme:
                    self._reset_setup()
                    return out
                if cur["high"] >= self._fvg_prox:
                    sig = self._open(ctx, "SHORT", close, p)
                    if sig:
                        out.append(sig)
            return out

        # 5. Manipulation — v4: sweep phải REJECTION (đóng ngược vào range) nếu reject_sweep=1.
        if self._sweep is None:
            rj = int(p.get("reject_sweep", 1)) == 1
            if cur["high"] > self._asia_high and (not rj or close < self._asia_high):
                self._sweep, self._sweep_extreme = "HIGH", cur["high"]
            elif cur["low"] < self._asia_low and (not rj or close > self._asia_low):
                self._sweep, self._sweep_extreme = "LOW", cur["low"]
            if self._sweep is not None:
                self._sweep_i, self._since = cur_i, 1
            return out

        # 6. MSS = CHoCH (phá swing sau sweep) + v4: DISPLACEMENT (thân nến ≥ disp_mult×ATR).
        direction = None
        w = int(p["swing"])
        if self._since >= int(p["mss_lookback"]):
            if self._sweep == "LOW":
                ref = self._recent_swing(candles, self._sweep_i, cur_i, w, "high")
                if ref is not None and close > ref:
                    direction = "LONG"
            else:
                ref = self._recent_swing(candles, self._sweep_i, cur_i, w, "low")
                if ref is not None and close < ref:
                    direction = "SHORT"
        if direction is not None and float(p.get("disp_mult", 0)) > 0:
            a = atr(candles, int(p["atr_len"]))
            if a and abs(close - cur["open"]) < float(p["disp_mult"]) * a:
                direction = None  # MSS yếu (không displacement) → bỏ, chờ nến sau

        self._since += 1
        if self._sweep == "HIGH":
            self._sweep_extreme = max(self._sweep_extreme, cur["high"])
        else:
            self._sweep_extreme = min(self._sweep_extreme, cur["low"])
        if direction is None:
            return out

        # 6b. Bias HTF — chỉ đánh thuận trend.
        if int(p["bias_mode"]) == 1:
            em = ema([x["close"] for x in candles], int(p["bias_len"]))
            if not em:
                return out
            if (direction == "LONG") != (close > em[-1]):
                return out

        # 7. Vào lệnh: conf=1 vào ngay; conf≥2 vũ trang chờ retest FVG.
        conf = int(p["confluence"])
        if conf == 1:
            sig = self._open(ctx, direction, close, p)
            if sig:
                out.append(sig)
            return out
        prox = self._find_fvg(candles, direction)
        if prox is None:
            return out
        if conf >= 3 and not self._has_order_block(candles, direction):
            return out
        self._armed, self._armed_dir, self._fvg_prox = True, direction, prox
        return out

    def _sl_distance(self, ctx: Context, entry: float, p: dict) -> float:
        if int(p.get("sl_mode", 0)) == 1:
            a = atr(ctx.candles, int(p["atr_len"]))
            dist = float(p["atr_mult"]) * a if a else 0.0
            return dist if dist > 0 else entry * 0.005
        buf = entry * float(p["sl_buffer_pct"]) / 100.0
        return abs(entry - self._sweep_extreme) + buf

    def _open(self, ctx: Context, direction: str, entry: float, p: dict) -> Signal | None:
        """Mở lệnh. v4: với tp_mode=1, bỏ nếu TP gần hơn min_rr×risk (chờ retest sâu hơn)."""
        rr = float(p["rr_target"])
        tp_mode = int(p.get("tp_mode", 0))
        min_rr = float(p.get("min_rr", 0))
        risk = self._sl_distance(ctx, entry, p)
        if risk <= 0:
            return None
        if direction == "LONG":
            sl, tp = entry - risk, entry + rr * risk
            if tp_mode == 1 and self._asia_high is not None and self._asia_high > entry:
                tp = self._asia_high
                if min_rr > 0 and (tp - entry) < min_rr * risk:
                    return None  # R:R kém → chờ retest sâu hơn (vẫn armed)
            sig = Signal("BUY", ctx.symbol, float(p["size"]), sl=sl, tp=tp)
        else:
            sl, tp = entry + risk, entry - rr * risk
            if tp_mode == 1 and self._asia_low is not None and self._asia_low < entry:
                tp = self._asia_low
                if min_rr > 0 and (entry - tp) < min_rr * risk:
                    return None
            sig = Signal("SELL", ctx.symbol, float(p["size"]), sl=sl, tp=tp)
        self._side, self._sl, self._tp = direction, sl, sig.tp
        self._armed = False
        self._n_today += 1
        return sig

    @staticmethod
    def _recent_swing(candles: list[dict], start_i: int, end_i: int, w: int, kind: str):
        key = "high" if kind == "high" else "low"
        for j in range(end_i - 1 - w, max(start_i, w) - 1, -1):
            v = candles[j][key]
            if kind == "high":
                if all(v > candles[j - d][key] for d in range(1, w + 1)) and \
                   all(v > candles[j + d][key] for d in range(1, w + 1)):
                    return v
            else:
                if all(v < candles[j - d][key] for d in range(1, w + 1)) and \
                   all(v < candles[j + d][key] for d in range(1, w + 1)):
                    return v
        return None

    @staticmethod
    def _news_blocked(dt, hour: int, p: dict) -> bool:
        nf = int(p.get("news_filter", 0))
        if nf < 1:
            return False
        if int(p["news_start_h"]) <= hour < int(p["news_end_h"]):
            return True
        if nf >= 2 and dt.weekday() == 4 and dt.day <= 7:
            return True
        return False

    @staticmethod
    def _find_fvg(candles: list[dict], direction: str) -> float | None:
        w = candles[-6:]
        prox = None
        for i in range(2, len(w)):
            a, c = w[i - 2], w[i]
            if direction == "LONG" and c["low"] > a["high"]:
                prox = c["low"]
            elif direction == "SHORT" and c["high"] < a["low"]:
                prox = c["high"]
        return prox

    @staticmethod
    def _has_order_block(candles: list[dict], direction: str) -> bool:
        w = candles[-5:]
        if direction == "LONG":
            return any(c["close"] < c["open"] for c in w)
        return any(c["close"] > c["open"] for c in w)

    def plot(self, candles):
        asia_end_h = int(self.params["asia_end_h"])
        day_hi: dict = {}
        day_lo: dict = {}
        for c in candles:
            dt = _utc(c["ts"])
            if dt.hour < asia_end_h:
                d = dt.date()
                day_hi[d] = c["high"] if d not in day_hi else max(day_hi[d], c["high"])
                day_lo[d] = c["low"] if d not in day_lo else min(day_lo[d], c["low"])
        hi_line, lo_line = [], []
        for c in candles:
            d = _utc(c["ts"]).date()
            hi_line.append(day_hi.get(d))
            lo_line.append(day_lo.get(d))
        out = {"Asia High": hi_line, "Asia Low": lo_line}
        if int(self.params["bias_mode"]) == 1:
            closes = [c["close"] for c in candles]
            out[f"Bias EMA {int(self.params['bias_len'])}"] = pad_left(
                ema(closes, int(self.params["bias_len"])), len(candles)
            )
        return out
