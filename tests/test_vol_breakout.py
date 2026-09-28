"""Volatility Breakout (Larry Williams k-range): enter when price crosses
day_open + k×yesterday_range, exit at the start of the next day; optional SL; EMA trend filter;
1 trade/day/direction."""

from datetime import UTC, datetime, timedelta

from app.strategy.base import Context
from app.strategy.strategies.vol_breakout import VolBreakout

BASE = datetime(2025, 1, 6, tzinfo=UTC)  # Monday


def ts(day: int, hour: int) -> int:
    return int((BASE + timedelta(days=day, hours=hour)).timestamp() * 1000)


def c(day, hour, o, h, low, cl, v=1.0):
    return {"ts": ts(day, hour), "open": o, "high": h, "low": low, "close": cl,
            "volume": v, "symbol": "X"}


def flat_day(day, level=100.0, hi=102.0, lo=98.0):
    """24 flat 1h candles at level; the first sets the day's high/low = [lo, hi] (range = hi-lo)."""
    bars = [c(day, 0, level, hi, lo, level)]
    bars += [c(day, h, level, level + 0.2, level - 0.2, level) for h in range(1, 24)]
    return bars


def replay(strat, bars):
    out, acc = [], []
    for b in bars:
        acc.append(b)
        out.extend(strat.on_candle(Context("X", b["close"], list(acc), None)))
    return out


def acts(sigs):
    return [s.action for s in sigs]


# previous day range = 102-98 = 4; k=0.5 → LONG level = day_open + 2, SHORT = day_open − 2.
MECH = {"k": 0.5, "direction": 1, "trend_len": 0, "sl_mode": 0, "size": 1}


def test_long_breakout_and_exit_next_day_open():
    bars = flat_day(0) + [
        c(1, 0, 100, 100.5, 99.5, 100),   # day 1 open = 100 → LONG level = 102
        c(1, 1, 100, 101.9, 100, 101.5),  # not above 102 yet → no entry yet
        c(1, 2, 101.5, 103, 101.5, 102.8),  # close 102.8 > 102 → BUY
        c(1, 3, 102.8, 104, 102.5, 103.5),  # hold
        c(2, 0, 103.5, 104, 103, 103.8),  # start of day 2 → CLOSE
    ]
    sigs = replay(VolBreakout(MECH), bars)
    assert acts(sigs) == ["BUY", "CLOSE"]


def test_no_entry_without_breakout():
    bars = flat_day(0) + [c(1, h, 100, 101.5, 99, 100) for h in range(0, 24)]
    sigs = replay(VolBreakout(MECH), bars)
    assert sigs == []


def test_short_breakout_when_direction_both():
    bars = flat_day(0) + [
        c(1, 0, 100, 100.5, 99.5, 100),    # SHORT level = 98
        c(1, 1, 100, 100, 97.5, 97.8),     # close 97.8 < 98 → SELL
        c(2, 0, 97.8, 98, 97, 97.5),       # start of day 2 → CLOSE
    ]
    sigs = replay(VolBreakout(MECH), bars)
    assert acts(sigs) == ["SELL", "CLOSE"]


def test_long_only_ignores_short():
    bars = flat_day(0) + [
        c(1, 0, 100, 100.5, 99.5, 100),
        c(1, 1, 100, 100, 97.5, 97.8),     # breaks the short level but direction=0
    ]
    sigs = replay(VolBreakout({**MECH, "direction": 0}), bars)
    assert sigs == []


def test_one_entry_per_day():
    bars = flat_day(0) + [
        c(1, 0, 100, 100.5, 99.5, 100),
        c(1, 1, 100, 103, 100, 102.8),     # BUY
        c(1, 2, 102.8, 103, 100, 100.2),   # falls back — no SL (sl_mode=0), keep holding
        c(1, 3, 100.2, 103.5, 100, 103.2),  # crosses the 102 level again — do NOT add
        c(2, 0, 103.2, 103.5, 103, 103.3),  # CLOSE at start of day
    ]
    sigs = replay(VolBreakout(MECH), bars)
    assert acts(sigs) == ["BUY", "CLOSE"]


def test_sl_day_open_cuts_loss():
    bars = flat_day(0) + [
        c(1, 0, 100, 100.5, 99.5, 100),
        c(1, 1, 100, 103, 100, 102.8),      # BUY, SL = day_open = 100
        c(1, 2, 102.8, 102.8, 99, 99.5),    # close 99.5 < 100 → CLOSE (SL)
        c(1, 3, 99.5, 103.5, 99.5, 103.2),  # no re-entry within the day after the SL
    ]
    sigs = replay(VolBreakout({**MECH, "sl_mode": 1}), bars)
    assert acts(sigs) == ["BUY", "CLOSE"]


def test_trend_filter_blocks_counter_trend_long():
    # price flat at 100 for a long time then drops to 90 → close < long EMA → LONG blocked.
    prior = []
    for d in range(-8, 0):
        prior += flat_day(d)
    bars = prior + [
        c(1, 0, 90, 90.5, 89.5, 90),       # day open = 90, previous day range = 4 → LONG level = 92
        c(1, 1, 90, 93, 90, 92.8),         # crosses 92 but close 92.8 < EMA(~100) → blocked
    ]
    sigs = replay(VolBreakout({**MECH, "trend_len": 100, "direction": 0}), bars)
    assert sigs == []


