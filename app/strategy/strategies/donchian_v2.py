"""Donchian v2 — channel breakout + ATR trailing (chandelier) + ADX/weekend filter.

=== EDIT THE STRATEGY HERE === (see donchian.md)

Upgrades v1 towards "intraday trend-following on 1h" (Concretum/turtle research):
- Entry as in v1: close above the top of the previous `period` candles → LONG;
  below the bottom → SHORT.
- Active exits (v1 only reverses on an opposite breakout):
  - `exit_mode=0`: ATR trailing (chandelier) — trail = extreme close since entry ∓ mult×ATR.
  - `exit_mode=1`: short opposite channel `exit_period` (turtle style: long exits when
    breaking the M-candle low).
  - `exit_mode=2`: whichever hits first (default).
- ADX filter (`adx_min`>0): only enter when ADX ≥ threshold — avoids whipsaw when there is no trend.
- Weekend filter (`dow_filter=1`): no NEW entries from Saturday 00:00 → Sunday 20:00 UTC
  (mean-reverting/chop zone per Concretum research 2018–2025); open positions are still managed.

An opposite breakout of the `period` channel always REVERSES the position
(keeps v1's trend-following nature).
"""

from datetime import UTC, datetime

from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register
from app.strategy.ta import adx_dmi, atr


def _utc(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC)


@register
class DonchianV2(Strategy):
    name = "donchian"
    version = "2"
    description = (
        "[v2] Donchian breakout + ATR trailing stop (chandelier) and/or short exit channel "
        "(turtle), ADX filter + weekend filter (chop Sat→Sun 20h UTC). Trend-following 1h."
    )
    default_params = {
        "period": 20,
        "exit_period": 10,   # opposite channel for exiting (turtle)
        "exit_mode": 2,      # 0=ATR trail · 1=opposite channel · 2=both (first hit)
        "atr_len": 14,
        "atr_mult": 2.5,
        "adx_min": 0,        # 0=ADX filter off
        "adx_len": 14,
        "dow_filter": 0,     # 1=no new entries Sat 00:00 → Sun 20:00 UTC
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
        self._ext: float | None = None  # extreme close since entry (trail ratchet)

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

        # --- manage open position: trail + exit channel + reversal ---
        if self._side is not None:
            self._ext = (
                max(self._ext, close) if self._side == "LONG" else min(self._ext, close)
            )
            # opposite breakout of the main channel → reverse (takes priority over normal exits).
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

        # --- flat: look for an entry ---
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
        return {"Upper channel": up, "Lower channel": lo}
