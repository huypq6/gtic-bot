"""Donchian Breakout — on_candle logic + đăng ký + backtest mẫu."""

import pytest

from app.strategy.base import Context
from app.strategy.registry import all_strategies, discover, get
from app.strategy.strategies.donchian import DonchianBreakout


def candle(c):
    return {"ts": 0, "open": c, "high": c + 0.5, "low": c - 0.5, "close": c, "volume": 1}


def ctx(price, closes):
    bars = [candle(c) for c in closes]
    return Context(symbol="BTCUSDT", price=price, candles=bars, position=None)


def test_breakout_up_buys():
    s = DonchianBreakout({"period": 3, "size": 1})
    sigs = s.on_candle(ctx(12.0, [10, 10, 10, 10]))  # giá > đỉnh 3 nến trước (high=10.5)
    assert [x.action for x in sigs] == ["BUY"]
    assert sigs[0].size == 1


def test_breakdown_sells():
    s = DonchianBreakout({"period": 3, "size": 1})
    assert [x.action for x in s.on_candle(ctx(8.0, [10, 10, 10, 10]))] == ["SELL"]


def test_inside_channel_no_signal():
    s = DonchianBreakout({"period": 3})
    assert s.on_candle(ctx(10.0, [10, 10, 10, 10])) == []


def test_insufficient_data():
    s = DonchianBreakout({"period": 20})
    assert s.on_candle(ctx(10.0, [10, 11])) == []


def test_sl_tp_pct_attached():
    s = DonchianBreakout({"period": 3, "size": 1, "sl_pct": 2, "tp_pct": 4})
    sig = s.on_candle(ctx(100.0, [10, 10, 10, 10]))[0]
    assert sig.action == "BUY"
    assert sig.sl == pytest.approx(98.0)  # -2%
    assert sig.tp == pytest.approx(104.0)  # +4%


def test_registered_in_registry():
    discover()
    assert "donchian" in {c.name for c in all_strategies()}
    assert get("donchian", "1") is DonchianBreakout


# ---- backtest mẫu (skip nếu chưa cài extra backtest) ----
def test_donchian_backtest_sample():
    pytest.importorskip("vectorbt")
    from app.backtest.engine import run_backtest

    # chuỗi giá có breakout lên rồi xuống → có lệnh
    prices = [10] * 25 + [11, 12, 13, 14, 15, 14, 13, 12, 11, 10, 9, 8, 7]
    candles = [
        {"ts": i * 60000, "open": p, "high": p + 0.3, "low": p - 0.3,
         "close": float(p), "volume": 1}
        for i, p in enumerate(prices)
    ]
    res = run_backtest("donchian", "1", {"period": 10, "size": 1}, candles, tf="1m")
    assert "pnl_pct" in res
    assert isinstance(res["n_trades"], int)
    assert isinstance(res["equity_curve"], list)
