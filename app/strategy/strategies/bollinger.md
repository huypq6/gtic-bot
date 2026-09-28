# Bollinger Bands Reversion — Reverting to the middle band

> Style: **Mean-reversion**. Suggested timeframes: 15m–4h. Suits range-bound markets.

## Idea

Bollinger Bands (John Bollinger) consist of: **middle band** = SMA(period), **upper/lower bands** = middle ± mult × standard deviation. The ±2σ range covers ~95% of price movement. Mean-reversion hypothesis: when price touches an **outer band** it tends to get "pulled" back to the middle band.

## Formula

```
mid   = SMA(close, period)
sd    = stdev(close, period)
upper = mid + mult × sd
lower = mid − mult × sd
```

## Entry/exit rules

| Condition | Action |
|---|---|
| `price ≤ lower band` | **BUY** — oversold, expect a bounce back to mid |
| `price ≥ upper band` | **SELL** — overbought, expect a drop back to mid |

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `period` | 20 | SMA + standard deviation period. |
| `mult` | 2.0 | Standard deviation multiplier (band width). |
| `size` | 0.001 | Order size. |

## Pros / Cons

- ✅ Effective in **sideways** markets with a stable range.
- ❌ On a **trend breakout** (band expansion), price can "walk the band" → fading it easily loses.
- ❌ Without an SL, tail risk is large (as with any mean-reversion).

## When to use

- Consolidating/sideways markets. Consider filtering by band width (squeeze) or adding an SL.

## Backtest notes

- Try `mult` 1.5–2.5 and different `period` values. Also backtest trending periods to see the weaknesses.
