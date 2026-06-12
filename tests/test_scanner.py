"""Scanner scoring — RSI/momentum → signal."""

from app.scanner.research import score_symbol


def test_oversold_gives_buy():
    closes = list(range(40, 10, -1))  # giảm liên tục → RSI thấp
    score, signal, reason = score_symbol([float(c) for c in closes], rsi_period=14)
    assert signal == "BUY"
    assert score > 0
    assert "RSI" in reason


def test_overbought_gives_sell():
    closes = [float(c) for c in range(10, 50)]  # tăng liên tục → RSI cao
    score, signal, _ = score_symbol(closes, rsi_period=14)
    assert signal == "SELL"
    assert score > 0


def test_insufficient_data_neutral():
    score, signal, reason = score_symbol([1.0, 2.0, 3.0])
    assert signal == "NEUTRAL"
    assert score == 0.0
    assert "thiếu" in reason


def test_score_capped_100():
    closes = [float(c) for c in range(100, 10, -1)]
    score, _, _ = score_symbol(closes, rsi_period=14)
    assert 0 <= score <= 100
