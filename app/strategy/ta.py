"""Pure technical indicators for strategies. Usable in paper/backtest/live alike."""


def pad_left(series: list[float], n: int) -> list[float | None]:
    """Left-pad a series to length n with None (for indicator warmup)."""
    return [None] * max(0, n - len(series)) + list(series)


def ema(values: list[float], period: int) -> list[float]:
    """EMA series, length = len(values)-period+1 (empty if not enough data)."""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def sma(values: list[float], period: int) -> float | None:
    """Simple moving average of the last `period` values."""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def stdev(values: list[float], period: int) -> float | None:
    """Standard deviation (population) of the last `period` values."""
    if len(values) < period:
        return None
    window = values[-period:]
    mean = sum(window) / period
    var = sum((x - mean) ** 2 for x in window) / period
    return var**0.5


def macd(
    values: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float], list[float]]:
    """MACD: (macd_line, signal_line) tail-aligned to the same length (empty if not enough data)."""
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
    """Supertrend → list of directions per candle (1 = uptrend/long, -1 = downtrend/short).

    Length = len(candles) - period (empty if not enough data). Use [-2],[-1] to catch reversals.
    """
    if len(candles) < period + 1:
        return []
    trs = []
    for i in range(1, len(candles)):
        h, low = candles[i]["high"], candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))
    # Wilder ATR series, atr[j] corresponds to candle index = period + j
    atr_series = [sum(trs[:period]) / period]
    for tr in trs[period:]:
        atr_series.append((atr_series[-1] * (period - 1) + tr) / period)

    directions: list[int] = []
    final_upper = final_lower = None
    st = None  # previous supertrend
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


def psar(candles: list[dict], step: float = 0.02, max_af: float = 0.2) -> list[int]:
    """Parabolic SAR → direction per candle (1 = up, -1 = down). [-2],[-1] catch reversals."""
    n = len(candles)
    if n < 2:
        return []
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    uptrend = highs[1] >= highs[0]
    af = step
    sar = lows[0] if uptrend else highs[0]
    ep = highs[0] if uptrend else lows[0]
    directions = [1 if uptrend else -1]
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if uptrend:
            sar = min(sar, lows[i - 1], lows[i - 2] if i >= 2 else lows[i - 1])
            if lows[i] < sar:
                uptrend, sar, ep, af = False, ep, lows[i], step
            elif highs[i] > ep:
                ep, af = highs[i], min(af + step, max_af)
        else:
            sar = max(sar, highs[i - 1], highs[i - 2] if i >= 2 else highs[i - 1])
            if highs[i] > sar:
                uptrend, sar, ep, af = True, ep, highs[i], step
            elif lows[i] < ep:
                ep, af = lows[i], min(af + step, max_af)
        directions.append(1 if uptrend else -1)
    return directions


def adx_dmi(candles: list[dict], period: int = 14) -> dict | None:
    """ADX/DMI → {plus_di(_prev/_now), minus_di(_prev/_now), adx}. None if too little data."""
    n = len(candles)
    if n < 2 * period:
        return None
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, n):
        up = candles[i]["high"] - candles[i - 1]["high"]
        down = candles[i - 1]["low"] - candles[i]["low"]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        h, low, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))

    def _wilder(vals: list[float]) -> list[float]:
        out = [sum(vals[:period])]
        for v in vals[period:]:
            out.append(out[-1] - out[-1] / period + v)
        return out

    sp, sm, st = _wilder(plus_dm), _wilder(minus_dm), _wilder(trs)
    plus_di, minus_di, dx = [], [], []
    for p, m, t in zip(sp, sm, st, strict=False):
        pdi = 100 * p / t if t else 0.0
        mdi = 100 * m / t if t else 0.0
        plus_di.append(pdi)
        minus_di.append(mdi)
        denom = pdi + mdi
        dx.append(100 * abs(pdi - mdi) / denom if denom else 0.0)
    if len(dx) < period or len(plus_di) < 2:
        return None
    adx = sum(dx[:period]) / period
    for v in dx[period:]:
        adx = (adx * (period - 1) + v) / period
    return {
        "plus_di_prev": plus_di[-2], "plus_di_now": plus_di[-1],
        "minus_di_prev": minus_di[-2], "minus_di_now": minus_di[-1], "adx": adx,
    }


