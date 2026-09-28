# Supertrend — ATR-based trend following

> Style: **Trend-following**. Suggested timeframes: 15m–4h. Suits clear trends.

## Idea

Supertrend plots a line that follows price and **switches sides** when the trend reverses. It uses **ATR** (volatility) to set a buffer band, which filters noise better than a plain line. Line **below price** = uptrend (long), **above price** = downtrend (short).

## Formula

```
hl2          = (high + low) / 2
basicUpper   = hl2 + mult × ATR(period)
basicLower   = hl2 − mult × ATR(period)
finalUpper/finalLower: "ratcheted" along with the close to resist noise
direction    = +1 (uptrend) if close is above finalUpper, −1 otherwise (stateful)
```

## Entry/exit rules

| Condition | Action |
|---|---|
| direction flips from −1 → **+1** | **BUY** (enter LONG) |
| direction flips from +1 → **−1** | **SELL** (enter SHORT) |

Enters only at the moment of the **flip** (comparing `direction[-2]` with `direction[-1]`).

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `period` | 10 | ATR period. |
| `mult` | 3.0 | ATR multiplier (buffer band). Larger → fewer flips, less noise but more lag. |
| `size` | 0.001 | Order size. |

## Pros / Cons

- ✅ Follows trends well, filters noise thanks to ATR; clear rules, few false flips.
- ❌ Still whipsaws in sideways markets (reduce with a larger `mult`).
- ❌ Enters late, after the trend is already established.

## When to use

- Trending markets with medium–high volatility. Increase `mult` if there is a lot of noise.

## Backtest notes

- Sweep `(period, mult)`; popular sets are 10/3 or 7/3.
- Compare with Donchian/EMA cross on the same data to choose a suitable trend filter.
