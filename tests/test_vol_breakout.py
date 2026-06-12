"""Volatility Breakout (Larry Williams k-range): vào khi giá vượt open_ngày + k×range_hôm_qua,
thoát đầu ngày kế tiếp; SL tùy chọn; lọc trend EMA; 1 lệnh/ngày/chiều."""

from datetime import datetime, timedelta, timezone

from app.strategy.base import Context
from app.strategy.strategies.vol_breakout import VolBreakout

BASE = datetime(2025, 1, 6, tzinfo=timezone.utc)  # thứ Hai


def ts(day: int, hour: int) -> int:
    return int((BASE + timedelta(days=day, hours=hour)).timestamp() * 1000)


def c(day, hour, o, h, low, cl, v=1.0):
    return {"ts": ts(day, hour), "open": o, "high": h, "low": low, "close": cl,
            "volume": v, "symbol": "X"}


def flat_day(day, level=100.0, hi=102.0, lo=98.0):
    """24 nến 1h đi ngang tại level; nến đầu đặt high/low ngày = [lo, hi] (range = hi-lo)."""
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


# range hôm trước = 102-98 = 4; k=0.5 → mức LONG = open_ngày + 2, SHORT = open_ngày − 2.
MECH = {"k": 0.5, "direction": 1, "trend_len": 0, "sl_mode": 0, "size": 1}


def test_long_breakout_and_exit_next_day_open():
    bars = flat_day(0) + [
        c(1, 0, 100, 100.5, 99.5, 100),   # open ngày 1 = 100 → mức LONG = 102
        c(1, 1, 100, 101.9, 100, 101.5),  # chưa vượt 102 → chưa vào
        c(1, 2, 101.5, 103, 101.5, 102.8),  # close 102.8 > 102 → BUY
        c(1, 3, 102.8, 104, 102.5, 103.5),  # giữ
        c(2, 0, 103.5, 104, 103, 103.8),  # đầu ngày 2 → CLOSE
    ]
    sigs = replay(VolBreakout(MECH), bars)
    assert acts(sigs) == ["BUY", "CLOSE"]


def test_no_entry_without_breakout():
    bars = flat_day(0) + [c(1, h, 100, 101.5, 99, 100) for h in range(0, 24)]
    sigs = replay(VolBreakout(MECH), bars)
    assert sigs == []


def test_short_breakout_when_direction_both():
    bars = flat_day(0) + [
        c(1, 0, 100, 100.5, 99.5, 100),    # mức SHORT = 98
        c(1, 1, 100, 100, 97.5, 97.8),     # close 97.8 < 98 → SELL
        c(2, 0, 97.8, 98, 97, 97.5),       # đầu ngày 2 → CLOSE
    ]
    sigs = replay(VolBreakout(MECH), bars)
    assert acts(sigs) == ["SELL", "CLOSE"]


def test_long_only_ignores_short():
    bars = flat_day(0) + [
        c(1, 0, 100, 100.5, 99.5, 100),
        c(1, 1, 100, 100, 97.5, 97.8),     # thủng mức short nhưng direction=0
    ]
    sigs = replay(VolBreakout({**MECH, "direction": 0}), bars)
    assert sigs == []


def test_one_entry_per_day():
    bars = flat_day(0) + [
        c(1, 0, 100, 100.5, 99.5, 100),
        c(1, 1, 100, 103, 100, 102.8),     # BUY
        c(1, 2, 102.8, 103, 100, 100.2),   # rơi lại — không SL (sl_mode=0), vẫn giữ
        c(1, 3, 100.2, 103.5, 100, 103.2),  # vượt lại mức 102 — KHÔNG vào thêm
        c(2, 0, 103.2, 103.5, 103, 103.3),  # CLOSE đầu ngày
    ]
    sigs = replay(VolBreakout(MECH), bars)
    assert acts(sigs) == ["BUY", "CLOSE"]


def test_sl_day_open_cuts_loss():
    bars = flat_day(0) + [
        c(1, 0, 100, 100.5, 99.5, 100),
        c(1, 1, 100, 103, 100, 102.8),      # BUY, SL = day_open = 100
        c(1, 2, 102.8, 102.8, 99, 99.5),    # close 99.5 < 100 → CLOSE (SL)
        c(1, 3, 99.5, 103.5, 99.5, 103.2),  # sau SL không re-entry trong ngày
    ]
    sigs = replay(VolBreakout({**MECH, "sl_mode": 1}), bars)
    assert acts(sigs) == ["BUY", "CLOSE"]