def stochastic_k(candles: list[dict], period: int = 14) -> float | None:
    """%K of the Stochastic Oscillator (0–100) at the last candle."""
    if len(candles) < period:
        return None
    w = candles[-period:]
    hh = max(c["high"] for c in w)
    ll = min(c["low"] for c in w)
    if hh == ll:
        return 50.0
    return 100 * (candles[-1]["close"] - ll) / (hh - ll)


def vwap(candles: list[dict], period: int) -> float | None:
    """Rolling VWAP (typical price (h+l+c)/3, volume-weighted) over the last `period` candles."""
    if len(candles) < period:
        return None
    w = candles[-period:]
    tot_v = sum(c["volume"] for c in w)
    if tot_v == 0:
        return None
    return sum(((c["high"] + c["low"] + c["close"]) / 3) * c["volume"] for c in w) / tot_v


def _hl_mid(candles: list[dict], end: int, period: int) -> float:
    """(HH + LL) / 2 over the `period` candles ending at index `end`."""
    w = candles[end - period + 1 : end + 1]
    return (max(c["high"] for c in w) + min(c["low"] for c in w)) / 2


def ichimoku(
    candles: list[dict], conv: int = 9, base: int = 26, span_b: int = 52, shift: int = 26
) -> dict | None:
    """Ichimoku — tenkan/kijun (last 2 points) + cloud top/bottom. None if data too short."""
    n = len(candles)
    if n < span_b + shift + 1:
        return None
    i = n - 1
    tenkan_prev = _hl_mid(candles, i - 1, conv)
    tenkan_now = _hl_mid(candles, i, conv)
    kijun_prev = _hl_mid(candles, i - 1, base)
    kijun_now = _hl_mid(candles, i, base)
    # Cloud at the current candle = spans computed `shift` candles earlier.
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
    """Average True Range (Wilder) — price volatility. candles have high/low/close."""
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
    """RSI (Wilder), length = len(values)-period (empty if not enough data)."""
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


# ── Series aligned PER candle (length = len(candles), None during warmup) — FOR plot() ──
# Unlike the functions above (which return the "last value" or are tail-aligned): the
# *_series/*_line/*_bands functions
# return arrays exactly as long as candles so they can be overlaid directly on the backtest chart.


def atr_series(candles: list[dict], period: int = 14) -> list[float | None]:
    """ATR (Wilder) per candle, length = len(candles). None during warmup."""
    n = len(candles)
    out: list[float | None] = [None] * n
    if n < period + 1:
        return out
    trs = []
    for i in range(1, n):
        h, low, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))
    a = sum(trs[:period]) / period
    out[period] = a  # trs[:period] = candles 1..period → aligned to candle index = period
    for k in range(period, len(trs)):
        a = (a * (period - 1) + trs[k]) / period
        out[k + 1] = a
    return out


def supertrend_line(candles: list[dict], period: int = 10, mult: float = 3.0) -> list[float | None]:
    """Supertrend line (stop level) per candle — overlay. None during warmup."""
    n = len(candles)
    out: list[float | None] = [None] * n
    if n < period + 1:
        return out
    trs = []
    for i in range(1, n):
        h, low, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))
    atr_s = [sum(trs[:period]) / period]
    for tr in trs[period:]:
        atr_s.append((atr_s[-1] * (period - 1) + tr) / period)
    final_upper = final_lower = None
    st = None
    direction = 1
    for j, a in enumerate(atr_s):
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
        out[ci] = st
    return out


def psar_line(candles: list[dict], step: float = 0.02, max_af: float = 0.2) -> list[float | None]:
    """Parabolic SAR value per candle — overlay (SAR dots drawn as a line)."""
    n = len(candles)
    if n < 2:
        return [None] * n
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    uptrend = highs[1] >= highs[0]
    af = step
    sar = lows[0] if uptrend else highs[0]
    ep = highs[0] if uptrend else lows[0]
    out: list[float | None] = [sar]
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if uptrend:
            sar = min(sar, lows[i - 1], lows[i - 2] if i >= 2 else lows[i - 1])
            if lows[i] < sar:
                uptrend, sar, ep, af = False, ep, lows[i], step
            elif highs[i] > ep:
                ep, af = highs[i], min(af + step, max_af)
        else:
            sar = max(sar, highs[i - 1], highs[i - 2] if i >= 2 else highs[i - 1])
            if highs[i] > sar:
                uptrend, sar, ep, af = True, ep, highs[i], step
            elif lows[i] < ep:
                ep, af = lows[i], min(af + step, max_af)
        out.append(sar)
    return out


