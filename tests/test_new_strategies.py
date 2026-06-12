"""TA helpers (sma/stdev/macd/supertrend) + strategies bollinger/macd/supertrend."""

from app.strategy.base import Context
from app.strategy.registry import all_strategies, discover
from app.strategy.strategies.bollinger import BollingerReversion
from app.strategy.strategies.macd_cross import MacdCross
from app.strategy.strategies.supertrend import Supertrend
from app.strategy.ta import macd, sma, stdev, supertrend


def candle(c):
    return {"ts": 0, "open": c, "high": c + 0.5, "low": c - 0.5, "close": c, "volume": 1}


def replay(strat, closes):
    out, bars = [], []
    for c in closes:
        bars.append(candle(c))
        out.extend(strat.on_candle(Context("X", c, list(bars), None)))
    return [s.action for s in out]


# ---- TA ----
def test_sma_stdev():
    assert sma([1, 2, 3, 4], 4) == 2.5
    assert stdev([2, 2, 2], 3) == 0.0
    assert stdev([1, 3], 2) == 1.0  # mean 2, var 1


def test_macd_aligned():
    closes = [float(i) for i in range(60)]
    m, s = macd(closes, 12, 26, 9)
    assert len(m) == len(s) and len(s) > 0


def test_supertrend_uptrend_down():
    up = [candle(c) for c in range(1, 60)]
    down = [candle(c) for c in range(60, 1, -1)]
    assert supertrend(up, 10, 3)[-1] == 1
    assert supertrend(down, 10, 3)[-1] == -1


# ---- bollinger ----
def test_bollinger_buy_below_lower():
    s = BollingerReversion({"period": 10, "mult": 2, "size": 1})
    closes = [99, 101] * 10  # mid≈100, sd≈1 → lower≈98
    bars = [candle(c) for c in closes]
    sigs = s.on_candle(Context("X", 95.0, bars, None))  # price << lower
    assert [x.action for x in sigs] == ["BUY"]


def test_bollinger_sell_above_upper():
    s = BollingerReversion({"period": 10, "mult": 2, "size": 1})
    bars = [candle(c) for c in [99, 101] * 10]
    assert [x.action for x in s.on_candle(Context("X", 105.0, bars, None))] == ["SELL"]


# ---- macd ----
def test_macd_cross_signals_on_trend_reversal():
    s = MacdCross({"fast": 3, "slow": 6, "signal": 3, "size": 1})
    closes = [10] * 10 + list(range(10, 30)) + list(range(30, 5, -1))
    actions = replay(s, [float(c) for c in closes])
    assert "BUY" in actions and "SELL" in actions


# ---- supertrend ----
def test_supertrend_strategy_flips():
    s = Supertrend({"period": 5, "mult": 2, "size": 1})
    closes = list(range(1, 40)) + list(range(39, 1, -1))  # lên rồi xuống
    actions = replay(s, [float(c) for c in closes])
    assert "SELL" in actions  # có lúc đảo xuống


# ---- registry ----
def test_all_registered():
    discover()
    names = {c.name for c in all_strategies()}
    assert {"bollinger", "macd", "supertrend"} <= names
