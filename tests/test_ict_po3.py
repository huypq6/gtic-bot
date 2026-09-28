"""ICT Power of Three (Session AMD): sweep → MSS (swing-structure/CHoCH) → entry, SL/TP,
retest FVG, HTF bias, tp_mode, news filter, flatten/no-overnight."""

from datetime import UTC, datetime, timedelta

from app.strategy.base import Context
from app.strategy.registry import all_strategies, discover
from app.strategy.strategies.ict_po3 import IctPo3

BASE = datetime(2025, 1, 6, tzinfo=UTC)  # arbitrary UTC anchor (a Monday)


def ts(day: int, hour: int) -> int:
    return int((BASE + timedelta(days=day, hours=hour)).timestamp() * 1000)


def c(day, hour, o, h, low, cl, v=1.0):
    return {"ts": ts(day, hour), "open": o, "high": h, "low": low, "close": cl,
            "volume": v, "symbol": "X"}


def asia(day, hi=101.0, lo=99.0):
    """8 Asia-session candles (hours 0..7): the first sets bounds [lo,hi], the rest stay inside."""
    bars = [c(day, 0, 100, hi, lo, 100)]
    bars += [c(day, h, 100, 100.5, 99.5, 100) for h in range(1, 8)]
    return bars


def trend_prior(level, n=14, day=-1):
    """n candles of the previous day flat at `level` — to seed the EMA bias (trend-filter test)."""
    return [c(day, h, level, level + 0.5, level - 0.5, level) for h in range(n)]


def replay(strat, bars):
    out, acc = [], []
    for b in bars:
        acc.append(b)
        out.extend(strat.on_candle(Context("X", b["close"], list(acc), None)))
    return out


def acts(sigs):
    return [s.action for s in sigs]


# Mechanism params: bias + news filter off, SL at the sweep point (sl_mode=0) for deterministic
# values.
MECH = {"bias_mode": 0, "news_filter": 0, "sl_mode": 0, "mss_lookback": 2, "swing": 1, "size": 1}

# LONG breakout: sweep low (h8) → swing-high at h9 (=99.2) → MSS when close breaks above 99.2 (h11).
LONG_BRK = [
    c(0, 8, 99, 99, 97, 97.5),       # sweep low (97<99), low high
    c(0, 9, 97.5, 99.2, 97, 98),     # swing-high = 99.2
    c(0, 10, 98, 99, 97.5, 98.5),    # lower-high → confirms swing h9
    c(0, 11, 98.5, 103, 98.5, 102),  # MSS: close 102 > swing-high 99.2
]

# SHORT breakout: sweep high (h8) → swing-low at h9 (=100.8) → MSS when close breaks below 100.8.
SHORT_BRK = [
    c(0, 8, 101, 103, 101, 102.5),
    c(0, 9, 102.5, 103, 100.8, 102),   # swing-low = 100.8
    c(0, 10, 102, 102.5, 101, 101.5),
    c(0, 11, 101.5, 101.5, 97, 98),    # MSS: close 98 < swing-low 100.8
]

# LONG with an FVG to retest: like LONG_BRK but h11 forms a bullish FVG (low 99.5 > swing-high
# 99.2),
# then h12 pulls back into the FVG to fill.
LONG_RETEST = [
    c(0, 8, 99, 99, 97, 97.5),
    c(0, 9, 97.5, 99.2, 97, 98),
    c(0, 10, 98, 99, 97.5, 98.5),
    c(0, 11, 98.5, 103, 99.5, 102),    # MSS + bullish FVG (prox = h11.low = 99.5)
    c(0, 12, 102, 102, 99, 99.8),      # retest: low 99 ≤ 99.5 → enter LONG ~99.8
    c(0, 13, 99.8, 108, 99.8, 107.5),  # TP
]


# ---- Basic LONG / SHORT (conf=1, enter at the MSS breakout) ----
def test_long_sweep_low_then_mss():
    bars = asia(0) + LONG_BRK + [c(0, 12, 102, 113, 102, 112.5)]  # TP
    sigs = replay(IctPo3({**MECH, "confluence": 1}), bars)
    a = acts(sigs)
    assert a == ["BUY", "CLOSE"]
    buy = next(s for s in sigs if s.action == "BUY")
    assert buy.sl < 102 < buy.tp  # entry = MSS close (102): SL below, TP above


def test_short_sweep_high_then_mss():
    bars = asia(0) + SHORT_BRK + [c(0, 12, 98, 98, 87, 87.5)]  # TP
    sigs = replay(IctPo3({**MECH, "confluence": 1}), bars)
    a = acts(sigs)
    assert a == ["SELL", "CLOSE"]
    sell = next(s for s in sigs if s.action == "SELL")
    assert sell.tp < 98 < sell.sl


