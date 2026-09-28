# VWAP Cross — Price crossing the volume-weighted average price

> Style: **Trend / Momentum** (following money flow). Suggested timeframes: 5m–1h.

## Idea

VWAP (Volume Weighted Average Price) is the **volume-weighted average price** — it reflects the price at which most of the volume has traded, and is often treated as the institutional "fair price" reference. Price rising above VWAP → buyers are in control; falling below → sellers.

## Formula

```
typical price = (high + low + close) / 3
VWAP (rolling N) = Σ(typical × volume) / Σ(volume)   over the last `period` candles
```

> This version uses a **rolling VWAP** over a `period`-candle window (no daily reset) to fit the engine.

## Entry/exit rules

| Condition | Action |
|---|---|
| Price crosses **ABOVE** VWAP (prev ≤ VWAP, now > VWAP) | **BUY** (LONG) |
| Price crosses **BELOW** VWAP | **SELL** (SHORT) |

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `period` | 20 | Number of candles for VWAP (rolling window). |
| `size` | 0.001 | Order size. |

## Pros / Cons

- ✅ Tied to **real money flow** (volume), not just price; an intuitive reference level.
- ❌ Crosses back and forth in sideways markets (whipsaw); rolling VWAP differs from the classic daily VWAP.

## When to use

- Intraday timeframes, markets with meaningful volume. Good as an in-session bias filter.

## Backtest notes

- Volume in the data must be valid (non-zero). Tune `period` to the timeframe.
- Consider a **daily-anchored** VWAP if you need the standard intraday version.
