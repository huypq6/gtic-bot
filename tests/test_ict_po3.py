"""ICT Power of Three (Session AMD) — kịch bản sweep→MSS→entry, SL/TP, flatten, confluence."""

from datetime import datetime, timedelta, timezone

from app.strategy.base import Context
from app.strategy.registry import all_strategies, discover
from app.strategy.strategies.ict_po3 import IctPo3

BASE = datetime(2025, 1, 6, tzinfo=timezone.utc)  # mốc UTC tuỳ ý


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


# Tham số chung cho test cơ chế: TẮT lọc bias để cô lập sweep/MSS/exit.
MECH = {"bias_mode": 0, "mss_lookback": 2, "size": 1}


def replay(strat, bars):
    out, acc = [], []
    for b in bars:
        acc.append(b)
        out.extend(strat.on_candle(Context("X", b["close"], list(acc), None)))
    return out


def acts(sigs):
    return [s.action for s in sigs]


# ---- LONG: sweep Asia low → MSS lên → BUY, chạm TP → CLOSE ----
def test_long_sweep_low_then_mss():
    bars = asia(0) + [
        c(0, 8, 100, 100, 98, 98.5),       # quét dưới Asia Low (98 < 99)
        c(0, 9, 98.5, 99.5, 97, 97.5),     # since=1 < lookback → chưa MSS
        c(0, 10, 98, 101, 98, 100.5),      # MSS: close 100.5 > đỉnh phản ứng 100
        c(0, 11, 100.5, 108.5, 100.5, 108),  # chạm TP
    ]
    sigs = replay(IctPo3({**MECH, "confluence": 1}), bars)
    a = acts(sigs)
    assert "BUY" in a and "CLOSE" in a
    assert a.index("BUY") < a.index("CLOSE")
    buy = next(s for s in sigs if s.action == "BUY")
    assert buy.sl is not None and buy.tp is not None
    assert buy.sl < 100.5 < buy.tp  # entry = close nến MSS (100.5): SL dưới, TP trên


# ---- SHORT: sweep Asia high → MSS xuống → SELL ----
def test_short_sweep_high_then_mss():
    bars = asia(0) + [
        c(0, 8, 100, 102, 100, 101.5),     # quét trên Asia High (102 > 101)
        c(0, 9, 101.5, 103, 101, 102.5),   # since=1 < lookback
        c(0, 10, 102, 102, 99, 99.5),      # MSS: close 99.5 < đáy phản ứng 100
        c(0, 11, 99.5, 99.5, 91, 91.5),    # chạm TP
    ]
    sigs = replay(IctPo3({**MECH, "confluence": 1}), bars)
    a = acts(sigs)
    assert "SELL" in a and "CLOSE" in a
    sell = next(s for s in sigs if s.action == "SELL")
    assert sell.tp < 99.5 < sell.sl  # entry = close nến MSS (99.5): short → TP dưới, SL trên


# ---- Flatten cuối ngày: không chạm TP/SL vẫn đóng ở flatten_h ----
def test_flatten_end_of_day():
    bars = asia(0) + [
        c(0, 8, 100, 100, 98, 98.5),
        c(0, 9, 98.5, 99.5, 97, 97.5),
        c(0, 10, 98, 101, 98, 100.5),      # BUY
    ] + [c(0, h, 100, 100.5, 99.5, 100) for h in range(11, 21)] + [
        c(0, 21, 100, 100, 99.5, 99.8),    # giờ flatten → CLOSE
    ]
    a = acts(replay(IctPo3({**MECH, "confluence": 1}), bars))
    assert a == ["BUY", "CLOSE"]


# ---- Không giữ qua ngày: lệnh mở treo sang ngày mới → CLOSE khi rollover ----
def test_no_overnight_rollover_close():
    bars = asia(0) + [
        c(0, 8, 100, 100, 98, 98.5),
        c(0, 9, 98.5, 99.5, 97, 97.5),
        c(0, 10, 98, 101, 98, 100.5),      # BUY
    ] + [c(0, h, 100, 100.5, 99.5, 100) for h in range(11, 23)] + [
        c(1, 1, 100, 100.5, 99.5, 100),    # sang ngày mới → đóng lệnh treo
    ]
    a = acts(replay(IctPo3({**MECH, "confluence": 1, "flatten_h": 23}), bars))
    assert a == ["BUY", "CLOSE"]


