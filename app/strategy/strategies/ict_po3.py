"""ICT Power of Three (PO3) — Session AMD (Asia tích lũy → London/NY thao túng+phân phối).

=== SỬA CHIẾN THUẬT Ở ĐÂY === (xem ict_po3.md cho thiết kế đầy đủ)

Vòng đời 1 ngày theo AMD: phiên Asia (00:00–08:00 UTC) tạo range; London+NY
(08:00–21:00) QUÉT range Asia (manipulation) rồi ĐẢO CHIỀU phân phối. Quét dưới
Asia Low → LONG, quét trên Asia High → SHORT. Xác nhận bằng MSS (phá đỉnh/đáy phản
ứng sau cú quét) + tuỳ chọn FVG / Order Block. SL ngoài điểm quét, TP = rr×risk.
Chỉ đánh TRONG NGÀY (UTC), tối đa 1 lệnh/ngày, đóng hết trước khi sang ngày.

Thời gian lấy từ `candles[-1]["ts"]` theo UTC (KHÔNG dùng ctx.now — backtest không set).
Stateful: giữ range/sweep/lệnh trong instance qua các nến (runner + backtest tái dùng
cùng instance). Tự quản SL/TP bằng tín hiệu CLOSE (engine backtest không tự áp SL/TP).
"""

from datetime import datetime, timezone

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import atr, ema, pad_left


