# Grid — Grid trading around a reference level

> Style: **Mean-reversion / harvesting oscillation**. Suggested timeframes: 5m–1h. Suits sideways markets.

## Idea

Grid trading places a "grid" of evenly spaced buy/sell levels around a reference; as price **oscillates up and down**, we repeatedly **buy low – sell high** to collect profit from the range, without having to predict direction. Best suited to **sideways** markets.

## Model note

The engine here is **1 bot = 1 position** (no multiple simultaneous grid orders like a classic grid). This version is a **1-step / 1-position grid**: enter when price deviates `step_pct` from the reference, **close when price returns to the reference**, then repeat — still capturing the "harvest the oscillation" spirit.

## Formula & rules

```
reference (ref) = SMA(close, period)
lower = ref × (1 − step_pct%)      upper = ref × (1 + step_pct%)
```

| State | Condition | Action |
|---|---|---|
| Flat | price ≤ lower | **BUY** (buy 1 step below the reference) |
| Flat | price ≥ upper | **SELL** (short 1 step above the reference) |
| LONG | price ≥ ref | **CLOSE** (take profit on return to the reference) |
| SHORT | price ≤ ref | **CLOSE** (take profit on return to the reference) |

> This strategy **reads `ctx.position`** to decide whether to close or open.

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `period` | 20 | SMA period used as the reference level. |
| `step_pct` | 1.0 | Width of 1 grid step (% from the reference). |
| `size` | 0.001 | Order size per step. |

## Pros / Cons

- ✅ Steady profits in **sideways** markets; no need to predict direction.
- ❌ **Dangerous in strong trends**: price moves one way far from the reference → a losing position that drags on (no multi-level grid to average down). Consider adding an SL or a limit.
- ❌ The 1-step version is simpler than a classic multi-level grid.

## When to use

- Consolidating/sideways markets with a stable range. Avoid strong trending periods or add risk guards.

## Backtest notes

- Tune `step_pct` to the pair's volatility; too small → many trades + fees, too large → few opportunities.
- Also backtest trending periods to see the risk of a stuck position.