# ---- Tối đa 1 lệnh/ngày ----
def test_max_one_trade_per_day():
    bars = asia(0) + [
        c(0, 8, 100, 100, 98, 98.5),
        c(0, 9, 98.5, 99.5, 97, 97.5),
        c(0, 10, 98, 101, 98, 100.5),      # BUY
        c(0, 11, 100.5, 108.5, 100.5, 108),  # CLOSE (TP)
        c(0, 12, 100, 100, 96, 97),        # setup khác — phải bị bỏ qua
        c(0, 13, 97, 102, 97, 101),
        c(0, 14, 101, 103, 101, 102),
    ]
    a = acts(replay(IctPo3({**MECH, "confluence": 1}), bars))
    assert a.count("BUY") == 1


# ---- Confluence: cùng kịch bản MSS nhưng KHÔNG có FVG ----
NOGAP = [
    c(0, 8, 100, 99.5, 98, 98.5),
    c(0, 9, 98.5, 99, 97.5, 98),
    c(0, 10, 98, 99, 98, 98.8),
    c(0, 11, 99, 101, 99, 101),            # MSS có, nhưng không có FVG (low 99 ≤ high 99)
]


def test_confluence_1_enters_without_fvg():
    a = acts(replay(IctPo3({**MECH, "confluence": 1}), asia(0) + NOGAP))
    assert "BUY" in a


def test_confluence_2_blocks_without_fvg():
    a = acts(replay(IctPo3({**MECH, "confluence": 2}), asia(0) + NOGAP))
    assert "BUY" not in a


# conf≥2: vũ trang tại MSS (có FVG), CHỜ giá retest về FVG mới vào.
RETEST = [
    c(0, 8, 100, 100, 98, 98.5),        # sweep low (ext=98)
    c(0, 9, 98.5, 99, 97.5, 98),        # since=1
    c(0, 10, 98, 103, 100.5, 102.5),    # MSS + bullish FVG (low 100.5 > high 100 hour8) → vũ trang, prox=100.5
    c(0, 11, 102.5, 102.5, 100, 101),   # giá hồi vào FVG (low 100 ≤ 100.5) → VÀO LONG tại 101
    c(0, 12, 101, 108.5, 101, 108.2),   # chạm TP
]


def test_confluence_2_arms_then_enters_on_retest():
    sigs = replay(IctPo3({**MECH, "confluence": 2}), asia(0) + RETEST)
    a = acts(sigs)
    assert a == ["BUY", "CLOSE"]
    # entry tại retest (close hour11 = 101) thấp hơn breakout (close hour10 = 102.5) → gần SL hơn.
    buy = next(s for s in sigs if s.action == "BUY")
    assert buy.sl < 101 < buy.tp


def test_confluence_2_no_retest_no_entry():
    # MSS+FVG vũ trang nhưng giá KHÔNG hồi về FVG (chạy thẳng) → không vào.
    norebound = asia(0) + RETEST[:3] + [
        c(0, 11, 102.5, 105, 102, 104),   # low 102 > prox 100.5 → chưa retest
        c(0, 12, 104, 106, 103, 105),
    ]
    a = acts(replay(IctPo3({**MECH, "confluence": 2}), norebound))
    assert "BUY" not in a


def test_confluence_2_invalidate_on_break_sweep():
    # Sau khi vũ trang, giá phá sâu hơn điểm quét → huỷ setup, không vào.
    invalid = asia(0) + RETEST[:3] + [
        c(0, 11, 102, 102, 97, 97.2),     # low 97 < sweep_extreme 98 → invalidate
    ]
    a = acts(replay(IctPo3({**MECH, "confluence": 2}), invalid))
    assert "BUY" not in a


