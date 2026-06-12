"""Ichimoku v2 — vào lệnh theo cross + ATR trailing stop cắt khi giá đảo."""

from app.strategy.base import Context
from app.strategy.registry import all_strategies, discover
from app.strategy.strategies.ichimoku_v2 import IchimokuTrail


def c(i, px):
    return {"ts": i * 900_000, "open": px, "high": px + 0.5, "low": px - 0.5,
            "close": px, "volume": 1.0, "symbol": "X"}


def replay(strat, prices):
    out, acc = [], []
    for i, px in enumerate(prices):
        acc.append(c(i, float(px)))
        out.extend(strat.on_candle(Context("X", float(px), list(acc), None)))
    return [s.action for s in out]


def test_long_then_trailing_stop_exit():
    s = IchimokuTrail({"conv": 2, "base": 5, "span_b": 10, "atr_len": 5, "atr_mult": 2.0, "size": 1})
    # đi ngang (nền + mây ~20), bứt phá lên (cross up + trên mây → BUY), rồi rớt mạnh → trailing stop cắt.
    prices = [20.0] * 20 + list(range(20, 40)) + [38, 32, 24]
    a = replay(s, prices)
    assert "BUY" in a and "CLOSE" in a
    assert a.index("BUY") < len(a) - 1 - a[::-1].index("CLOSE")  # có CLOSE sau BUY


def test_no_signal_until_enough_candles():
    s = IchimokuTrail({"conv": 2, "base": 5, "span_b": 10, "atr_len": 5, "size": 1})
    a = replay(s, list(range(1, 10)))  # < span_b+shift+1 → ichimoku None
    assert a == []


def test_v2_registered():
    discover()
    vs = {(c.name, c.version) for c in all_strategies()}
    assert ("ichimoku", "1") in vs and ("ichimoku", "2") in vs
