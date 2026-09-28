# Keltner Channel Breakout — Breaking out of the EMA ± ATR channel

> Style: **Trend / Momentum (breakout)**. Suggested timeframes: 15m–1d.

## Idea

The Keltner Channel (Chester Keltner) places bands around an EMA, with the width based on **ATR** (volatility). Unlike Bollinger (which uses standard deviation), Keltner uses ATR, so it is smoother. This version is used in a **breakout** fashion: price breaking out of the bands signals strong momentum.

## Formula

```
mid   = EMA(close, period)
upper = mid + mult × ATR(period)
lower = mid − mult × ATR(period)
```

## Entry/exit rules

| Condition | Action |
|---|---|
| `price > upper band` | **BUY** (upside breakout) |
| `price < lower band` | **SELL** (downside breakout) |

> Note: this is the **breakout** version (the opposite of Bollinger reversion). Depending on the market, the logic can be inverted to reversion.

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `period` | 20 | EMA + ATR period. |
| `mult` | 2.0 | ATR multiplier (channel width). |
| `size` | 0.001 | Order size. |

## Pros / Cons

- ✅ Catches momentum/breakouts; bands are smooth thanks to ATR, less noisy than Bollinger in some cases.
- ❌ False breakouts in sideways markets; enters after price has already broken out.

## When to use

- Markets about to have / already having strong momentum. Combine with a trend filter to reduce false breakouts.

## Backtest notes

- Compare **breakout vs reversion** on the same data to pick the direction that suits the pair/timeframe.
- Try `mult` 1.5–2.5.