# ---- End-of-day flatten ----
def test_flatten_end_of_day():
    flat = [c(0, h, 100, 100.5, 99.5, 100) for h in range(12, 21)]  # between SL/TP, not touched
    bars = asia(0) + LONG_BRK + flat + [c(0, 21, 100, 100, 99.5, 99.8)]
    a = acts(replay(IctPo3({**MECH, "confluence": 1}), bars))
    assert a == ["BUY", "CLOSE"]


# ---- No overnight holding ----
def test_no_overnight_rollover_close():
    flat = [c(0, h, 100, 100.5, 99.5, 100) for h in range(12, 23)]
    bars = asia(0) + LONG_BRK + flat + [c(1, 1, 100, 100.5, 99.5, 100)]
    a = acts(replay(IctPo3({**MECH, "confluence": 1, "flatten_h": 23}), bars))
    assert a == ["BUY", "CLOSE"]


# ---- One position at a time: while a position is open, do NOT open another ----
def test_one_position_at_a_time():
    bars = asia(0) + LONG_RETEST[:5] + [   # BUY at h12
        c(0, 13, 99.8, 100, 99, 99.5),     # FVG touched again, position open → ignored
        c(0, 14, 99.5, 108, 99.5, 107),    # TP
    ]
    a = acts(replay(IctPo3({**MECH, "confluence": 2}), bars))
    assert a == ["BUY", "CLOSE"]


# ---- No daily trade limit: after closing, a new trade can be entered (LONG then SHORT) ----
def test_multiple_trades_per_day():
    bars = asia(0) + LONG_BRK + [
        c(0, 12, 102, 113, 102, 112.5),    # TP LONG → CLOSE
        c(0, 13, 112, 113, 111, 112),      # new HIGH sweep (price is high)
        c(0, 14, 112, 112.5, 110, 111),    # swing-low = 110
        c(0, 15, 111, 112, 110.5, 111.5),  # confirm swing
        c(0, 16, 111, 111, 105, 106),      # MSS down: close 106 < 110 → SELL
    ]
    a = acts(replay(IctPo3({**MECH, "confluence": 1}), bars))
    assert a[:2] == ["BUY", "CLOSE"] and "SELL" in a  # 2 sequential trades in the day


# ---- max_per_day: cap trades per day (reduces fees) ----
def test_max_per_day_cap():
    bars = asia(0) + LONG_BRK + [
        c(0, 12, 102, 113, 102, 112.5),    # LONG TP → CLOSE (trade 1)
        c(0, 13, 112, 113, 111, 112), c(0, 14, 112, 112.5, 110, 111),
        c(0, 15, 111, 112, 110.5, 111.5), c(0, 16, 111, 111, 105, 106),  # setup SHORT
    ]
    a = acts(replay(IctPo3({**MECH, "confluence": 1, "max_per_day": 1}), bars))
    assert "BUY" in a and "SELL" not in a  # cap=1 → no 2nd trade in the day


# ---- Real MSS: NO swing-high means NO entry (price goes straight up, no structure formed) ----
def test_no_mss_without_swing():
    # after the low sweep, price rises steadily (higher highs) → no swing-high to break → no MSS.
    straight = [c(0, 8, 99, 99, 97, 98)] + [
        c(0, h, 98 + (h - 8), 99 + (h - 8), 97 + (h - 8), 98 + (h - 8))
        for h in range(9, 14)
    ]
    a = acts(replay(IctPo3({**MECH, "confluence": 1}), asia(0) + straight))
    assert "BUY" not in a


# ---- Confluence ----
def test_confluence_1_enters_at_breakout():
    a = acts(replay(IctPo3({**MECH, "confluence": 1}), asia(0) + LONG_BRK))
    assert "BUY" in a


def test_confluence_2_blocks_without_fvg():
    # LONG_BRK does not form an FVG on the MSS candle → conf=2 never arms → no entry.
    a = acts(replay(IctPo3({**MECH, "confluence": 2}), asia(0) + LONG_BRK))
    assert "BUY" not in a


def test_confluence_2_arms_then_enters_on_retest():
    sigs = replay(IctPo3({**MECH, "confluence": 2}), asia(0) + LONG_RETEST)
    a = acts(sigs)
    assert a == ["BUY", "CLOSE"]
    buy = next(s for s in sigs if s.action == "BUY")
    assert buy.sl < 99.8 < buy.tp  # retest entry ~99.8 < breakout 102 → nearer SL