# ---- tp_mode=1: TP về thanh khoản đối diện (Asia High cho long) ----
def test_tp_mode_opposite_liquidity():
    bars = asia(0) + [
        c(0, 8, 100, 100, 98, 98.5),
        c(0, 9, 98.5, 99, 97.5, 98),
        c(0, 10, 98, 103, 100.5, 102.5),   # MSS + FVG, prox=100.5
        c(0, 11, 102.5, 102.5, 100, 100.2),  # retest, entry 100.2 < Asia High 101
    ]
    sigs = replay(IctPo3({**MECH, "confluence": 2, "tp_mode": 1}), bars)
    buy = next(s for s in sigs if s.action == "BUY")
    assert buy.tp == 101.0  # = Asia High (đỉnh range), không phải rr cố định


# ---- Không vào lệnh trong phiên Asia ----
def test_no_signal_during_asia():
    sigs = replay(IctPo3(MECH), asia(0))
    assert sigs == []


# ---- plot: Asia High/Low có giá trị sau khi phiên Asia hình thành ----
def test_plot_asia_levels():
    s = IctPo3({"bias_mode": 0})
    bars = asia(0) + [c(0, 10, 100, 101, 99, 100)]
    p = s.plot(bars)
    assert set(p) == {"Asia High", "Asia Low"}
    assert p["Asia High"][-1] == 101.0 and p["Asia Low"][-1] == 99.0


# ---- Bias HTF: chỉ đánh thuận trend (đối chiếu blog ICT PO3) ----
LONG_SETUP = [
    c(0, 8, 100, 100, 98, 98.5),
    c(0, 9, 98.5, 99.5, 97, 97.5),
    c(0, 10, 98, 101, 98, 100.5),  # MSS long, entry 100.5
]


def test_bias_allows_long_in_uptrend():
    # EMA bias thấp hơn giá (trend tăng) → cho phép LONG.
    bars = trend_prior(80) + asia(0) + LONG_SETUP
    a = acts(replay(IctPo3({"bias_mode": 1, "bias_len": 10, "mss_lookback": 2,
                            "confluence": 1, "size": 1}), bars))
    assert "BUY" in a


def test_bias_blocks_long_in_downtrend():
    # EMA bias cao hơn giá (trend giảm) → CHẶN LONG (không đánh ngược trend).
    bars = trend_prior(140) + asia(0) + LONG_SETUP
    a = acts(replay(IctPo3({"bias_mode": 1, "bias_len": 10, "mss_lookback": 2,
                            "confluence": 1, "size": 1}), bars))
    assert "BUY" not in a


# ---- Lọc tin (NFP / khung giờ tin) ----
def test_news_blocked_window():
    tue = datetime(2025, 1, 7, 12, tzinfo=timezone.utc)  # thứ Ba
    p = {"news_filter": 1, "news_start_h": 12, "news_end_h": 14}
    assert IctPo3._news_blocked(tue, 12, p) is True   # trong khung giờ tin
    assert IctPo3._news_blocked(tue, 15, p) is False  # ngoài khung
    assert IctPo3._news_blocked(tue, 12, {"news_filter": 0}) is False  # tắt


def test_news_blocked_nfp_day():
    fri = datetime(2025, 1, 3, 16, tzinfo=timezone.utc)  # thứ Sáu đầu tháng 1/2025 = NFP
    base = {"news_start_h": 12, "news_end_h": 14}
    assert IctPo3._news_blocked(fri, 16, {**base, "news_filter": 2}) is True   # chặn ngày NFP
    assert IctPo3._news_blocked(fri, 16, {**base, "news_filter": 1}) is False  # chỉ-khung-giờ, ngoài giờ


def test_news_filter_blocks_entry():
    # khung giờ tin phủ nến vào lệnh (10–13h) → không vào.
    bars = asia(0) + RETEST
    pr = {**MECH, "confluence": 2, "news_filter": 1, "news_start_h": 10, "news_end_h": 13}
    assert "BUY" not in acts(replay(IctPo3(pr), bars))


# ---- registry ----
def test_registered():
    discover()
    assert "ict_po3" in {c.name for c in all_strategies()}
