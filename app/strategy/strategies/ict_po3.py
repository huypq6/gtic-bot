"""ICT Power of Three (PO3) — Session AMD (Asia accumulation → London/NY manipulation+distribution).

=== EDIT THE STRATEGY HERE === (see ict_po3.md for the full design)

A day's life cycle under AMD: the Asia session (00:00–08:00 UTC) builds a range; London+NY
(08:00–21:00) SWEEPS the Asia range (manipulation) and then REVERSES into distribution. Sweep
below Asia Low → LONG, sweep above Asia High → SHORT. Confirmed by MSS (break of the reaction
high/low after the sweep) + optional FVG / Order Block. SL beyond the sweep point, TP = rr×risk.
INTRADAY only (UTC), at most 1 trade/day, everything closed before the day rolls over.

Time is taken from `candles[-1]["ts"]` in UTC (NOT ctx.now — backtest does not set it).
Stateful: keeps range/sweep/trade in the instance across candles (runner + backtest reuse
the same instance). Manages SL/TP itself via CLOSE signals (backtest engine does not apply SL/TP).
"""

from datetime import UTC, datetime

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import atr, ema, pad_left


def _utc(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC)


@register
class IctPo3(Strategy):
    name = "ict_po3"
    version = "3"
    description = (
        "[v3] ICT PO3 — swing-structure MSS (CHoCH) + HTF bias + FVG/OB retest + tp_mode + "
        "news filter. RECOMMENDED version (positive in-sample, mixed OOS). See ict_po3.md."
    )
    # Defaults = most ROBUST set from the sweep (scripts/sweep_ict_po3.py) after adding the ATR SL:
    # conf=2 retest, tp=opposite liquidity, SL=ATR×1.0, bias_len 100. SL/TP are REACHABLE (no
    # longer flatten-dominated), win ~45%. But avg PnL is ~breakeven (fee drag from many trades).
    # NOT a sure-profit set.
    default_params = {
        "bias_mode": 1,        # 0=off (both ways) · 1=HTF EMA trend filter (with-trend only)
        "bias_len": 100,       # bias EMA length (candles ~ 4H/daily)
        "confluence": 2,       # 1=MSS-breakout · 2=FVG retest · 3=FVG+OrderBlock retest
        "mss_lookback": 2,     # minimum candles since the sweep before MSS is allowed (debounce)
        "swing": 1,            # fractal half-width to define swing high/low (MSS = swing break)
        "tp_mode": 1,          # 0=TP by rr_target · 1=TP at opposite liquidity (Asia high/low)
        "rr_target": 2.0,      # R multiple for TP (when tp_mode=0; also the fallback for tp_mode=1)
        "sl_mode": 1,          # 0=SL at sweep point (far, often flattened) · 1=ATR SL (near)
        "atr_len": 14,         # ATR period for sl_mode=1
        "atr_mult": 1.0,       # SL distance from entry = atr_mult × ATR (sl_mode=1)
        "sl_buffer_pct": 0.05,  # SL buffer beyond the sweep point, % of price (sl_mode=0)
        "asia_end_h": 8,       # UTC hour the Asia session ends (range locked)
        "flatten_h": 21,       # UTC hour to close all trades (end of NY)
        "news_filter": 2,      # 0=off · 1=block entries during news hours · 2=+block NFP days
        "news_start_h": 12,    # US news window (UTC): 8:30 ET = 12:30 (summer) / 13:30 (winter)
        "news_end_h": 14,
        "max_per_day": 0,      # 0=unlimited (re-enter after close) · N=max N trades/day
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
        self._day = None              # UTC day being tracked
        self._asia_high = None
        self._asia_low = None
        self._sweep = None            # "HIGH" (→SHORT) | "LOW" (→LONG) | None
        self._sweep_extreme = None    # extreme of the sweep (SL goes beyond it)
        self._sweep_ts = None          # sweep candle ts (to find swing structure AFTER it)
        self._since = 0               # candles elapsed since the sweep
        self._armed = False           # MSS done, waiting for FVG retest to enter (conf≥2)
        self._armed_dir = None        # armed direction
        self._fvg_prox = None         # near edge of the FVG (retest level to fill)
        self._n_today = 0             # trades entered today (for max_per_day)
        self._side = None             # "LONG" | "SHORT" | None (open trade)
        self._sl = None
        self._tp = None

    def _reset_day(self, day) -> None:
        self._day = day
        self._asia_high = self._asia_low = None
        self._n_today = 0
        self._reset_setup()

    def _reset_setup(self) -> None:
        """Clear sweep/MSS/armed state to look for a new setup (same day)."""
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

        # 1. New day → close any dangling trade (no overnight holds), then reset.
        if self._day != day:
            if self._side is not None:
                out.append(Signal("CLOSE", ctx.symbol))
                self._clear_trade()
            self._reset_day(day)

        # 2. Asia session: build the range, no trading yet.
        if hour < asia_end_h:
            self._asia_high = (
                cur["high"] if self._asia_high is None else max(self._asia_high, cur["high"])
            )
            self._asia_low = (
                cur["low"] if self._asia_low is None else min(self._asia_low, cur["low"])
            )
            return out

        # 3. In a trade: manage SL/TP + end-of-day flatten (checked on close).
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
                self._reset_setup()  # closed → look for a NEW setup the same day
            return out

        # 4. Outside the hunting window / no Asia range yet → no new entries.
        #    1 trade at a time (enforced in step 3). max_per_day>0 → cap trades/day (lower fees).
        mpd = int(p.get("max_per_day", 0))
        if hour >= flatten_h or self._asia_high is None or self._asia_low is None:
            return out
        if mpd > 0 and self._n_today >= mpd:
            return out

        # 4a. News filter: no new OPEN/ARM/FILL during the news window (or on NFP days).
        #     Open trades are still managed (handled in step 3) — only new entries are blocked.
        if self._news_blocked(dt, hour, p):
            return out

        close = cur["close"]

        # 4b. Armed (MSS done, waiting for FVG retest): fill when price pulls back into the zone,
        #     or cancel if the sweep is broken.
        if self._armed:
            if self._armed_dir == "LONG":
                if cur["low"] < self._sweep_extreme:  # broke past sweep → setup invalid
                    self._reset_setup()
                    return out
                if cur["low"] <= self._fvg_prox:  # pulled back into FVG → enter
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

        # 5. Manipulation — record the day's FIRST sweep.
        if self._sweep is None:
            if cur["high"] > self._asia_high:
                self._sweep, self._sweep_extreme = "HIGH", cur["high"]
            elif cur["low"] < self._asia_low:
                self._sweep, self._sweep_extreme = "LOW", cur["low"]
            if self._sweep is not None:  # mark the sweep candle to find swing structure afterwards
                self._sweep_ts, self._since = cur["ts"], 1
            return out  # need later candles to confirm MSS

        # 6. MSS = CHoCH: break of the latest SWING formed AFTER the sweep (a real structure shift).
        #    LONG: close above the latest swing-high (lower-high of the pullback). SHORT: reverse.
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

        # update the sweep extreme (SL goes beyond it).
        self._since += 1
        if self._sweep == "HIGH":
            self._sweep_extreme = max(self._sweep_extreme, cur["high"])
        else:
            self._sweep_extreme = min(self._sweep_extreme, cur["low"])

        if direction is None:
            return out

        # 6b. HTF bias — trade WITH the trend only (ICT blog: long if bias up, short if down).
        if int(p["bias_mode"]) == 1:
            em = ema([x["close"] for x in candles], int(p["bias_len"]))
            if not em:  # not enough data to determine trend → no entry (safe).
                return out
            bias_up = close > em[-1]
            if (direction == "LONG") != bias_up:  # trade direction must match the bias
                return out

        # 7. Confluence + entry:
        #    conf=1 → enter MARKET right at the MSS breakout (price far from SL).
        #    conf≥2 → ARM: wait for price to RETEST the FVG before entering
        #             (better price, close to SL → R:R achievable).
        conf = int(p["confluence"])
        if conf == 1:
            sig = self._open(ctx, direction, close, p)
            if sig:
                out.append(sig)
            return out

        prox = self._find_fvg(candles, direction)
        if prox is None:  # no FVG to retest yet → wait for later candles (sweep is kept)
            return out
        if conf >= 3 and not self._has_order_block(candles, direction):
            return out
        self._armed, self._armed_dir, self._fvg_prox = True, direction, prox
        return out

    def _sl_distance(self, ctx: Context, entry: float, p: dict) -> float:
        """SL distance. sl_mode=0: to sweep point (far) + buffer. sl_mode=1: atr_mult×ATR (near)."""
        if int(p.get("sl_mode", 0)) == 1:
            a = atr(ctx.candles, int(p["atr_len"]))
            dist = float(p["atr_mult"]) * a if a else 0.0
            return dist if dist > 0 else entry * 0.005  # fallback 0.5% if ATR is unavailable
        buf = entry * float(p["sl_buffer_pct"]) / 100.0
        return abs(entry - self._sweep_extreme) + buf

    def _open(self, ctx: Context, direction: str, entry: float, p: dict) -> Signal | None:
        """Open at `entry`. SL by `sl_mode` (sweep point/ATR). TP by `tp_mode` (rr/liquidity)."""
        rr = float(p["rr_target"])
        tp_mode = int(p.get("tp_mode", 0))
        risk = self._sl_distance(ctx, entry, p)
        if risk <= 0:
            return None
        if direction == "LONG":
            sl, tp = entry - risk, entry + rr * risk
            if tp_mode == 1 and self._asia_high is not None and self._asia_high > entry:
                tp = self._asia_high  # opposite = top of the Asia range
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
        """Latest swing (fractal) in [start_i, end_i): pivot above/below `w` candles each side.

        kind='high' → swing-high (long CHoCH); 'low' → swing-low (short). None if none yet.
        The pivot needs `w` confirming candles after it (all < end_i = current) → natural lag.
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
        """Are new entries blocked by news? NFP = first Friday of the month (day≤7, weekday=4)."""
        nf = int(p.get("news_filter", 0))
        if nf < 1:
            return False
        if int(p["news_start_h"]) <= hour < int(p["news_end_h"]):
            return True
        if nf >= 2 and dt.weekday() == 4 and dt.day <= 7:  # NFP day
            return True
        return False

    @staticmethod
    def _find_fvg(candles: list[dict], direction: str) -> float | None:
        """NEAR edge of the most recent FVG (retest level to fill). None if there is none.

        Bullish: low[i] > high[i-2] → gap [high[i-2], low[i]], near edge = low[i] (gap top).
        Bearish: high[i] < low[i-2] → gap [high[i], low[i-2]], near edge = high[i] (gap bottom).
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
        """Is there an opposite-colour candle (Order Block origin) in the latest MSS push?"""
        w = candles[-5:]
        if direction == "LONG":
            return any(c["close"] < c["open"] for c in w)  # bearish candle = OB for long
        return any(c["close"] > c["open"] for c in w)

    def plot(self, candles):
        """Plot Asia High/Asia Low per day (step lines, pane 0)."""
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
        if int(self.params["bias_mode"]) == 1:  # trend line that filters trade direction
            closes = [c["close"] for c in candles]
            out[f"Bias EMA {int(self.params['bias_len'])}"] = pad_left(
                ema(closes, int(self.params["bias_len"])), len(candles)
            )
        return out
