"""TA helpers + strategy logic (ema_cross, rsi_rev) + registry discovery."""

from app.strategy.base import Context
from app.strategy.registry import all_strategies, discover, get
from app.strategy.strategies.ema_cross import EmaCross
from app.strategy.strategies.rsi_rev import RsiReversal
from app.strategy.ta import ema, rsi


def replay(strat, closes):
    """Phát lại chuỗi giá qua strategy như runner làm (ctx.candles lớn dần)."""
    out, candles = [], []
    for c in closes:
        candles.append({"open": c, "high": c, "low": c, "close": c, "volume": 1, "ts": 0})
        ctx = Context(symbol="BTCUSDT", price=c, candles=list(candles), position=None)
        out.extend(strat.on_candle(ctx))
    return out


# ---- TA ----
def test_ema_basic():
    series = ema([1, 2, 3, 4, 5], 3)
    assert len(series) == 3
    assert series[0] == 2.0  # SMA seed (1+2+3)/3


def test_rsi_all_gains_is_100():
    assert rsi([1, 2, 3, 4, 5, 6], 3)[-1] == 100.0


def test_rsi_all_losses_low():
    assert rsi([6, 5, 4, 3, 2, 1], 3)[-1] == 0.0


# ---- ema_cross ----
def test_ema_cross_buys_on_uptrend():
    strat = EmaCross({"fast": 3, "slow": 6, "size": 1})
    closes = [10, 10, 10, 10, 9, 8, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    actions = [s.action for s in replay(strat, closes)]
    assert "BUY" in actions


def test_ema_cross_sells_on_downtrend():
    strat = EmaCross({"fast": 3, "slow": 6, "size": 1})
    closes = [10, 10, 10, 10, 11, 12, 13, 12, 11, 10, 9, 8, 7, 6, 5]
    actions = [s.action for s in replay(strat, closes)]
    assert "SELL" in actions


def test_ema_cross_quiet_when_insufficient_data():
    strat = EmaCross({"fast": 3, "slow": 6, "size": 1})
    assert replay(strat, [10, 11]) == []


# ---- rsi_rev ----
def test_rsi_rev_buys_when_oversold():
    strat = RsiReversal({"period": 3, "oversold": 30, "overbought": 70, "size": 1})
    actions = [s.action for s in replay(strat, [10, 9, 8, 7, 6, 5, 4])]
    assert "BUY" in actions


def test_rsi_rev_sells_when_overbought():
    strat = RsiReversal({"period": 3, "oversold": 30, "overbought": 70, "size": 1})
    actions = [s.action for s in replay(strat, [4, 5, 6, 7, 8, 9, 10])]
    assert "SELL" in actions


# ---- registry ----
def test_discover_registers_samples():
    discover()
    names = {c.name for c in all_strategies()}
    assert {"ema_cross", "rsi_rev"} <= names
    assert get("ema_cross", "1") is EmaCross
