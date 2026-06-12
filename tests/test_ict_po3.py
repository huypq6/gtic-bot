"""ICT Power of Three (Session AMD): sweep → MSS (swing-structure/CHoCH) → entry, SL/TP,
retest FVG, bias HTF, tp_mode, lọc tin, flatten/no-overnight."""

from datetime import datetime, timedelta, timezone

from app.strategy.base import Context
from app.strategy.registry import all_strategies, discover
from app.strategy.strategies.ict_po3 import IctPo3

BASE = datetime(2025, 1, 6, tzinfo=timezone.utc)  # mốc UTC tuỳ ý (thứ Hai)


def ts(day: int, hour: int) -> int:
    return int((BASE + timedelta(days=day, hours=hour)).timestamp() * 1000)


def c(day, hour, o, h, low, cl, v=1.0):
    return {"ts": ts(day, hour), "open": o, "high": h, "low": low, "close": cl,
            "volume": v, "symbol": "X"}


def asia(day, hi=101.0, lo=99.0):
    """8 nến phiên Asia (giờ 0..7): nến đầu đặt biên [lo,hi], còn lại nằm trong."""
    bars = [c(day, 0, 100, hi, lo, 100)]
    bars += [c(day, h, 100, 100.5, 99.5, 100) for h in range(1, 8)]
    return bars


def trend_prior(level, n=14, day=-1):
    """n nến ngày hôm trước đi ngang ở `level` — để nạp EMA bias (test lọc trend)."""
    return [c(day, h, level, level + 0.5, level - 0.5, level) for h in range(n)]


def replay(strat, bars):
    out, acc = [], []
    for b in bars:
        acc.append(b)
        out.extend(strat.on_candle(Context("X", b["close"], list(acc), None)))
    return out


def acts(sigs):
    return [s.action for s in sigs]


# Tham số cơ chế: tắt bias + tắt lọc tin (cô lập sweep/MSS), swing=1, debounce mss_lookback=2.
MECH = {"bias_mode": 0, "news_filter": 0, "mss_lookback": 2, "swing": 1, "size": 1}

# LONG breakout: sweep low (h8) → swing-high tại h9 (=99.2) → MSS khi close vượt 99.2 (h11).
LONG_BRK = [
    c(0, 8, 99, 99, 97, 97.5),       # sweep low (97<99), high thấp
    c(0, 9, 97.5, 99.2, 97, 98),     # swing-high = 99.2
    c(0, 10, 98, 99, 97.5, 98.5),    # lower-high → xác nhận swing h9
    c(0, 11, 98.5, 103, 98.5, 102),  # MSS: close 102 > swing-high 99.2
]

# SHORT breakout: sweep high (h8) → swing-low tại h9 (=100.8) → MSS khi close thủng 100.8.
SHORT_BRK = [
    c(0, 8, 101, 103, 101, 102.5),
    c(0, 9, 102.5, 103, 100.8, 102),   # swing-low = 100.8
    c(0, 10, 102, 102.5, 101, 101.5),
    c(0, 11, 101.5, 101.5, 97, 98),    # MSS: close 98 < swing-low 100.8
]

# LONG có FVG để retest: như LONG_BRK nhưng h11 tạo bullish FVG (low 99.5 > swing-high 99.2),
# rồi h12 hồi vào FVG để fill.
LONG_RETEST = [
    c(0, 8, 99, 99, 97, 97.5),
    c(0, 9, 97.5, 99.2, 97, 98),
    c(0, 10, 98, 99, 97.5, 98.5),
    c(0, 11, 98.5, 103, 99.5, 102),    # MSS + bullish FVG (prox = h11.low = 99.5)
    c(0, 12, 102, 102, 99, 99.8),      # retest: low 99 ≤ 99.5 → vào LONG ~99.8
    c(0, 13, 99.8, 108, 99.8, 107.5),  # TP
]


