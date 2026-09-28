# Volatility Breakout (Larry Williams k-range)

> Strategy file: `vol_breakout.py` · version 1

## Idea

Larry Williams: **days with strong moves tend to continue** — if during the day price breaks away
from the opening level by ≥ k × yesterday's range, there is a high probability that today is a
"trend day" that keeps going in the breakout direction until the end of the day. Very popular among
Korean crypto quants (Upbit/Bithumb, k≈0.5). Source: community (not peer-reviewed) — evidence is
MEDIUM-WEAK, so it must be validated yourself with walk-forward.

## Rules

| Condition | Action |
|---|---|
| close breaks above `day_open + k × (yesterday_high − yesterday_low)` | **BUY** (once per day) |
| close breaks below `day_open − k × yesterday_range` (if `direction=1`) | **SELL** (once per day) |
| First candle of the next UTC day | **CLOSE** (exit everything) |
| close hits SL (day open or ATR) | **CLOSE**, no re-entry in that direction for the rest of the day |

Days are computed in **UTC** (crypto trades 24/7 with no real opening time — this is a point that must be swept).
EMA trend filter (`trend_len`>0): only LONG when close > EMA, SHORT when close < EMA.

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `k` | 0.5 | Multiplier of yesterday's range. |
| `direction` | 1 | 0 = long-only · 1 = both directions. |
| `trend_len` | 0 | EMA trend filter on the current TF (0 = off). |
| `sl_mode` | 1 | 0 = no SL · 1 = SL at day open · 2 = ATR-based SL. |
| `atr_len` / `atr_mult` | 14 / 1.5 | ATR SL (sl_mode=2). |
| `entry_cutoff_h` | 22 | No new entries after this hour (UTC). |
| `size` | 0.001 | Position size. |

## Pros / Cons

- ✅ 0–1 trades/day/pair, large expected profit per trade (catches trend days) → can absorb taker fees.
- ✅ Only needs OHLCV; simple logic, few parameters → harder to overfit.
- ❌ Sideways/low vol → continuous streaks of small losses (false breakouts).
- ❌ Sensitive to k and the "day open" anchor (00:00 UTC vs other hours); decay after 2018 on BTC (community reports).

## When to use

- 15m–1h candles (needs intraday fills close to the breakout level). Markets with strong trend days (high-vol alts).

## Backtest notes

- The engine fills at candle close → entry price is slightly worse than the theoretical breakout level (acceptable on 15m).
- SL is checked on close (not intrabar) — consistent with the other strategies in the repo.

## Research (strategy-research skill)

Candidate selection context: web survey (Concretum/Quantpedia/academic 2020–2026) + screening of the 12
existing classics (180d × 6 markets, default params → ALL negative on 15m; fees grind down high-turnover
strategies). vol_breakout was chosen because of 0–1 trades/day and large profit per trade.

- **Sweep** (`scripts/sweep_vol_breakout.py`, 48 configs × BTC/ETH/SOL 15m + BTC 1h, 90d):
  a stable plateau at k=0.5–0.7 both directions, positive on 4/4 markets. Top config `k=0.6 dir=1 sl=0`
  average PnL +20.5%, worst market +9.8%, win ~50% — but maxDD ~25%.
- **Long-only is WORSE than both directions** (sweep: dir=0 → 1/4 positive): shorts contribute a lot (the first
  half of the 180d is a downtrend regime); in the second half both directions are positive ~+7–8% → keep direction=1.
- **Loss diagnosis** (`scripts/diag_vol_breakout.py` + `diag_vol_breakout2.py`, 270 trades/180d):
  the patterns "16–19h negative", "Monday negative", "Saturday negative" are NOT stable across the 2 halves → they are
  regime noise, so NO filter was added (avoid overfitting).
- **SL does not rescue DD**: a paper loss cap (−2.5%/trade) improves both halves, but a REAL SL
  (sl_mode=3) exits at close and misses the rebound → SOL +18.4%→+1.7%, DD barely drops.
  DD comes from STREAKS of losing chop weeks, not single tail losses. Default to sl_mode=0
  (the only exit = start of the next day) when evaluating; SL is only an operational option.
