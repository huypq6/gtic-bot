# RSI Reversal — RSI-based reversal

> Style: **Mean-reversion** (reverting to the mean). Suggested timeframes: 15m–4h. Suits range-bound markets.

## Idea

RSI (Relative Strength Index, Welles Wilder) measures the **speed & magnitude** of price moves, oscillating between 0–100. Mean-reversion hypothesis: when price is pushed **too far** in one direction (oversold/overbought), it tends to **bounce back** toward equilibrium.

## Formula

```
RS = average gain / average loss   — Wilder smoothing
RSI = 100 − 100 / (1 + RS)
```

- `RSI < 30` → **oversold**.
- `RSI > 70` → **overbought**.

## Entry/exit rules

| Condition | Action | Logic |
|---|---|---|
| `RSI < oversold` | **BUY** (LONG) | catch the bottom, expect a bounce up |
| `RSI > overbought` | **SELL** (SHORT) | catch the top, expect a drop |

> This is a **counter-trend** strategy — use with caution (see Cons).

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `period` | 14 | RSI period. |
| `oversold` | 30 | Oversold threshold → BUY. |
| `overbought` | 70 | Overbought threshold → SELL. |
| `size` | 0.001 | Order size. |

## Pros / Cons

- ✅ Effective in **sideways** / range-bound markets — buy low, sell high.
- ✅ Clear, easy-to-understand signals.
- ❌ **Dangerous in strong trends**: RSI can stay "overbought/oversold" for a long time → catching a falling knife against the trend can lead to heavy losses.
- ❌ Without an SL, tail risk is large.

## When to use

- **Sideways** markets with a stable range.
- Combine with a **trend filter** (e.g. only BUY while price is above a long EMA) or enable an SL to avoid getting stuck when the market breaks out.

## Backtest notes

- Try different thresholds (20/80, 30/70) and `period` values.
- Backtest across both **trending** and **sideways** periods to see the weakness during trends.
- To make counter-trend trading safer: consider entering only when RSI **exits** the extreme zone (cross back) rather than while it is inside it.