# ---- LONG / SHORT cơ bản (conf=1, vào tại MSS-breakout) ----
def test_long_sweep_low_then_mss():
    bars = asia(0) + LONG_BRK + [c(0, 12, 102, 113, 102, 112.5)]  # TP
    sigs = replay(IctPo3({**MECH, "confluence": 1}), bars)
    a = acts(sigs)
    assert a == ["BUY", "CLOSE"]
    buy = next(s for s in sigs if s.action == "BUY")
    assert buy.sl < 102 < buy.tp  # entry = close MSS (102): SL dưới, TP trên


def test_short_sweep_high_then_mss():
    bars = asia(0) + SHORT_BRK + [c(0, 12, 98, 98, 87, 87.5)]  # TP
    sigs = replay(IctPo3({**MECH, "confluence": 1}), bars)
    a = acts(sigs)
    assert a == ["SELL", "CLOSE"]
    sell = next(s for s in sigs if s.action == "SELL")
    assert sell.tp < 98 < sell.sl


# ---- Flatten cuối ngày ----
def test_flatten_end_of_day():
    flat = [c(0, h, 100, 100.5, 99.5, 100) for h in range(12, 21)]  # giữa SL/TP, không chạm
    bars = asia(0) + LONG_BRK + flat + [c(0, 21, 100, 100, 99.5, 99.8)]
    a = acts(replay(IctPo3({**MECH, "confluence": 1}), bars))
    assert a == ["BUY", "CLOSE"]


# ---- Không giữ qua ngày ----
def test_no_overnight_rollover_close():
    flat = [c(0, h, 100, 100.5, 99.5, 100) for h in range(12, 23)]
    bars = asia(0) + LONG_BRK + flat + [c(1, 1, 100, 100.5, 99.5, 100)]
    a = acts(replay(IctPo3({**MECH, "confluence": 1, "flatten_h": 23}), bars))
    assert a == ["BUY", "CLOSE"]


# ---- Tối đa 1 lệnh/ngày ----
def test_max_one_trade_per_day():
    bars = asia(0) + LONG_BRK + [
        c(0, 12, 102, 113, 102, 112.5),   # TP → CLOSE
        c(0, 13, 100, 100, 96, 97), c(0, 14, 97, 102, 97, 101), c(0, 15, 101, 103, 101, 102),
    ]
    a = acts(replay(IctPo3({**MECH, "confluence": 1}), bars))
    assert a.count("BUY") == 1


# ---- MSS thật: KHÔNG có swing-high thì KHÔNG vào (giá đi thẳng, không lập cấu trúc) ----
def test_no_mss_without_swing():
    # sau sweep low, giá tăng đều (mỗi high cao hơn) → không có swing-high để phá → không MSS.
    straight = [c(0, 8, 99, 99, 97, 98)] + [c(0, h, 98 + (h - 8), 99 + (h - 8), 97 + (h - 8), 98 + (h - 8))
                                            for h in range(9, 14)]
    a = acts(replay(IctPo3({**MECH, "confluence": 1}), asia(0) + straight))
    assert "BUY" not in a


# ---- Confluence ----
def test_confluence_1_enters_at_breakout():
    a = acts(replay(IctPo3({**MECH, "confluence": 1}), asia(0) + LONG_BRK))
    assert "BUY" in a


def test_confluence_2_blocks_without_fvg():
    # LONG_BRK không tạo FVG ở nến MSS → conf=2 không vũ trang → không vào.
    a = acts(replay(IctPo3({**MECH, "confluence": 2}), asia(0) + LONG_BRK))
    assert "BUY" not in a


def test_confluence_2_arms_then_enters_on_retest():
    sigs = replay(IctPo3({**MECH, "confluence": 2}), asia(0) + LONG_RETEST)
    a = acts(sigs)
    assert a == ["BUY", "CLOSE"]
    buy = next(s for s in sigs if s.action == "BUY")
    assert buy.sl < 99.8 < buy.tp  # entry retest (~99.8) thấp hơn breakout (102) → gần SL hơn