- **Noise-k (k_mode=1) is the model fix that pays off** (weekly walk-forward over 180d, 3 pairs 15m):
  `noise_len=40` vs fixed k 0.6: BTC +21.2% DD **9.7%** (from +11.7/16.2), ETH +45.8%
  DD 13.7%, SOL +31.3% DD 15.9% (from +18.4/22.6); worst week −11%→−6.4%; both halves
  (OOS/IS) positive on ALL 3 pairs. A technique with an original source (systrader79), not window fitting.
- **6-pair basket scan** (fixed k 0.6): BTC/ETH/SOL/XRP positive, DOGE/AVAX slightly negative.

- **180d portfolio (Dec 2025→Jun 2026)**: the 3 standard pairs BTC/ETH/SOL equal-weight **+32.75%,
  maxDD 9.91%**, worst week −4.6%; 30d windows: each pair 4/6 positive, portfolio 5/7. All 6 pairs
  (adding XRP/DOGE/AVAX) positive per pair. Looks like it MEETS all 3 goals…
- **…but 365 days flips the picture** (`scripts/walkforward_windows_vol_breakout.py`, fixed params):
  the ~Nov 2025–Jan 2026 window is a disaster — ETH −30%, SOL −37%, **portfolio −26.8% then −12.8%
  back to back**; the full year is ~flat (+3–4%), 8/13 windows positive (62% < 2/3), PnL concentrated in the rebound after the crash.
  The 180d development period happened to fall in a favorable phase — exactly the regime trap of ict_po3 v3.
- **Control on the same 365d** (`scripts/walkforward_365_ict_po3_v4.py`): ict_po3 v4 BTC +3.88%
  maxDD 3.31%, SUI +2.81% DD 6.22% — the old benchmark SURVIVES the adverse regime, just with thin profits.

## VERDICT (2026-06-13)

| Goal | vol_breakout noise40 (3-pair portfolio) |
|---|---|
| Stable in ≥2/3 of windows | ❌ 8/13 over 365d (62%); ✅ over 180d — regime-dependent |
| Consistently positive PnL | ❌ full year ~flat; −26.8%/−12.8% in two consecutive months |
| Max DD < ~10% | ❌ ~35%+ over 365d (✅ 9.9% over 180d) |

**FAILS — do not use with real money.** The edge is real in trend/normal-vol regimes
(OOS 180d holds, noise-k improves it robustly) but dies in the violent chop regime of Nov–Dec 2025.
Compared to the ict_po3 v4 benchmark (survives the full year, DD ≤6%): vol_breakout is NOT more robust.

**If revisiting**: it needs a PRINCIPLED regime gate (e.g. switch off when daily vol > a long-history threshold,
or a drawdown circuit breaker that switches off for 2 weeks after a month worse than −x%) — it must be validated on
UNSEEN data (2024 or forward), not fitted further on this 365d. Do NOT tune k/noise any further.

## Round 2: circuit breaker + verdict on unseen data (2026-06-13) — STOPPED FOR GOOD

Tried exactly the direction above: added a self-referencing **drawdown circuit breaker** (`cb_thresh_pct`/
`cb_window_d`/`cb_pause_d`: rolling 30-day PnL ≤ −10% → stop entering for 14 days; OFF by default).

- **Config selected on seen data** (`scripts/cb_select_vol_breakout.py`, 365d Jun25–Jun26):
  CB 10%/30d/14d improves ALL 3 pairs — BTC −3.8%→+3.4%, ETH +41.4%→+63.3%, SOL −25.3%→−3.3%;
  DD drops (ETH 36→25%, SOL 56→35%) but is still FAR from the 10% goal.
- **ONE-TIME verdict on UNSEEN data** (`scripts/cb_validate_vol_breakout.py`,
  Jun 2024–Jun 2025): the edge does NOT generalize — baseline BTC −4.7%, ETH +11.7%, **SOL −53.9%
  (DD 63%)**; again disastrous months (Feb 2025: −24/−20/−29%). CB limits the damage on all 3
  (BTC +7.4%, SOL −12.7%) but DD is still 25–37%, with many months at −10..−15%.

**FINAL VERDICT: vol_breakout has NO edge that holds across regimes — STOPPED, do not use with real money,
no further tuning.** What remains valuable: (1) the thoroughly tested circuit-breaker mechanism
(improved 6/6 pair-years, reusable for other strategies); (2) the lesson of walk-forward ≥365d + verdict
on unseen data has been added to the skill.