def test_sl_pct_caps_loss():
    bars = flat_day(0) + [
        c(1, 0, 100, 100.5, 99.5, 100),
        c(1, 1, 100, 103, 100, 102.8),       # BUY at 102.8, SL% = 102.8×0.975 ≈ 100.23
        c(1, 2, 102.8, 102.8, 100, 100.1),   # close 100.1 < 100.23 → CLOSE (SL)
        c(1, 3, 100.1, 103.5, 100, 103.2),   # no re-entry within the day
    ]
    sigs = replay(VolBreakout({**MECH, "sl_mode": 3, "sl_pct": 2.5}), bars)
    assert acts(sigs) == ["BUY", "CLOSE"]


def trend_day(day):
    """Clean trend day: open 100 → close 103.9, range [99.9, 104] → noise ≈ 0.05."""
    bars = [c(day, 0, 100, 104, 99.9, 103.9)]
    bars += [c(day, h, 103.9, 104, 103.5, 103.9) for h in range(1, 24)]
    return bars


def test_noise_k_blocks_breakout_after_doji_days():
    # 6 doji days (noise=1 → k clamped to 0.9): LONG level = open + 0.9×4 = 103.6 → close 102.8 does
    # NOT enter.
    bars = []
    for d in range(6):
        bars += flat_day(d)
    bars += [
        c(6, 0, 100, 100.5, 99.5, 100),
        c(6, 1, 100, 103, 100, 102.8),
    ]
    sigs = replay(VolBreakout({**MECH, "k_mode": 1, "noise_len": 20}), bars)
    assert sigs == []


def test_noise_k_allows_breakout_after_trend_days():
    # 6 trend days (noise≈0.05 → k clamped to 0.3): LONG level = 103.9 + 0.3×4.1 ≈ 105.13 → close
    # 105.5 enters.
    bars = []
    for d in range(6):
        bars += trend_day(d)
    bars += [
        c(6, 0, 103.9, 104, 103.8, 103.9),
        c(6, 1, 103.9, 105.6, 103.9, 105.5),
    ]
    sigs = replay(VolBreakout({**MECH, "k_mode": 1, "noise_len": 20}), bars)
    # day 5 (5 days of noise available) breaks out → BUY + CLOSE at start of day 6; then BUY on day
    # 6.
    assert acts(sigs) == ["BUY", "CLOSE", "BUY"]


def lose_long_day(day):
    """Losing LONG day: breaks out up then falls — closes at the next day's start ~3.7% below entry.

    The day's range stays [99,103] (=4) so the next day has a similar breakout level.
    """
    bars = [c(day, 0, 100, 100.5, 99.5, 100)]            # day open = 100, LONG level = 102
    bars += [c(day, 1, 100, 103, 100, 102.8)]            # BUY 102.8
    bars += [c(day, h, 99, 99.2, 99.0, 99) for h in range(2, 24)]  # falls to 99
    return bars


def test_circuit_breaker_pauses_after_losses():
    # cb_thresh=5: 2 losing trades (~−3.8% each) → triggers → day 3 breaks out but does NOT enter.
    bars = flat_day(0, hi=103, lo=99) + lose_long_day(1) + lose_long_day(2) + lose_long_day(3)
    p = {**MECH, "cb_thresh_pct": 5.0, "cb_window_d": 30, "cb_pause_d": 14}
    sigs = replay(VolBreakout(p), bars)
    # day 1: BUY+CLOSE (start of day 2); day 2: BUY+CLOSE (start of day 3, triggers CB); day 3:
    # silent.
    assert acts(sigs) == ["BUY", "CLOSE", "BUY", "CLOSE"]


def test_circuit_breaker_resumes_after_pause():
    bars = flat_day(0, hi=103, lo=99) + lose_long_day(1) + lose_long_day(2)
    # 14 idle days (flat, no breakout) then 1 breakout day — must re-enter.
    for d in range(3, 18):
        bars += flat_day(d, hi=102, lo=98)
    bars += [
        c(18, 0, 100, 100.5, 99.5, 100),
        c(18, 1, 100, 103, 100, 102.8),
    ]
    p = {**MECH, "cb_thresh_pct": 5.0, "cb_window_d": 30, "cb_pause_d": 14}
    sigs = replay(VolBreakout(p), bars)
    assert acts(sigs) == ["BUY", "CLOSE", "BUY", "CLOSE", "BUY"]


def test_circuit_breaker_off_by_default():
    bars = flat_day(0, hi=103, lo=99) + lose_long_day(1) + lose_long_day(2) + lose_long_day(3)
    sigs = replay(VolBreakout(MECH), bars)  # cb off → day 3 still enters (no day 4 yet to close)
    assert acts(sigs) == ["BUY", "CLOSE", "BUY", "CLOSE", "BUY"]


def test_needs_prev_day_range():
    bars = [c(0, h, 100, 102, 98, 100) for h in range(3)]  # no previous day yet
    sigs = replay(VolBreakout(MECH), bars)
    assert sigs == []
