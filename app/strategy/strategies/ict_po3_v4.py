"""ICT PO3 v4 — fixes 4 MODEL flaws of v3 (not parameter tuning).

=== EDIT THE STRATEGY HERE === (see ict_po3.md)

Diagnosis on real data (ETH 15m, 181 days): 54% of v3 "sweeps" were candles CLOSING OUTSIDE the
range (a genuine breakout) → v3 faded the trend on more than half the days. v4 fixes:
1. **Rejection sweep** (`reject_sweep`): a sweep is only valid when the sweep candle CLOSES BACK
   inside the Asia range (wick outside, close inside = SFP). Close outside = breakout → don't fade.
2. **Displacement MSS** (`disp_mult`): the structure-break candle needs a BODY ≥ disp_mult×ATR
   (a forceful push, true to ICT) — filters out weak MSS in chop.
3. **Last entry hour** (`entry_cutoff_h`): no new entries after this hour — late entries have
   only 1–2h left before flatten and die from running out of time, not from being wrong.
4. **Minimum R:R** (`min_rr`, with tp_mode=1): skip the entry if TP (opposite liquidity) is closer
   than min_rr×risk; wait for a deeper retest (R:R improves as the entry gets better).

Inherited from v3: Asia range → sweep → swing MSS (CHoCH) → FVG retest, HTF EMA bias, ATR SL,
rr/liquidity TP, news filter, 1 trade at a time, end-of-day flatten (UTC, no overnight holds).
"""

from datetime import UTC, datetime

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import atr, ema, pad_left


def _utc(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC)


@register
class IctPo3V4(Strategy):
    name = "ict_po3"
    version = "4"
    description = (
        "[v4] ICT PO3 — model fixes: sweep must be a REJECTION (close back inside the range, "
        "don't fade breakouts), MSS needs DISPLACEMENT (body ≥ k×ATR), last-entry hour, "
        "minimum R:R filter. "
        "Built on v3 (FVG retest + ATR SL + bias + news filter). Intraday 15m/5m."
    )
    default_params = {
        "bias_mode": 1, "bias_len": 100,
        "confluence": 2,        # 1=MSS-breakout · 2=FVG retest · 3=+OrderBlock
        "mss_lookback": 2, "swing": 1,
        "tp_mode": 1, "rr_target": 2.0,
        "sl_mode": 1, "atr_len": 14, "atr_mult": 1.0, "sl_buffer_pct": 0.05,
        "asia_end_h": 8, "flatten_h": 21,
        "news_filter": 2, "news_start_h": 12, "news_end_h": 14,
        "max_per_day": 0,
        # --- v4: model fixes ---
        "reject_sweep": 1,      # 1=sweep must close back inside the range (SFP) · 0=as v3
        "disp_mult": 0.5,       # MSS candle body ≥ disp_mult×ATR (0=off)
        "entry_cutoff_h": 15,   # no NEW entries after this UTC hour — weekly walk-forward winner
        "min_rr": 0.0,          # tp_mode=1: skip entry if TP is closer than min_rr×risk (0=off)
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
        self._sweep_ts = None
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
        self._sweep = self._sweep_extreme = self._sweep_ts = None
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

        # 1. New day → close any dangling trade, then reset.
        if self._day != day:
            if self._side is not None:
                out.append(Signal("CLOSE", ctx.symbol))
                self._clear_trade()
            self._reset_day(day)

        # 2. Asia session: build the range.
        if hour < asia_end_h:
            self._asia_high = (
                cur["high"] if self._asia_high is None else max(self._asia_high, cur["high"])
            )
            self._asia_low = (
                cur["low"] if self._asia_low is None else min(self._asia_low, cur["low"])
            )
            return out

        # 3. In a trade: manage SL/TP + flatten (checked on close).
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

        # 4. New-entry guards: window over / no range yet / max_per_day reached /
        #    past last-entry hour (v4) / news window.
        mpd = int(p.get("max_per_day", 0))
        if hour >= flatten_h or self._asia_high is None or self._asia_low is None:
            return out
        if mpd > 0 and self._n_today >= mpd:
            return out
        if hour >= int(p["entry_cutoff_h"]):  # v4: late entries die from running out of time
            return out
        if self._news_blocked(dt, hour, p):
            return out

        close = cur["close"]

        # 4b. Armed: cancel if the sweep is broken, fill on FVG retest.
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

        # 5. Manipulation — v4: if reject_sweep=1, sweep must be a REJECTION (close back in range).
        if self._sweep is None:
            rj = int(p.get("reject_sweep", 1)) == 1
            if cur["high"] > self._asia_high and (not rj or close < self._asia_high):
                self._sweep, self._sweep_extreme = "HIGH", cur["high"]
            elif cur["low"] < self._asia_low and (not rj or close > self._asia_low):
                self._sweep, self._sweep_extreme = "LOW", cur["low"]
            if self._sweep is not None:
                self._sweep_ts, self._since = cur["ts"], 1
            return out

        # 6. MSS = CHoCH (swing break after sweep) + v4: DISPLACEMENT (body ≥ disp_mult×ATR).
        direction = None
        w = int(p["swing"])
        # Anchor the sweep by ts (not index): the live runner passes a sliding window (deque 300),
        # so absolute indices shift every candle → live used to never see a swing/MSS.
        sweep_i = self._index_of(candles, self._sweep_ts)
        if sweep_i is None:  # the sweep candle has scrolled out of the window
            self._reset_setup()
            return out
        if self._since >= int(p["mss_lookback"]):
            if self._sweep == "LOW":
                ref = self._recent_swing(candles, sweep_i, cur_i, w, "high")
                if ref is not None and close > ref:
                    direction = "LONG"
            else:
                ref = self._recent_swing(candles, sweep_i, cur_i, w, "low")
                if ref is not None and close < ref:
                    direction = "SHORT"
        if direction is not None and float(p.get("disp_mult", 0)) > 0:
            a = atr(candles, int(p["atr_len"]))
            if a and abs(close - cur["open"]) < float(p["disp_mult"]) * a:
                direction = None  # weak MSS (no displacement) → drop, wait for a later candle

        self._since += 1
        if self._sweep == "HIGH":
            self._sweep_extreme = max(self._sweep_extreme, cur["high"])
        else:
            self._sweep_extreme = min(self._sweep_extreme, cur["low"])
        if direction is None:
            return out

        # 6b. HTF bias — trade with the trend only.
        if int(p["bias_mode"]) == 1:
            em = ema([x["close"] for x in candles], int(p["bias_len"]))
            if not em:
                return out
            if (direction == "LONG") != (close > em[-1]):
                return out

        # 7. Entry: conf=1 enter immediately; conf≥2 arm and wait for FVG retest.
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
        """Open a trade. v4 (tp_mode=1): skip if TP < min_rr×risk away; wait for a deeper retest."""
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
                    return None  # poor R:R → wait for a deeper retest (stays armed)
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
    def _index_of(candles: list[dict], ts) -> int | None:
        for j in range(len(candles) - 1, -1, -1):
            t = candles[j]["ts"]
            if t == ts:
                return j
            if t < ts:
                break
        return None

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