def test_confluence_2_no_retest_no_entry():
    norebound = asia(0) + LONG_RETEST[:4] + [
        c(0, 12, 102.5, 105, 102, 104), c(0, 13, 104, 106, 103, 105),  # no FVG pullback
    ]
    a = acts(replay(IctPo3({**MECH, "confluence": 2}), norebound))
    assert "BUY" not in a


def test_confluence_2_invalidate_on_break_sweep():
    invalid = asia(0) + LONG_RETEST[:4] + [c(0, 12, 102, 102, 96, 96.5)]  # low 96 < sweep 97
    a = acts(replay(IctPo3({**MECH, "confluence": 2}), invalid))
    assert "BUY" not in a


# ---- tp_mode=1: TP at opposite liquidity (Asia High for longs) ----
def test_tp_mode_opposite_liquidity():
    sigs = replay(IctPo3({**MECH, "confluence": 2, "tp_mode": 1}), asia(0) + LONG_RETEST)
    buy = next(s for s in sigs if s.action == "BUY")
    assert buy.tp == 101.0  # = Asia High (top of range), entry 99.8 < 101


# ---- HTF bias: only trade with the trend ----
def test_bias_allows_long_in_uptrend():
    bars = trend_prior(80) + asia(0) + LONG_BRK
    a = acts(replay(IctPo3({**MECH, "bias_mode": 1, "bias_len": 10, "confluence": 1}), bars))
    assert "BUY" in a


def test_bias_blocks_long_in_downtrend():
    bars = trend_prior(140) + asia(0) + LONG_BRK
    a = acts(replay(IctPo3({**MECH, "bias_mode": 1, "bias_len": 10, "confluence": 1}), bars))
    assert "BUY" not in a


# ---- News filter (NFP / news time window) ----
def test_news_blocked_window():
    tue = datetime(2025, 1, 7, 12, tzinfo=UTC)
    p = {"news_filter": 1, "news_start_h": 12, "news_end_h": 14}
    assert IctPo3._news_blocked(tue, 12, p) is True
    assert IctPo3._news_blocked(tue, 15, p) is False
    assert IctPo3._news_blocked(tue, 12, {"news_filter": 0}) is False


def test_news_blocked_nfp_day():
    fri = datetime(2025, 1, 3, 16, tzinfo=UTC)  # first Friday of Jan 2025 = NFP
    base = {"news_start_h": 12, "news_end_h": 14}
    assert IctPo3._news_blocked(fri, 16, {**base, "news_filter": 2}) is True
    assert IctPo3._news_blocked(fri, 16, {**base, "news_filter": 1}) is False


def test_news_filter_blocks_entry():
    pr = {**MECH, "confluence": 1, "news_filter": 1, "news_start_h": 10, "news_end_h": 13}
    assert "BUY" not in acts(replay(IctPo3(pr), asia(0) + LONG_BRK))


# ---- No entries during the Asia session ----
def test_no_signal_during_asia():
    assert replay(IctPo3(MECH), asia(0)) == []


# ---- plot: Asia High/Low ----
def test_plot_asia_levels():
    s = IctPo3({"bias_mode": 0})
    p = s.plot(asia(0) + [c(0, 10, 100, 101, 99, 100)])
    assert {"Asia High", "Asia Low"} <= set(p)
    assert p["Asia High"][-1] == 101.0 and p["Asia Low"][-1] == 99.0


# ---- sl_mode=1 (ATR) puts SL closer to entry than sl_mode=0 (sweep point) → TP easier to hit ----
def test_sl_mode_atr_is_tighter():
    bars = asia(0) + LONG_BRK  # LONG MSS at h11, entry close = 102
    b0 = next(s for s in replay(IctPo3({**MECH, "confluence": 1, "sl_mode": 0}), bars)
              if s.action == "BUY")
    b1 = next(s for s in replay(IctPo3({**MECH, "confluence": 1, "sl_mode": 1,
                                        "atr_len": 5, "atr_mult": 1.0}), bars)
              if s.action == "BUY")
    assert (102 - b1.sl) < (102 - b0.sl)  # ATR risk < sweep-point risk


# ---- swing helper directly ----
def test_recent_swing_high():
    bars = [c(0, i, 10, 10 + (1 if i == 2 else 0), 9, 10) for i in range(5)]  # highest high at idx2
    assert IctPo3._recent_swing(bars, 0, 5, 1, "high") == 11.0


# ---- registry ----
def test_registered():
    discover()
    assert "ict_po3" in {c.name for c in all_strategies()}
