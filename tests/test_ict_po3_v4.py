"""ict_po3 v4 — rejection sweep, displacement MSS, entry cutoff, min R:R."""

from app.strategy.base import Context
from app.strategy.registry import all_strategies, discover
from app.strategy.strategies.ict_po3_v4 import IctPo3V4
from tests.test_ict_po3 import LONG_BRK, acts, asia, c, replay

# Cơ chế thuần: tắt bias/news/displacement/min_rr, SL điểm quét, cutoff muộn.
MECH4 = {"bias_mode": 0, "news_filter": 0, "sl_mode": 0, "mss_lookback": 2, "swing": 1,
         "disp_mult": 0.0, "min_rr": 0.0, "entry_cutoff_h": 21, "size": 1}

# LONG hợp lệ kiểu v4: sweep low ĐÓNG NGƯỢC vào range (rejection) rồi MSS.
LONG_REJ = [
    c(0, 8, 99.5, 99.5, 98, 99.3),     # quét dưới Asia Low (98<99) NHƯNG close 99.3 > 99 → rejection ✓
    c(0, 9, 99.3, 100.2, 98.8, 99.8),  # swing-high = 100.2
    c(0, 10, 99.8, 99.9, 99.0, 99.4),  # xác nhận swing (high thấp hơn)
    c(0, 11, 99.4, 101.2, 99.4, 100.8),  # MSS: close 100.8 > 100.2
]


# ---- 1. Rejection sweep ----
def test_reject_sweep_blocks_breakout():
    # LONG_BRK: nến quét ĐÓNG NGOÀI range (close 97.5 < asia_low 99) = breakout → v4 KHÔNG fade.
    a = acts(replay(IctPo3V4({**MECH4, "confluence": 1, "reject_sweep": 1}), asia(0) + LONG_BRK))
    assert "BUY" not in a


def test_reject_sweep_off_behaves_like_v3():
    a = acts(replay(IctPo3V4({**MECH4, "confluence": 1, "reject_sweep": 0}), asia(0) + LONG_BRK))
    assert "BUY" in a


def test_rejection_sweep_then_mss_enters():
    a = acts(replay(IctPo3V4({**MECH4, "confluence": 1, "reject_sweep": 1}), asia(0) + LONG_REJ))
    assert "BUY" in a


# ---- 2. Displacement MSS ----
def test_displacement_blocks_weak_mss():
    p = {**MECH4, "confluence": 1, "reject_sweep": 1, "disp_mult": 3.0, "atr_len": 5}
    a = acts(replay(IctPo3V4(p), asia(0) + LONG_REJ))  # thân nến MSS 1.4 < 3×ATR
    assert "BUY" not in a


def test_displacement_passes_strong_mss():
    p = {**MECH4, "confluence": 1, "reject_sweep": 1, "disp_mult": 0.3, "atr_len": 5}
    a = acts(replay(IctPo3V4(p), asia(0) + LONG_REJ))
    assert "BUY" in a


# ---- 3. Entry cutoff ----
def test_entry_cutoff_blocks_late_entry():
    p = {**MECH4, "confluence": 1, "reject_sweep": 1, "entry_cutoff_h": 10}
    a = acts(replay(IctPo3V4(p), asia(0) + LONG_REJ))  # MSS ở h11 ≥ cutoff 10 → bỏ
    assert "BUY" not in a


# ---- 4. min_rr (tp_mode=1) ----
def test_min_rr_skips_poor_rr():
    # entry ~100.8, Asia High 101 → TP cách 0.2; risk ATR ~1 → R:R << 1 → bỏ.
    p = {**MECH4, "confluence": 1, "reject_sweep": 1, "tp_mode": 1,
         "sl_mode": 1, "atr_len": 5, "atr_mult": 1.0, "min_rr": 1.0}
    a = acts(replay(IctPo3V4(p), asia(0) + LONG_REJ))
    assert "BUY" not in a


def test_min_rr_zero_allows_entry():
    p = {**MECH4, "confluence": 1, "reject_sweep": 1, "tp_mode": 1,
         "sl_mode": 1, "atr_len": 5, "atr_mult": 1.0, "min_rr": 0.0}
    a = acts(replay(IctPo3V4(p), asia(0) + LONG_REJ))
    assert "BUY" in a


# ---- registry ----
def test_v4_registered():
    discover()
    vs = {(s.name, s.version) for s in all_strategies()}
    assert ("ict_po3", "4") in vs


# ---- Parity live ↔ backtest: runner live đưa cửa sổ trượt (deque), backtest đưa list tăng dần.
# Bug cũ: neo sweep theo index tuyệt đối → với cửa sổ trượt không bao giờ thấy MSS → 0 lệnh live.
def _random_walk(seed: int, days: int = 60) -> list[dict]:
    import random

    r = random.Random(seed)
    t0 = 1_699_920_000_000  # 00:00 UTC
    p, out = 100.0, []
    for i in range(days * 96):
        o = p
        p *= 1 + r.gauss(0, 0.004)
        out.append({"ts": t0 + i * 900_000, "open": o, "close": p, "volume": 1.0,
                    "high": max(o, p) * (1 + abs(r.gauss(0, 0.002))),
                    "low": min(o, p) * (1 - abs(r.gauss(0, 0.002)))})
    return out


def _signals(strat, cs: list[dict], window: int | None) -> list[tuple]:
    out = []
    for i in range(len(cs)):
        win = cs[max(0, i - window + 1): i + 1] if window else cs[: i + 1]
        ctx = Context(symbol="X", price=cs[i]["close"], candles=win, position=None)
        # SL/TP làm tròn: ATR đệ quy trên cửa sổ khác nhau lệch ~1e-10
        out += [(cs[i]["ts"], s.action, round(s.sl or 0, 6), round(s.tp or 0, 6))
                for s in strat.on_candle(ctx)]
    return out


def test_sliding_window_matches_growing_list():
    from app.strategy.strategies.ict_po3 import IctPo3

    for cls in (IctPo3V4, IctPo3):
        cs = _random_walk(0)
        live = _signals(cls({"bias_mode": 0}), cs, window=300)
        bt = _signals(cls({"bias_mode": 0}), cs, window=None)
        assert any(a != "CLOSE" for _, a, _, _ in bt), cls
        assert live == bt, cls
