"""ATR + scanner analyze_symbol đề xuất SL/TP."""

from app.scanner.research import analyze_symbol
from app.strategy.ta import atr


def _c(h, low, close):
    return {"high": h, "low": low, "close": close}


def test_atr_basic():
    candles = [_c(10 + i, 9 + i, 9.5 + i) for i in range(20)]
    a = atr(candles, 14)
    assert a is not None
    assert a > 0


def test_atr_insufficient():
    assert atr([_c(10, 9, 9.5)], 14) is None


def test_analyze_buy_sets_sl_below_tp_above():
    # giá giảm dần → RSI thấp → BUY; entry = close cuối
    candles = [_c(c + 0.5, c - 0.5, float(c)) for c in range(40, 8, -1)]
    a = analyze_symbol(candles, rsi_period=14)
    assert a["signal"] == "BUY"
    assert a["entry"] is not None
    assert a["atr"] is not None
    assert a["sl"] < a["entry"] < a["tp"]  # long: SL dưới, TP trên


def test_analyze_sell_sets_sl_above_tp_below():
    candles = [_c(c + 0.5, c - 0.5, float(c)) for c in range(8, 40)]
    a = analyze_symbol(candles, rsi_period=14)
    assert a["signal"] == "SELL"
    assert a["tp"] < a["entry"] < a["sl"]  # short: SL trên, TP dưới


def test_analyze_neutral_no_sltp():
    # giá dao động đều lên/xuống → RSI ~50 → NEUTRAL
    closes = [10.0 if i % 2 == 0 else 11.0 for i in range(40)]
    candles = [_c(c + 0.2, c - 0.2, c) for c in closes]
    a = analyze_symbol(candles)
    assert a["signal"] == "NEUTRAL"
    assert a["sl"] is None and a["tp"] is None
