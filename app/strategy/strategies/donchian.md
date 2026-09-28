# Donchian Breakout — Price Channel Breakout

> School: **Trend-following**. Suggested timeframe: 1h–1d. Pairs: high liquidity.

## Idea

The Donchian Channel was proposed by Richard Donchian — one of the classic trend-following systems (the foundation of the "Turtle Traders"). Hypothesis: when price **breaks out** of its recent range (the high/low of N candles), it often **starts a new trend** strong enough to be profitable.

## Formula

With `period = N`, at each closed candle:

- **Channel top** = highest price (`high`) of the **N candles BEFORE** the current candle.
- **Channel bottom** = lowest price (`low`) of the previous N candles.

> The current candle is excluded from the window to **avoid lookahead** (it is not compared against itself).

## Entry/exit rules

| Condition | Action |
|---|---|
| `current price > Channel top` | **BUY** (go LONG) — breaks the high |
| `current price < Channel bottom` | **SELL** (go SHORT) — breaks the low |
| Opposite signal | The engine automatically **closes the old position and opens the new direction** (flip) |

Optional risk management: enable `sl_pct` / `tp_pct` (% from entry price) so the engine cuts SL/TP automatically on every tick.

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `period` | 20 | Channel width. Larger → fewer signals, catches long trends; smaller → more sensitive, more noise. |
| `size` | 0.001 | Position size (base units). |
| `sl_pct` | 0 (off) | Stop-loss as % from entry price. |
| `tp_pct` | 0 (off) | Take-profit as % from entry price. |

## Pros / Cons

- ✅ Catches big trends; simple, objective rules, easy to backtest.
- ✅ Does not depend on predicting tops/bottoms.
- ❌ **Sideways**: many false breakouts → consecutive losses (whipsaw).
- ❌ Late entries (after price has already broken out) → misses the start of the move.

## When to use

- Markets/pairs with a **clear trend** and enough volatility.
- **Medium–long** timeframes (1h and up) to reduce false breakouts.
- Consider adding a trend filter (e.g. only LONG when price > a long EMA) to reduce noise.

## Backtest notes

- Try several `period` values (10/20/55) on **multiple pairs + multiple periods** — avoid picking one "pretty" value (overfitting).
- Include **fees**; trend-following trades rarely so fees have a moderate impact, but whipsaw in sideways zones can erode it.
- Evaluate `max_dd` (losing streaks in sideways markets) and the average length of winners.

## v2 — ATR trailing + exit channel + ADX/weekend filter (`donchian_v2.py`)

The 180-day screening showed raw v1 profitable on 1h (ETH +66%) but with **maxDD > 60%** because it only exits on
an opposite breakout (giving back all profit when the trend breaks). v2 adds active exits + filters:

| Param | Default | Meaning |
|---|---|---|
| `exit_mode` | 2 | 0 = ATR trailing (chandelier) · 1 = short opposite channel (turtle) · 2 = both. |
| `exit_period` | 10 | Opposite channel for exiting (long exits when breaking the M-candle low). |
| `atr_len` / `atr_mult` | 14 / 2.5 | Trail = extreme close since entry ∓ mult×ATR (ratchet). |
| `adx_min` | 0 (off) | Only enter when ADX ≥ threshold — avoids sideways whipsaw. |
| `dow_filter` | 0 (off) | 1 = no new entries Sat 00:00 → Sun 20:00 UTC (chop zone, Concretum research). |

An opposite breakout of the main channel still **reverses** the position, as in v1.

### Research (strategy-research skill)
- **Screening (default params, 180d × 6 markets)**: raw v1 NEGATIVE on 5/6 (15m killed by fees;
  1h mixed — ETH +66% but DD 64%).
- **v2 sweep** (`scripts/sweep_donchian_v2.py`, 36 configs × BTC/ETH/SOL 1h 180d + BTC 15m 90d):
  **COMPLETE FAILURE** — every config is negative on average (−12…−31%), the best only positive on 2/4 markets,
  DD 33–70%, win 33–36%, 440–1200 trades. Active exits (ATR trail / exit channel) cut off
  the big winners — the only thing that feeds trend-following — and then churn fees on re-entry.
  ADX/weekend filters do not rescue it.
- **Verdict: STOP donchian v2.** Same conclusion as ichimoku: 1h trend-following on
  crypto in this regime cannot reduce DD without killing PnL. No further parameter tuning
  (alpha ceiling). The intraday direction looks more promising: see `vol_breakout.md`.