def _utc(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


@register
class IctPo3(Strategy):
    name = "ict_po3"
    version = "3"
    description = (
        "[v3] ICT PO3 — MSS swing-structure (CHoCH) + bias HTF + retest FVG/OB + tp_mode + "
        "lọc tin. Bản KHUYẾN NGHỊ (in-sample dương, OOS hỗn hợp). Xem ict_po3.md."
    )
    # Mặc định = bộ BỀN nhất từ sweep (scripts/sweep_ict_po3.py) sau khi thêm SL theo ATR:
    # conf=2 retest, tp=thanh khoản đối diện, SL=ATR×1.0, bias_len 100. SL/TP CHẠM được (không còn
    # flatten-dominated), win ~45%. Nhưng PnL TB ~hòa (phí ăn mòn do nhiều lệnh). KHÔNG phải bộ chắc lời.
    default_params = {
        "bias_mode": 1,        # 0=tắt (2 chiều) · 1=lọc theo EMA trend HTF (chỉ thuận trend)
        "bias_len": 100,       # độ dài EMA bias (số nến ~ 4H/daily)
        "confluence": 2,       # 1=MSS-breakout · 2=retest FVG · 3=retest FVG+OrderBlock
        "mss_lookback": 2,     # tối thiểu số nến kể từ sweep trước khi cho phép MSS (debounce)
        "swing": 1,            # nửa-độ-rộng fractal để xác định swing high/low (MSS = phá swing)
        "tp_mode": 1,          # 0=TP theo rr_target · 1=TP về thanh khoản đối diện (Asia high/low)
        "rr_target": 2.0,      # bội số R cho TP (khi tp_mode=0; cũng là fallback của tp_mode=1)
        "sl_mode": 1,          # 0=SL tại điểm quét (xa, hay bị flatten) · 1=SL theo ATR (gần, TP dễ chạm)
        "atr_len": 14,         # chu kỳ ATR cho sl_mode=1
        "atr_mult": 1.0,       # SL cách entry = atr_mult × ATR (sl_mode=1)
        "sl_buffer_pct": 0.05,  # đệm SL ngoài điểm quét, theo % giá (sl_mode=0)
        "asia_end_h": 8,       # giờ UTC kết thúc phiên Asia (chốt range)
        "flatten_h": 21,       # giờ UTC đóng hết lệnh (kết thúc NY)
        "news_filter": 2,      # 0=tắt · 1=chặn vào lệnh trong khung giờ tin · 2=+chặn ngày NFP
        "news_start_h": 12,    # khung giờ tin US (UTC): 8:30 ET = 12:30 (hè) / 13:30 (đông)
        "news_end_h": 14,
        "max_per_day": 0,      # 0=không giới hạn (vào lại sau mỗi lần đóng) · N=tối đa N lệnh/ngày (bớt phí)
        "size": 0.001,
    }
    param_schema = {
        "bias_mode": {"type": "int", "min": 0, "max": 1, "default": 1},
        "bias_len": {"type": "int", "min": 10, "max": 1000, "default": 200},
        "confluence": {"type": "int", "min": 1, "max": 3, "default": 2},
        "mss_lookback": {"type": "int", "min": 1, "max": 20, "default": 3},
        "swing": {"type": "int", "min": 1, "max": 10, "default": 2},
        "tp_mode": {"type": "int", "min": 0, "max": 1, "default": 0},
        "rr_target": {"type": "float", "min": 0.5, "max": 10.0, "default": 2.0},
        "sl_mode": {"type": "int", "min": 0, "max": 1, "default": 1},
        "atr_len": {"type": "int", "min": 2, "max": 100, "default": 14},
        "atr_mult": {"type": "float", "min": 0.3, "max": 6.0, "default": 1.5},
        "sl_buffer_pct": {"type": "float", "min": 0.0, "max": 2.0, "default": 0.05},
        "asia_end_h": {"type": "int", "min": 1, "max": 23, "default": 8},
        "flatten_h": {"type": "int", "min": 1, "max": 23, "default": 21},
        "news_filter": {"type": "int", "min": 0, "max": 2, "default": 0},
        "news_start_h": {"type": "int", "min": 0, "max": 23, "default": 12},
        "news_end_h": {"type": "int", "min": 0, "max": 23, "default": 14},
        "max_per_day": {"type": "int", "min": 0, "max": 10, "default": 0},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._day = None              # ngày UTC đang theo dõi
        self._asia_high = None
        self._asia_low = None
        self._sweep = None            # "HIGH" (→SHORT) | "LOW" (→LONG) | None
        self._sweep_extreme = None    # điểm cực trị của cú quét (đặt SL ngoài đây)
        self._sweep_i = None          # index nến quét (để dò swing-structure SAU sweep)
        self._since = 0               # số nến đã qua kể từ sweep
        self._armed = False           # đã MSS, đang chờ giá retest FVG để vào (conf≥2)
        self._armed_dir = None        # hướng đã vũ trang
        self._fvg_prox = None         # mép gần của FVG (mức retest để fill)
        self._n_today = 0             # số lệnh đã vào trong ngày (cho max_per_day)
        self._side = None             # "LONG" | "SHORT" | None (lệnh đang mở)
        self._sl = None
        self._tp = None

    def _reset_day(self, day) -> None:
        self._day = day
        self._asia_high = self._asia_low = None
        self._n_today = 0
        self._reset_setup()

    def _reset_setup(self) -> None:
        """Xoá trạng thái sweep/MSS/vũ trang để dò setup mới (cùng ngày)."""
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

        # 1. Sang ngày mới → đóng lệnh treo (không qua đêm) rồi reset.
        if self._day != day:
            if self._side is not None:
                out.append(Signal("CLOSE", ctx.symbol))
                self._clear_trade()
            self._reset_day(day)

        # 2. Phiên Asia: gom range, chưa giao dịch.
        if hour < asia_end_h:
            self._asia_high = cur["high"] if self._asia_high is None else max(self._asia_high, cur["high"])
            self._asia_low = cur["low"] if self._asia_low is None else min(self._asia_low, cur["low"])
            return out

        # 3. Đang có lệnh: quản SL/TP + flatten cuối ngày (kiểm theo close).
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
                self._reset_setup()  # đóng xong → dò setup MỚI cùng ngày (không giới hạn số lệnh)
            return out

        # 4. Ngoài cửa sổ săn lệnh / chưa có range Asia → không vào mới.
        #    1 lệnh/thời điểm (chặn ở bước 3). max_per_day>0 → giới hạn số lệnh/ngày (giảm phí).
        mpd = int(p.get("max_per_day", 0))
        if hour >= flatten_h or self._asia_high is None or self._asia_low is None:
            return out
        if mpd > 0 and self._n_today >= mpd:
            return out

        # 4a. Lọc tin: không MỞ/ARM/FILL lệnh mới trong khung giờ tin (hoặc ngày NFP).
        #     Lệnh đang mở vẫn được quản (đã xử lý ở bước 3) — chỉ chặn vào mới.
        if self._news_blocked(dt, hour, p):
            return out

        close = cur["close"]

        # 4b. Đã vũ trang (MSS xong, chờ retest FVG): fill khi giá hồi về vùng, hoặc huỷ nếu phá sweep.
        if self._armed:
            if self._armed_dir == "LONG":
                if cur["low"] < self._sweep_extreme:  # phá sâu hơn sweep → setup hỏng, dò lại
                    self._reset_setup()
                    return out
                if cur["low"] <= self._fvg_prox:  # giá hồi vào FVG → vào lệnh (gần SL)
                    sig = self._open(ctx, "LONG", close, p)
                    if sig:
                        out.append(sig)
            else:  # SHORT
                if cur["high"] > self._sweep_extreme:
                    self._reset_setup()
                    return out
                if cur["high"] >= self._fvg_prox:
                    sig = self._open(ctx, "SHORT", close, p)
                    if sig:
                        out.append(sig)
            return out

        # 5. Manipulation — ghi nhận cú quét ĐẦU TIÊN của ngày.
        if self._sweep is None:
            if cur["high"] > self._asia_high:
                self._sweep, self._sweep_extreme = "HIGH", cur["high"]
            elif cur["low"] < self._asia_low:
                self._sweep, self._sweep_extreme = "LOW", cur["low"]
            if self._sweep is not None:  # đánh dấu nến quét để dò swing-structure sau đó
                self._sweep_i, self._since = cur_i, 1
            return out  # cần nến sau để xác nhận MSS

        # 6. MSS = CHoCH: phá SWING gần nhất hình thành SAU cú quét (đảo cấu trúc thật).
        #    LONG: close vượt swing-high gần nhất (lower-high của nhịp hồi). SHORT: ngược lại.
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

        # cập nhật điểm cực trị sweep (SL đặt ngoài đây).
        self._since += 1
        if self._sweep == "HIGH":
            self._sweep_extreme = max(self._sweep_extreme, cur["high"])
        else:
            self._sweep_extreme = min(self._sweep_extreme, cur["low"])

        if direction is None:
            return out

        # 6b. Bias HTF — chỉ đánh THUẬN trend (blog ICT: long khi bias tăng, short khi bias giảm).
        if int(p["bias_mode"]) == 1:
            em = ema([x["close"] for x in candles], int(p["bias_len"]))
            if not em:  # chưa đủ dữ liệu xác định trend → không vào (an toàn).
                return out
            bias_up = close > em[-1]
            if (direction == "LONG") != bias_up:  # hướng lệnh phải khớp bias
                return out

        # 7. Confluence + vào lệnh:
        #    conf=1 → vào MARKET ngay tại MSS-breakout (giá xa SL).
        #    conf≥2 → VŨ TRANG: chờ giá RETEST về FVG mới vào (giá tốt hơn, gần SL → R:R đạt được).
        conf = int(p["confluence"])
        if conf == 1:
            sig = self._open(ctx, direction, close, p)
            if sig:
                out.append(sig)
            return out

        prox = self._find_fvg(candles, direction)
        if prox is None:  # chưa có FVG để retest → chờ nến sau (sweep vẫn giữ)
            return out
        if conf >= 3 and not self._has_order_block(candles, direction):
            return out
        self._armed, self._armed_dir, self._fvg_prox = True, direction, prox
        return out

    def _sl_distance(self, ctx: Context, entry: float, p: dict) -> float:
        """Khoảng cách SL từ entry. sl_mode=0: tới điểm quét (xa) + đệm. sl_mode=1: atr_mult×ATR (gần)."""
        if int(p.get("sl_mode", 0)) == 1:
            a = atr(ctx.candles, int(p["atr_len"]))
            dist = float(p["atr_mult"]) * a if a else 0.0
            return dist if dist > 0 else entry * 0.005  # fallback 0.5% nếu thiếu ATR
        buf = entry * float(p["sl_buffer_pct"]) / 100.0
        return abs(entry - self._sweep_extreme) + buf

    def _open(self, ctx: Context, direction: str, entry: float, p: dict) -> Signal | None:
        """Mở lệnh tại `entry`. SL theo `sl_mode` (điểm quét / ATR). TP theo `tp_mode` (rr / thanh khoản)."""
        rr = float(p["rr_target"])
        tp_mode = int(p.get("tp_mode", 0))
        risk = self._sl_distance(ctx, entry, p)
        if risk <= 0:
            return None
        if direction == "LONG":
            sl, tp = entry - risk, entry + rr * risk
            if tp_mode == 1 and self._asia_high is not None and self._asia_high > entry:
                tp = self._asia_high  # đối diện = đỉnh range Asia
            sig = Signal("BUY", ctx.symbol, float(p["size"]), sl=sl, tp=tp)
        else:
            sl, tp = entry + risk, entry - rr * risk
            if tp_mode == 1 and self._asia_low is not None and self._asia_low < entry:
                tp = self._asia_low
            sig = Signal("SELL", ctx.symbol, float(p["size"]), sl=sl, tp=tp)
        self._side, self._sl, self._tp = direction, sl, sig.tp
        self._armed = False
        self._n_today += 1
        return sig

    @staticmethod
    def _recent_swing(candles: list[dict], start_i: int, end_i: int, w: int, kind: str):
        """Swing (fractal) gần nhất trong [start_i, end_i): tâm cao/thấp hơn `w` nến mỗi bên.

        kind='high' → swing-high (cho CHoCH long); 'low' → swing-low (cho short). None nếu chưa có.
        Tâm cần `w` nến xác nhận phía sau (đều < end_i = nến hiện tại) nên có độ trễ tự nhiên.
        """
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
        """Có chặn vào lệnh mới vì tin không. NFP = thứ Sáu đầu tháng (day≤7, weekday=4)."""
        nf = int(p.get("news_filter", 0))
        if nf < 1:
            return False
        if int(p["news_start_h"]) <= hour < int(p["news_end_h"]):
            return True
        if nf >= 2 and dt.weekday() == 4 and dt.day <= 7:  # ngày NFP
            return True
        return False

    @staticmethod
    def _find_fvg(candles: list[dict], direction: str) -> float | None:
        """Mép GẦN của FVG mới nhất (mức retest để fill). None nếu không có.

        Bullish: low[i] > high[i-2] → gap [high[i-2], low[i]], mép gần = low[i] (đỉnh gap).
        Bearish: high[i] < low[i-2] → gap [high[i], low[i-2]], mép gần = high[i] (đáy gap).
        """
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
        """Có nến đối màu (gốc Order Block) trong cú đẩy MSS gần nhất."""
        w = candles[-5:]
        if direction == "LONG":
            return any(c["close"] < c["open"] for c in w)  # nến giảm = OB cho long
        return any(c["close"] > c["open"] for c in w)

    def plot(self, candles):
        """Vẽ Asia High/Asia Low theo từng ngày (đường bậc thang, pane 0)."""
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
        if int(self.params["bias_mode"]) == 1:  # đường trend lọc hướng lệnh
            closes = [c["close"] for c in candles]
            out[f"Bias EMA {int(self.params['bias_len'])}"] = pad_left(
                ema(closes, int(self.params["bias_len"])), len(candles)
            )
        return out
