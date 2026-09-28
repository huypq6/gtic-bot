# Stochastic Oscillator — Overbought / oversold

> Style: **Mean-reversion**. Suggested timeframes: 15m–4h. Suits oscillating markets.

## Idea

The Stochastic oscillator (George Lane) compares the closing price to the recent **high–low range**. Hypothesis: in an uptrend, price closes near the top; in a downtrend, near the bottom. When %K enters an extreme zone → expect a reversal.

## Formula

```
%K = 100 × (close − LL_period) / (HH_period − LL_period)
```
(LL/HH = lowest low / highest high over `period` candles.) %K → 0 = oversold, → 100 = overbought.

## Entry/exit rules

| Condition | Action |
|---|---|
| `%K < oversold` (e.g. 20) | **BUY** — oversold |
| `%K > overbought` (e.g. 80) | **SELL** — overbought |

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `period` | 14 | Period for computing HH/LL. |
| `oversold` | 20 | Oversold threshold → BUY. |
| `overbought` | 80 | Overbought threshold → SELL. |
| `size` | 0.001 | Order size. |

## Pros / Cons

- ✅ Sensitive, catches reversals early in sideways markets.
- ❌ In a **strong trend**, %K sticks to the extreme zone for a long time → counter-trend signals easily lose.

## When to use

- Sideways markets. Filter by trend (e.g. only BUY when price is above a long EMA) or add an SL.

## Backtest notes

- Try thresholds (20/80, 30/70) and `period`. Backtest across trending periods too to see the weakness.
