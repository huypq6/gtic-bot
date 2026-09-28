# Parabolic SAR — Stop and Reverse

> Style: **Trend-following / trailing stop**. Suggested timeframes: 15m–1d. Suits clear trends.

## Idea

Parabolic SAR (Welles Wilder) plots "dots" that follow price, acting as a **trailing stop** and a **reversal** signal. Dots **below price** = uptrend; when price touches a dot → **flip** to downtrend (and vice versa). The trailing speed increases over time according to the acceleration factor (AF).

## Formula

```
SAR_next = SAR + AF × (EP − SAR)
EP  = highest high (uptrend) / lowest low (downtrend) since the trend began
AF  = starts at step (0.02), +step on every new EP, capped at max_af (0.2)
Reverses when price crosses through the SAR.
```

## Entry/exit rules

| Condition | Action |
|---|---|
| SAR flips from down → **up** (dir −1 → +1) | **BUY** (LONG) |
| SAR flips from up → **down** (dir +1 → −1) | **SELL** (SHORT) |

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `step` | 0.02 | Initial acceleration (AF). |
| `max_af` | 0.2 | Acceleration cap. |
| `size` | 0.001 | Order size. |

## Pros / Cons

- ✅ Natural trailing stop, always has an exit point; follows trends well.
- ❌ **Sideways**: flips constantly (whipsaw) → many small losing trades.
- ❌ Late entries/exits at the start and end of a move.

## When to use

- Trending markets. Usually **combined** with a trend-confirmation indicator (ADX, EMA) to filter whipsaws.

## Backtest notes

- Large `step` → sensitive, many flips; small → smooth, lagging. Test across multiple periods.
