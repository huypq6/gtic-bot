"""Chỉ báo kỹ thuật thuần (pure) cho strategy. Dùng được cả paper/backtest/live."""


def ema(values: list[float], period: int) -> list[float]:
    """EMA series, độ dài = len(values)-period+1 (rỗng nếu thiếu dữ liệu)."""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(values: list[float], period: int = 14) -> list[float]:
    """RSI (Wilder), độ dài = len(values)-period (rỗng nếu thiếu)."""
    if len(values) <= period:
        return []
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))

    def rsi_val(ag: float, al: float) -> float:
        if al == 0:
            return 100.0
        rs = ag / al
        return 100 - 100 / (1 + rs)

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out = [rsi_val(avg_gain, avg_loss)]
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out.append(rsi_val(avg_gain, avg_loss))
    return out
