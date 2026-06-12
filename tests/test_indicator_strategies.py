"""TA (psar/adx_dmi/stochastic_k) + strategies psar/adx/stoch/keltner."""

from app.strategy.base import Context
from app.strategy.registry import all_strategies, discover
from app.strategy.strategies.keltner import KeltnerBreakout
from app.strategy.strategies.parabolic_sar import ParabolicSar
from app.strategy.strategies.stochastic import Stochastic
from app.strategy.ta import adx_dmi, psar, stochastic_k


def candle(c, h=None, low=None):
    return {"ts": 0, "open": c, "high": h if h else c + 0.5,
            "low": low if low else c - 0.5, "close": c, "volume": 1}


def replay(strat, closes):
    out, bars = [], []
    for c in closes:
        bars.append(candle(c))
        out.extend(strat.on_candle(Context("X", c, list(bars), None)))
    return [s.action for s in out]


# ---- TA ----
def test_psar_uptrend_down():
    up = [candle(float(i)) for i in range(1, 40)]
    down = [candle(float(i)) for i in range(40, 1, -1)]
    assert psar(up)[-1] == 1
    assert psar(down)[-1] == -1


def test_adx_dmi_uptrend_plus_over_minus():
    up = [candle(float(i)) for i in range(1, 60)]
    d = adx_dmi(up, 14)
    assert d is not None
    assert d["plus_di_now"] > d["minus_di_now"]  # uptrend: +DI > -DI
    assert d["adx"] > 0


def test_adx_dmi_insufficient():
    assert adx_dmi([candle(10) for _ in range(10)], 14) is None


def test_stochastic_k_bounds():
    cs = [candle(float(i)) for i in range(1, 20)]  # uptrend → close gần đỉnh → %K cao
    k = stochastic_k(cs, 14)
    assert k is not None and 0 <= k <= 100 and k > 70


# ---- psar strategy ----
def test_psar_strategy_flips():
    s = ParabolicSar({"size": 1})
    actions = replay(s, [float(c) for c in list(range(1, 40)) + list(range(39, 1, -1))])
    assert "SELL" in actions  # có lúc đảo xuống


# ---- stochastic strategy ----
def test_stoch_buy_when_oversold():
    s = Stochastic({"period": 5, "oversold": 20, "overbought": 80, "size": 1})
    actions = replay(s, [float(c) for c in range(20, 5, -1)])  # giảm liên tục → %K thấp
    assert "BUY" in actions


# ---- keltner strategy ----
def test_keltner_buy_on_breakout():
    s = KeltnerBreakout({"period": 10, "mult": 1.0, "size": 1})
    # giá đi ngang rồi vọt lên → vượt dải trên
    closes = [100.0] * 20 + [130.0]
    bars = [candle(c) for c in closes]
    sigs = s.on_candle(Context("X", 130.0, bars, None))
    assert [x.action for x in sigs] == ["BUY"]


# ---- registry ----
def test_all_four_registered():
    discover()
    names = {c.name for c in all_strategies()}
    assert {"psar", "adx", "stoch", "keltner"} <= names
