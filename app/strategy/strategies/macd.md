# MACD Crossover — MACD / Signal crossover

> Style: **Trend / Momentum**. Suggested timeframes: 1h–1d.

## Idea

MACD (Moving Average Convergence Divergence, Gerald Appel) measures **momentum** via the difference between two EMAs. The **MACD** line crossing the **Signal** line (an EMA of the MACD) signals a change in momentum direction.

## Formula

```
MACD line   = EMA(close, fast) − EMA(close, slow)
Signal line = EMA(MACD line, signal)
Histogram   = MACD − Signal
```

## Entry/exit rules

| Condition | Action |
|---|---|
| MACD crosses **ABOVE** Signal (mp ≤ sp and mn > sn) | **BUY** (LONG) |
| MACD crosses **BELOW** Signal | **SELL** (SHORT) |

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `fast` | 12 | Fast EMA. |
| `slow` | 26 | Slow EMA. |
| `signal` | 9 | EMA of the MACD line. |
| `size` | 0.001 | Order size. |

## Pros / Cons

- ✅ Catches momentum/trends well; the 12/26/9 parameter set is popular and reliable.
- ❌ Lagging (EMA-based); frequent false signals in sideways markets (whipsaw).

## When to use

- Trending/momentum markets. Combine with a long-term trend filter to reduce false signals.

## Backtest notes

- Keep the standard parameter set before fine-tuning; avoid overfitting fast/slow/signal.
- You can use the **histogram** (MACD − Signal) changing sign instead of the crossover to enter earlier.
