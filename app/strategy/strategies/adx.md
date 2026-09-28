# ADX / DMI — Directional Movement Index

> Style: **Trend (filtered by strength)**. Suggested timeframes: 1h–1d.

## Idea

The DMI system (Welles Wilder) consists of two directional lines, **+DI / −DI** (buying/selling pressure), and the **ADX**, which measures the **strength** of the trend (regardless of direction). The idea: only trade DI signals when the trend is strong enough (high ADX) → avoid entering during sideways markets.

## Formula (simplified)

```
+DM / −DM : upward / downward directional movement between candles
+DI = 100 × Wilder(+DM) / Wilder(TR)
−DI = 100 × Wilder(−DM) / Wilder(TR)
DX  = 100 × |+DI − −DI| / (+DI + −DI)
ADX = Wilder-smooth(DX)
```

## Entry/exit rules

| Condition | Action |
|---|---|
| `ADX ≥ adx_min` **and** +DI crosses **ABOVE** −DI | **BUY** (strong uptrend) |
| `ADX ≥ adx_min` **and** +DI crosses **BELOW** −DI | **SELL** (strong downtrend) |

ADX < `adx_min` (sideways) → **no entry**.

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `period` | 14 | DMI/ADX period. |
| `adx_min` | 25 | Trend-strength threshold required to allow entries (25 = "strong enough"). |
| `size` | 0.001 | Order size. |

## Pros / Cons

- ✅ The **trend-strength** filter is very useful — avoids trading in sideways markets.
- ❌ Lagging; ADX alone gives no direction (needs DI). DI crosses can be noisy when ADX hovers around the threshold.

## When to use

- As a **filter** combined with other strategies (only enter when ADX is high), or standalone using DI crosses.

## Backtest notes

- Try `adx_min` 20–30. Needs enough data (≥ 2×period) for ADX to stabilize.
