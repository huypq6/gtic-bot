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


def sma(values: list[float], period: int) -> float | None:
    """Simple moving average của `period` giá trị cuối."""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def stdev(values: list[float], period: int) -> float | None:
    """Độ lệch chuẩn (population) của `period` giá trị cuối."""
    if len(values) < period:
        return None
    window = values[-period:]
    mean = sum(window) / period
    var = sum((x - mean) ** 2 for x in window) / period
    return var**0.5


def macd(
    values: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float], list[float]]:
    """MACD: trả (macd_line, signal_line) đã căn đuôi cùng độ dài (rỗng nếu thiếu)."""
    ef, es = ema(values, fast), ema(values, slow)
    if not ef or not es:
        return [], []
    n = min(len(ef), len(es))
    macd_line = [ef[-n + i] - es[-n + i] for i in range(n)]
    sig = ema(macd_line, signal)
    if not sig:
        return macd_line, []
    return macd_line[-len(sig) :], sig


def supertrend(candles: list[dict], period: int = 10, mult: float = 3.0) -> list[int]:
    """Supertrend → list direction theo từng nến (1 = uptrend/long, -1 = downtrend/short).

    Độ dài = len(candles) - period (rỗng nếu thiếu). Dùng [-2],[-1] để bắt lúc đảo chiều.
    """
    if len(candles) < period + 1:
        return []
    trs = []
    for i in range(1, len(candles)):
        h, low = candles[i]["high"], candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))
    # Wilder ATR series, atr[j] ứng với nến index = period + j
    atr_series = [sum(trs[:period]) / period]
    for tr in trs[period:]:
        atr_series.append((atr_series[-1] * (period - 1) + tr) / period)

    directions: list[int] = []
    final_upper = final_lower = None
    st = None  # supertrend trước
    direction = 1
    for j, a in enumerate(atr_series):
        ci = period + j
        c = candles[ci]
        close = c["close"]
        hl2 = (c["high"] + c["low"]) / 2
        bu, bl = hl2 + mult * a, hl2 - mult * a
        prev_close = candles[ci - 1]["close"]
        if final_upper is None:
            final_upper, final_lower = bu, bl
        else:
            final_upper = bu if (bu < final_upper or prev_close > final_upper) else final_upper
            final_lower = bl if (bl > final_lower or prev_close < final_lower) else final_lower
        if st is None:
            direction = 1 if close > final_upper else -1
        elif direction == 1:
            direction = -1 if close < final_lower else 1
        else:
            direction = 1 if close > final_upper else -1
        st = final_lower if direction == 1 else final_upper
        directions.append(direction)
    return directions


def vwap(candles: list[dict], period: int) -> float | None:
    """Rolling VWAP (typical price (h+l+c)/3, trọng số volume) của `period` nến cuối."""
    if len(candles) < period:
        return None
    w = candles[-period:]
    tot_v = sum(c["volume"] for c in w)
    if tot_v == 0:
        return None
    return sum(((c["high"] + c["low"] + c["close"]) / 3) * c["volume"] for c in w) / tot_v


def _hl_mid(candles: list[dict], end: int, period: int) -> float:
    """(HH + LL) / 2 của `period` nến kết thúc tại index `end`."""
    w = candles[end - period + 1 : end + 1]
    return (max(c["high"] for c in w) + min(c["low"] for c in w)) / 2


def ichimoku(
    candles: list[dict], conv: int = 9, base: int = 26, span_b: int = 52, shift: int = 26
) -> dict | None:
    """Ichimoku — trả tenkan/kijun (2 điểm cuối) + đỉnh/đáy mây hiện tại. None nếu thiếu."""
    n = len(candles)
    if n < span_b + shift + 1:
        return None
    i = n - 1
    tenkan_prev = _hl_mid(candles, i - 1, conv)
    tenkan_now = _hl_mid(candles, i, conv)
    kijun_prev = _hl_mid(candles, i - 1, base)
    kijun_now = _hl_mid(candles, i, base)
    # Mây tại nến hiện tại = các span tính từ `shift` nến trước.
    j = i - shift
    span_a = (_hl_mid(candles, j, conv) + _hl_mid(candles, j, base)) / 2
    span_b_val = _hl_mid(candles, j, span_b)
    return {
        "tenkan_prev": tenkan_prev,
        "tenkan_now": tenkan_now,
        "kijun_prev": kijun_prev,
        "kijun_now": kijun_now,
        "cloud_top": max(span_a, span_b_val),
        "cloud_bottom": min(span_a, span_b_val),
    }


def atr(candles: list[dict], period: int = 14) -> float | None:
    """Average True Range (Wilder) — biến động giá. candles có high/low/close."""
    if len(candles) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(candles)):
        h, low = candles[i]["high"], candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        trs.append(max(h - low, abs(h - prev_close), abs(low - prev_close)))
    # Wilder smoothing
    a = sum(trs[:period]) / period
    for tr in trs[period:]:
        a = (a * (period - 1) + tr) / period
    return a


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