def test_confluence_2_no_retest_no_entry():
    norebound = asia(0) + LONG_RETEST[:4] + [
        c(0, 12, 102.5, 105, 102, 104), c(0, 13, 104, 106, 103, 105),  # không hồi về FVG
    ]
    a = acts(replay(IctPo3({**MECH, "confluence": 2}), norebound))
    assert "BUY" not in a


def test_confluence_2_invalidate_on_break_sweep():
    invalid = asia(0) + LONG_RETEST[:4] + [c(0, 12, 102, 102, 96, 96.5)]  # low 96 < sweep_extreme 97
    a = acts(replay(IctPo3({**MECH, "confluence": 2}), invalid))
    assert "BUY" not in a


# ---- tp_mode=1: TP về thanh khoản đối diện (Asia High cho long) ----
def test_tp_mode_opposite_liquidity():
    sigs = replay(IctPo3({**MECH, "confluence": 2, "tp_mode": 1}), asia(0) + LONG_RETEST)
    buy = next(s for s in sigs if s.action == "BUY")
    assert buy.tp == 101.0  # = Asia High (đỉnh range), entry 99.8 < 101


# ---- Bias HTF: chỉ đánh thuận trend ----
def test_bias_allows_long_in_uptrend():
    bars = trend_prior(80) + asia(0) + LONG_BRK
    a = acts(replay(IctPo3({**MECH, "bias_mode": 1, "bias_len": 10, "confluence": 1}), bars))
    assert "BUY" in a


def test_bias_blocks_long_in_downtrend():
    bars = trend_prior(140) + asia(0) + LONG_BRK
    a = acts(replay(IctPo3({**MECH, "bias_mode": 1, "bias_len": 10, "confluence": 1}), bars))
    assert "BUY" not in a


# ---- Lọc tin (NFP / khung giờ tin) ----
def test_news_blocked_window():
    tue = datetime(2025, 1, 7, 12, tzinfo=timezone.utc)
    p = {"news_filter": 1, "news_start_h": 12, "news_end_h": 14}
    assert IctPo3._news_blocked(tue, 12, p) is True
    assert IctPo3._news_blocked(tue, 15, p) is False
    assert IctPo3._news_blocked(tue, 12, {"news_filter": 0}) is False


def test_news_blocked_nfp_day():
    fri = datetime(2025, 1, 3, 16, tzinfo=timezone.utc)  # thứ Sáu đầu tháng 1/2025 = NFP
    base = {"news_start_h": 12, "news_end_h": 14}
    assert IctPo3._news_blocked(fri, 16, {**base, "news_filter": 2}) is True
    assert IctPo3._news_blocked(fri, 16, {**base, "news_filter": 1}) is False


def test_news_filter_blocks_entry():
    pr = {**MECH, "confluence": 1, "news_filter": 1, "news_start_h": 10, "news_end_h": 13}
    assert "BUY" not in acts(replay(IctPo3(pr), asia(0) + LONG_BRK))


# ---- Không vào lệnh trong phiên Asia ----
def test_no_signal_during_asia():
    assert replay(IctPo3(MECH), asia(0)) == []


# ---- plot: Asia High/Low ----
def test_plot_asia_levels():
    s = IctPo3({"bias_mode": 0})
    p = s.plot(asia(0) + [c(0, 10, 100, 101, 99, 100)])
    assert {"Asia High", "Asia Low"} <= set(p)
    assert p["Asia High"][-1] == 101.0 and p["Asia Low"][-1] == 99.0


# ---- swing helper trực tiếp ----
def test_recent_swing_high():
    bars = [c(0, i, 10, 10 + (1 if i == 2 else 0), 9, 10) for i in range(5)]  # high cao nhất ở idx2
    assert IctPo3._recent_swing(bars, 0, 5, 1, "high") == 11.0


# ---- registry ----
def test_registered():
    discover()
    assert "ict_po3" in {c.name for c in all_strategies()}
