# EMA Crossover — Moving average crossover

> Style: **Trend-following**. Two versions: **v1** (basic) and **v2** (adds a gap% filter).

## Idea

The EMA (Exponential Moving Average) smooths price, giving more weight to recent data. Use **two EMAs** with different periods: the **fast** line reacts quickly, the **slow** line reacts slowly. When the fast line crosses the slow line → trend-change signal.

## Formula

```
EMA_t = price_t × k + EMA_(t-1) × (1 − k),   k = 2 / (period + 1)
```

Look at the last 2 points of each EMA (`prev`, `now`):

- **Golden cross**: `fast` crosses **above** `slow` (fast_prev ≤ slow_prev and fast_now > slow_now).
- **Death cross**: `fast` crosses **below** `slow`.

## Entry/exit rules

| Condition | Action |
|---|---|
| Golden cross | **BUY** (LONG) |
| Death cross | **SELL** (SHORT) |
| Opposite direction | Flip (close + open the new side) |

## v2 — Distance filter (gap%)

On low timeframes (1m), v1 often enters while the 2 EMAs are stuck close together → **noisy crosses**, and fees eat into profit. **v2** only enters when:

```
|EMA_fast − EMA_slow| / EMA_slow × 100 ≥ gap_pct
```

→ skips weak crosses, **fewer false trades**. Empirically (BTC 5m backtest): v1 ≈ −20% / 91 trades, v2 ≈ +3.6% / 1 trade — the filter clearly reduces overtrading.

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `fast` | 9 | Fast EMA period. |
| `slow` | 21 | Slow EMA period (> fast). |
| `size` | 0.001 | Order size. |
| `gap_pct` | 0.1 | (v2) Minimum % distance between the 2 EMAs to enter. |

## Pros / Cons

- ✅ Simple, catches trends well; v2 filters noise effectively.
- ❌ In sideways markets: crosses back and forth repeatedly (whipsaw).
- ❌ Lagging signals (EMA is a lagging indicator).

## When to use

- Trending markets. Medium timeframes and above.
- On low timeframes → prefer **v2** (gap filter) to reduce false trades.

## Backtest notes

- Sweep `(fast, slow)` pairs but beware of overfitting; prefer common "round" pairs (9/21, 12/26, 50/200).
- Compare **v1 vs v2** on the Backtest page → "Compare versions".