def test_trend_filter_blocks_counter_trend_long():
    # giá đi ngang 100 rất lâu rồi sụt còn 90 → close < EMA dài → chặn LONG.
    prior = []
    for d in range(-8, 0):
        prior += flat_day(d)
    bars = prior + [
        c(1, 0, 90, 90.5, 89.5, 90),       # open ngày = 90, range hôm trước = 4 → mức LONG = 92
        c(1, 1, 90, 93, 90, 92.8),         # vượt 92 nhưng close 92.8 < EMA(~100) → chặn
    ]
    sigs = replay(VolBreakout({**MECH, "trend_len": 100, "direction": 0}), bars)
    assert sigs == []


def test_sl_pct_caps_loss():
    bars = flat_day(0) + [
        c(1, 0, 100, 100.5, 99.5, 100),
        c(1, 1, 100, 103, 100, 102.8),       # BUY tại 102.8, SL% = 102.8×0.975 ≈ 100.23
        c(1, 2, 102.8, 102.8, 100, 100.1),   # close 100.1 < 100.23 → CLOSE (SL)
        c(1, 3, 100.1, 103.5, 100, 103.2),   # không re-entry trong ngày
    ]
    sigs = replay(VolBreakout({**MECH, "sl_mode": 3, "sl_pct": 2.5}), bars)
    assert acts(sigs) == ["BUY", "CLOSE"]


def trend_day(day):
    """Ngày trend sạch: open 100 → close 103.9, range [99.9, 104] → noise ≈ 0.05."""
    bars = [c(day, 0, 100, 104, 99.9, 103.9)]
    bars += [c(day, h, 103.9, 104, 103.5, 103.9) for h in range(1, 24)]
    return bars


def test_noise_k_blocks_breakout_after_doji_days():
    # 6 ngày doji (noise=1 → k kẹp 0.9): mức LONG = open + 0.9×4 = 103.6 → close 102.8 KHÔNG vào.
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
    # 6 ngày trend (noise≈0.05 → k kẹp 0.3): mức LONG = 103.9 + 0.3×4.1 ≈ 105.13 → close 105.5 vào.
    bars = []
    for d in range(6):
        bars += trend_day(d)
    bars += [
        c(6, 0, 103.9, 104, 103.8, 103.9),
        c(6, 1, 103.9, 105.6, 103.9, 105.5),
    ]
    sigs = replay(VolBreakout({**MECH, "k_mode": 1, "noise_len": 20}), bars)
    # ngày 5 (đủ 5 ngày noise) tự breakout → BUY + CLOSE đầu ngày 6; rồi BUY ngày 6.
    assert acts(sigs) == ["BUY", "CLOSE", "BUY"]


def lose_long_day(day):
    """Ngày thua chiều LONG: breakout lên rồi rơi — đóng đầu ngày sau thấp hơn entry ~3.7%.

    Range ngày giữ [99,103] (=4) để ngày sau vẫn có mức breakout tương tự.
    """
    bars = [c(day, 0, 100, 100.5, 99.5, 100)]            # open ngày = 100, mức LONG = 102
    bars += [c(day, 1, 100, 103, 100, 102.8)]            # BUY 102.8
    bars += [c(day, h, 99, 99.2, 99.0, 99) for h in range(2, 24)]  # rơi về 99
    return bars


def test_circuit_breaker_pauses_after_losses():
    # cb_thresh=5: 2 lệnh thua (~−3.8% mỗi lệnh) → kích → ngày 3 breakout nhưng KHÔNG vào.
    bars = flat_day(0, hi=103, lo=99) + lose_long_day(1) + lose_long_day(2) + lose_long_day(3)
    p = {**MECH, "cb_thresh_pct": 5.0, "cb_window_d": 30, "cb_pause_d": 14}
    sigs = replay(VolBreakout(p), bars)
    # ngày 1: BUY+CLOSE(đầu ngày 2); ngày 2: BUY+CLOSE(đầu ngày 3, kích CB); ngày 3: im lặng.
    assert acts(sigs) == ["BUY", "CLOSE", "BUY", "CLOSE"]


def test_circuit_breaker_resumes_after_pause():
    bars = flat_day(0, hi=103, lo=99) + lose_long_day(1) + lose_long_day(2)
    # 14 ngày nghỉ (flat, không breakout) rồi 1 ngày breakout — phải vào lại.
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
    sigs = replay(VolBreakout(MECH), bars)  # cb tắt → ngày 3 vẫn vào (chưa có ngày 4 để đóng)
    assert acts(sigs) == ["BUY", "CLOSE", "BUY", "CLOSE", "BUY"]


def test_needs_prev_day_range():
    bars = [c(0, h, 100, 102, 98, 100) for h in range(3)]  # chưa có ngày hôm trước
    sigs = replay(VolBreakout(MECH), bars)
    assert sigs == []
