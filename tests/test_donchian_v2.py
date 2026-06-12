"""Donchian v2: breakout kênh + ATR trailing (chandelier) + exit kênh ngược + lọc ADX/cuối tuần."""

from datetime import datetime, timedelta, timezone

from app.strategy.base import Context
from app.strategy.strategies.donchian_v2 import DonchianV2

BASE = datetime(2025, 1, 6, tzinfo=timezone.utc)  # thứ Hai


def ts(day: int, hour: int) -> int:
    return int((BASE + timedelta(days=day, hours=hour)).timestamp() * 1000)


def c(day, hour, o, h, low, cl, v=1.0):
    return {"ts": ts(day, hour), "open": o, "high": h, "low": low, "close": cl,
            "volume": v, "symbol": "X"}


def flat(n, level=100.0, day=0, h0=0, amp=0.5):
    """n nến đi ngang quanh level (high=+amp, low=−amp)."""
    return [c(day + (h0 + i) // 24, (h0 + i) % 24, level, level + amp, level - amp, level)
            for i in range(n)]


def replay(strat, bars):
    out, acc = [], []
    for b in bars:
        acc.append(b)
        out.extend(strat.on_candle(Context("X", b["close"], list(acc), None)))
    return out


def acts(sigs):
    return [s.action for s in sigs]


MECH = {"period": 10, "exit_period": 5, "exit_mode": 2, "atr_len": 5, "atr_mult": 2.0,
        "adx_min": 0, "dow_filter": 0, "size": 1}


def test_long_breakout_entry():
    bars = flat(12) + [c(0, 12, 100, 103, 100, 102.5)]  # close 102.5 > đỉnh kênh 100.5
    sigs = replay(DonchianV2(MECH), bars)
    assert acts(sigs) == ["BUY"]


def test_short_breakout_entry():
    bars = flat(12) + [c(0, 12, 100, 100, 97, 97.5)]  # close 97.5 < đáy kênh 99.5
    sigs = replay(DonchianV2(MECH), bars)
    assert acts(sigs) == ["SELL"]


def test_atr_trail_exit_after_rise():
    bars = flat(12) + [
        c(0, 12, 100, 103, 100, 102.5),    # BUY
        c(0, 13, 102.5, 110, 102.5, 109.5),  # đẩy cao → trail nâng theo (ext=109.5)
        c(0, 14, 109.5, 110, 104, 104.5),    # ATR≈3.3 → trail≈106.2 > 104.5 → CLOSE
    ]
    sigs = replay(DonchianV2({**MECH, "exit_mode": 0, "atr_mult": 1.0}), bars)
    assert acts(sigs) == ["BUY", "CLOSE"]


def test_opposite_channel_exit():
    # đáy kênh chính (10 nến) = 97 (nến h6 nhúng sâu) — close 99.2 KHÔNG đảo chiều,
    # nhưng thủng đáy kênh-thoát 5 nến (= 99.5) → CLOSE.
    bars = flat(12)
    bars[6] = c(0, 6, 100, 100.5, 97, 100)
    bars += [
        c(0, 12, 100, 103, 100, 102.5),      # BUY
        c(0, 13, 102.5, 103, 102, 102.5),
        c(0, 14, 102.5, 102.5, 99, 99.2),    # thủng đáy 5-nến → CLOSE
    ]
    sigs = replay(DonchianV2({**MECH, "exit_mode": 1, "atr_mult": 99}), bars)
    assert acts(sigs) == ["BUY", "CLOSE"]


def test_reversal_long_to_short():
    bars = flat(12) + [
        c(0, 12, 100, 103, 100, 102.5),   # BUY
        c(0, 13, 102.5, 102.5, 95, 95.5),  # thủng đáy kênh 10-nến → SELL (đảo chiều)
    ]
    sigs = replay(DonchianV2({**MECH, "exit_mode": 0, "atr_mult": 99}), bars)
    assert acts(sigs) == ["BUY", "SELL"]


def test_adx_filter_blocks_entry():
    bars = flat(30) + [c(1, 6, 100, 103, 100, 102.5)]
    sigs = replay(DonchianV2({**MECH, "adx_min": 99}), bars)
    assert sigs == []


def test_weekend_filter_blocks_saturday_entry():
    # ngày 5 từ BASE (thứ Hai) = thứ Bảy.
    bars = flat(12, day=5) + [c(5, 12, 100, 103, 100, 102.5)]
    sigs = replay(DonchianV2({**MECH, "dow_filter": 1}), bars)
    assert sigs == []


def test_weekend_filter_off_allows_saturday():
    bars = flat(12, day=5) + [c(5, 12, 100, 103, 100, 102.5)]
    sigs = replay(DonchianV2(MECH), bars)
    assert acts(sigs) == ["BUY"]