def keltner_bands(candles: list[dict], period: int = 20, mult: float = 2.0) -> dict[str, list]:
    """Keltner Channel → middle (EMA), upper, lower (= EMA ± mult·ATR) per candle."""
    n = len(candles)
    closes = [c["close"] for c in candles]
    mid_full = pad_left(ema(closes, period), n)
    atr_full = atr_series(candles, period)
    mid: list[float | None] = [None] * n
    up: list[float | None] = [None] * n
    low: list[float | None] = [None] * n
    for i in range(n):
        m, a = mid_full[i], atr_full[i]
        if m is None or a is None:
            continue
        mid[i], up[i], low[i] = m, m + mult * a, m - mult * a
    return {"Keltner mid": mid, "Keltner upper": up, "Keltner lower": low}


def ichimoku_lines(
    candles: list[dict], conv: int = 9, base: int = 26, span_b: int = 52, shift: int = 26
) -> dict[str, list]:
    """Ichimoku → Tenkan, Kijun, Span A, Span B per candle (cloud = the one the strategy uses)."""
    n = len(candles)
    tenkan: list[float | None] = [None] * n
    kijun: list[float | None] = [None] * n
    span_a: list[float | None] = [None] * n
    span_b_line: list[float | None] = [None] * n
    for i in range(n):
        if i >= conv - 1:
            tenkan[i] = _hl_mid(candles, i, conv)
        if i >= base - 1:
            kijun[i] = _hl_mid(candles, i, base)
        # "effective" cloud at candle i = span computed shift candles earlier (matches on_candle)
        j = i - shift
        if j >= conv - 1 and j >= base - 1:
            span_a[i] = (_hl_mid(candles, j, conv) + _hl_mid(candles, j, base)) / 2
        if j >= span_b - 1:
            span_b_line[i] = _hl_mid(candles, j, span_b)
    return {"Tenkan": tenkan, "Kijun": kijun, "Span A": span_a, "Span B": span_b_line}


def adx_series(candles: list[dict], period: int = 14) -> dict[str, list]:
    """ADX/DMI → +DI, -DI, ADX per candle (oscillator, secondary pane)."""
    n = len(candles)
    out_p: list[float | None] = [None] * n
    out_m: list[float | None] = [None] * n
    out_adx: list[float | None] = [None] * n
    if n < 2 * period:
        return {"+DI": out_p, "-DI": out_m, "ADX": out_adx}
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, n):
        up = candles[i]["high"] - candles[i - 1]["high"]
        down = candles[i - 1]["low"] - candles[i]["low"]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        h, low, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))

    def _wilder(vals: list[float]) -> list[float]:
        o = [sum(vals[:period])]
        for v in vals[period:]:
            o.append(o[-1] - o[-1] / period + v)
        return o

    sp, sm, stt = _wilder(plus_dm), _wilder(minus_dm), _wilder(trs)
    plus_di, minus_di, dx = [], [], []
    for p, m, t in zip(sp, sm, stt, strict=False):
        pdi = 100 * p / t if t else 0.0
        mdi = 100 * m / t if t else 0.0
        plus_di.append(pdi)
        minus_di.append(mdi)
        denom = pdi + mdi
        dx.append(100 * abs(pdi - mdi) / denom if denom else 0.0)
    for mi in range(len(plus_di)):
        ci = period + mi  # DI[mi] aligned to candle period+mi
        if ci < n:
            out_p[ci], out_m[ci] = plus_di[mi], minus_di[mi]
    if len(dx) >= period:
        adx = sum(dx[:period]) / period
        if 2 * period - 1 < n:
            out_adx[2 * period - 1] = adx  # first ADX = dx[:period] → candle 2·period-1
        for idx in range(period, len(dx)):
            adx = (adx * (period - 1) + dx[idx]) / period
            ci = period + idx
            if ci < n:
                out_adx[ci] = adx
    return {"+DI": out_p, "-DI": out_m, "ADX": out_adx}


def stochastic_series(candles: list[dict], period: int = 14) -> list[float | None]:
    """%K Stochastic (0–100) per candle (oscillator, secondary pane)."""
    n = len(candles)
    out: list[float | None] = [None] * n
    for i in range(period - 1, n):
        w = candles[i - period + 1 : i + 1]
        hh = max(c["high"] for c in w)
        ll = min(c["low"] for c in w)
        out[i] = 50.0 if hh == ll else 100 * (candles[i]["close"] - ll) / (hh - ll)
    return out
