"""Backtest engine — dùng chung on_candle, metrics qua vectorbt.

Skip nếu chưa cài extra backtest (vectorbt). Strategy 'always buy first candle'
để có trade xác định.
"""

import pytest

vbt = pytest.importorskip("vectorbt")  # noqa: F841

from app.backtest.engine import run_backtest  # noqa: E402


def _candles(prices):
    return [
        {"ts": 1700000000000 + i * 60000, "open": p, "high": p, "low": p, "close": p, "volume": 1}
        for i, p in enumerate(prices)
    ]


def test_ema_cross_backtest_runs_and_returns_metrics():
    # giá có xu hướng lên rồi xuống → có giao cắt EMA → có trade
    prices = [10, 10, 10, 10, 9, 8, 7, 8, 9, 10, 11, 12, 13, 14, 15, 14, 13, 12, 11, 10]
    res = run_backtest(
        "ema_cross", "1", {"fast": 3, "slow": 6, "size": 1},
        _candles(prices), capital=1000, fee_rate=0.001, tf="1m",
    )
    assert "pnl_pct" in res
    assert isinstance(res["n_trades"], int)
    assert isinstance(res["equity_curve"], list)
    assert len(res["equity_curve"]) >= 1
    assert isinstance(res["trades"], list)


def test_backtest_too_short_raises():
    with pytest.raises(ValueError):
        run_backtest("ema_cross", "1", {}, _candles([10, 11]), tf="1m")
