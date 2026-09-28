# ICT Power of Three (PO3) — Session AMD

> School: **Smart Money / liquidity (ICT)**. Suggested timeframe: **15m** (5m–1h works). **Intraday** only (UTC), no overnight holds.

## Versions (kept side by side for comparison)

3 versions share `name="ict_po3"`; pick the version in the UI. VersionCompare compares by name:

| Ver | File | Main difference |
|---|---|---|
| **v1** | `ict_po3_v1.py` | **Proxy** MSS (break of reaction high/low) + bias + FVG/OB retest + tp_mode. NO news filter yet. |
| **v2** | `ict_po3_v2.py` | = v1 + **news filter** (NFP / US hours). |
| **v3** | `ict_po3.py` | = v2 but MSS switched to **swing-structure (CHoCH)** + `swing` param. |
| **v4** | `ict_po3_v4.py` | = v3 + fixes for 4 **model flaws**: rejection sweep, displacement MSS, last-entry hour, min R:R. **Recommended version.** |

**Controlled comparison (same params, only MSS differs), 90–200 days BTC/ETH:** v2 (proxy) avg +0.08% vs
v3 (swing) avg −0.60% — **v3 does NOT clearly beat v2** (v3 only wins on ETH 15m). v3's earlier "+1.65% in-sample"
figure came from the sweep finding params that suited the window (overfit), not from swing MSS being inherently better.
⇒ No version is a proven edge yet; use VersionCompare + backtests across many pairs to check for yourself.

## Idea

ICT **Power of Three (PO3)** describes the life cycle of every candle / every session in 3 **AMD** phases:

1. **Accumulation** — price moves sideways building a range, pooling liquidity.
2. **Manipulation** — price **sweeps** one side of the range to grab liquidity (stops) and then reverses. This is the "judas swing".
3. **Distribution** — the real move in the direction opposite to the sweep.

This version applies PO3 to **intraday sessions** (Session AMD), mapped to **UTC** hours (crypto trades 24/7):

| Session | UTC hours | AMD role |
|---|---|---|
| **Asia** | 00:00–08:00 | **Accumulation** → defines **Asia High / Asia Low** (the day's range) |
| **London + New York** | 08:00–21:00 | **Manipulation** (sweep of the Asia range) → **Distribution** (the push) |
| **Flatten** | 21:00 | Close everything, nothing held into the next day. 00:00 UTC new day → reset |

The trade direction comes from the sweep, BUT it must **agree with the HTF bias** (per the ICT PO3 blog — determine the 4H/daily bias FIRST, "long bias → look for manipulation below the open; short bias → above the open"):
- Sweep **below** Asia Low (sell-side liquidity) → reversal up → **LONG** — only when the **bias is bullish**.
- Sweep **above** Asia High (buy-side liquidity) → reversal down → **SHORT** — only when the **bias is bearish**.

### Bias / Trend filter (ON by default)

`bias_mode=1` (default): filter using a **long EMA** `bias_len` on the running timeframe itself (approximating the 4H/daily trend). Bias is **bullish** if `close > EMA(bias_len)`, **bearish** if `<`. Only enter trades that MATCH the bias direction → drops counter-trend trades (the main source of losses without the filter). `bias_mode=0` = off (trade both directions based on the sweep). The **Bias EMA** line is drawn on the chart.

## Technical framework in this project

- Runs through the shared `Strategy.on_candle` on **1 selected TF**. All timestamps come from the candle's `ts` in **UTC** — `ctx.now` is **not** used (it is not set in backtests).
- **Stateful**: keeps state in the instance across candles (Asia range, sweep, open trade, traded-today). Confirmed that the runner + backtest reuse the same instance.
- Manages **SL/TP** itself: the backtest engine (`vbt.Portfolio.from_signals`) does **not** apply SL/TP on its own — trades exit via a `CLOSE` signal (or a reversal). So the strategy checks price vs SL/TP every candle and emits `CLOSE`.
- Enters **MARKET** at the `close` of the confirming candle. The engine fills at close → **FVG/Order Block are confirmation filters**, not resting LIMIT orders (keeps behavior consistent across all 4 modes).

## Per-candle logic (`on_candle`)

1. **Time**: compute `date` + `hour` (UTC) from `candles[-1]["ts"]`.
2. **New day** (date changes): reset the Asia range / sweep / traded flag; if a trade is still open → `CLOSE` (safety close, no overnight holds).
3. **Build the Asia range**: from today's candles with `hour < asia_end_h`, take `asia_high = max(high)`, `asia_low = min(low)`. Trade only when `hour ≥ asia_end_h` (Asia has closed) and the range has data.
4. **Manipulation (sweep)** — within the window `[asia_end_h, flatten_h)`, consider the day's **first** sweep:
   - `high > asia_high` → record a **HIGH sweep** (SHORT setup), `sweep_extreme = high`.
   - `low < asia_low` → record a **LOW sweep** (LONG setup), `sweep_extreme = low`.
5. **MSS = CHoCH (Change of Character)** — a REAL structure shift using **swing structure** (fractals), only considering structure formed AFTER the sweep:
   - **Swing-high** (fractal): a candle whose high is above `swing` candles on each side; **swing-low** is symmetric. Needs `swing` confirming candles after it → a natural lag.
   - LONG setup: enter when `close >` the **most recent swing-high** (the lower-high of the pullback) → upward structure break (CHoCH).
   - SHORT setup: enter when `close <` the **most recent swing-low**.
   - `mss_lookback` = debounce (minimum candles since the sweep before MSS is allowed).
6. **Confluence** (param `confluence`) — decides **HOW TO ENTER**:
   - `1` = **MSS-breakout**: enter MARKET right at the MSS candle (price far from SL → poor R:R, TP hard to reach — see observations below).
   - `2` = **FVG retest** (default): when MSS occurs + there is a **Fair Value Gap** in the same direction → **ARM** (no entry yet). Wait for price to **pull back** to the near edge of the FVG before entering (better price, **close to SL** → R:R achievable).
     - Bullish FVG: `low[i] > high[i-2]` → near edge = `low[i]` (top of the gap); retest when a candle trades down to ≤ the edge.
     - Bearish FVG: `high[i] < low[i-2]` → near edge = `high[i]`; retest when a candle trades up to ≥ the edge.
   - `3` = **FVG + Order Block retest**: like `2` but also requires an **opposite-colour** candle (OB origin) within the push.
7. **Entry** (MARKET at close):
   - `conf=1`: enter immediately on MSS.
   - `conf≥2`: after arming, enter when price **retests** the FVG. If price **breaks beyond the sweep point** before the retest → **cancel the setup** (look again). If `flatten_h` arrives without a retest → drop it.
   - **1 trade at a time** (no new trade while one is open); **NO limit on trades per day** —
     after a trade closes, it looks for a new setup (sweep→MSS→[retest]) the same day and enters only when conditions are met.

## SL / TP & intraday exit

**Risk (SL distance from entry)** per `sl_mode`:
- `sl_mode=0`: `risk = |entry − sweep_extreme| + buffer` (the sweep point — usually FAR → TP/SL rarely hit, often flattened).
- `sl_mode=1` (default): `risk = atr_mult × ATR(atr_len)` (CLOSE, adapts to volatility → TP/SL reachable within the day).

| Direction | SL | TP |
|---|---|---|
| LONG | `entry − risk` | `entry + rr_target × risk` (or Asia High if `tp_mode=1`) |
| SHORT | `entry + risk` | `entry − rr_target × risk` (or Asia Low if `tp_mode=1`) |
- Every candle while in a trade, check against **close** (matching vectorbt's fill method):
  - LONG: `close ≤ SL` (stop loss) or `close ≥ TP` (take profit) → `CLOSE`.
  - SHORT symmetric.
- **End-of-day flatten**: `hour ≥ flatten_h` or a new day with a trade still open → `CLOSE`.

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `bias_mode` | 1 | 0 = trend filter off (both directions) · 1 = only trade with the HTF EMA trend. |
| `bias_len` | 200 | Bias EMA length (candles ~ 4H/daily; depends on TF). |
| `confluence` | 2 | Entry method: 1 = MSS-breakout (MARKET) · 2 = FVG retest · 3 = FVG+OB retest. |
| `mss_lookback` | 2 | Debounce: minimum candles since the sweep before MSS is allowed. |
| `swing` | 1 | Fractal half-width defining swing high/low (MSS = swing break). Smaller = more sensitive/more trades. |
| `tp_mode` | 1 | TP: 0 = fixed `rr_target` · 1 = opposite liquidity (Asia range high/low). |
| `rr_target` | 2.0 | R multiple for TP when `tp_mode=0` (also the fallback for `tp_mode=1`). |
| `sl_mode` | 1 | SL: 0 = at the sweep point (far → often flattened) · 1 = **ATR**-based (close → TP/SL reachable). |
| `atr_len` / `atr_mult` | 14 / 1.0 | SL distance from entry = `atr_mult × ATR(atr_len)` when `sl_mode=1`. |
| `sl_buffer_pct` | 0.05 | SL buffer beyond the sweep point, as % of price (only `sl_mode=0`). |
| `asia_end_h` | 8 | UTC hour the Asia session ends (range locked). |
| `flatten_h` | 21 | UTC hour to close all trades (end of NY). |
| `news_filter` | 2 | News filter: 0 = off · 1 = block entries during news hours · 2 = + block NFP days (first Friday of the month). |
| `news_start_h` / `news_end_h` | 12 / 14 | US news window (UTC): 8:30 ET = 12:30 (summer) / 13:30 (winter). |
| `max_per_day` | 0 | 0 = unlimited (re-enter after each close) · N = max N trades/day. |
| `size` | 0.001 | Quantity. |

## Display (backtest chart)

- `plot()` draws **Asia High** and **Asia Low** **per day** (step lines, pane 0) — clearly shows the range being swept before the reversal.
- Entry/exit markers for each trade use the backtest chart's built-in trade mechanism.

## Pros / Cons

- ✅ Follows ICT logic (liquidity sweep + reversal), fixed 2R R:R, intraday discipline, no overnight risk.
- ✅ HTF bias filter (with-trend only); 1 trade at a time, re-entry after close → tracks structure closely.
- ❌ MSS uses a **break-of-N-candles** proxy, not full swing structure → may enter earlier/later than manual ICT.
- ❌ FVG/OB are **confirmation filters** (MARKET entry at close), not a simulation of a resting LIMIT order at the FVG → real fills (paper/live) may differ from the ICT-optimal price.
- ❌ The Asia range means less on big-news / abnormally volatile days (NFP/CPI…).

## When to use

- Liquid pairs (BTCUSDT, ETHUSDT), **15m** timeframe. Days where the Asia session forms a clear range and London/NY then sweeps it.
- Raise `confluence` (2→3) for fewer, higher-quality trades; lower it to 1 for more signals to study.

## Backtesting notes

- Needs many days of data (set "days" ≥ 14) to get enough session samples. Parameters are edited directly on the backtest form (bias_mode, confluence, bias_len, rr_target…).
- Sweep `(bias_mode, bias_len, confluence, mss_lookback, rr_target)`; defaults 1 / 200 / 2 / 3 / 2.0.
- Verify: 1 trade at a time; multiple trades per day possible; no trade held past 00:00 UTC.

### Empirical observations + parameter sweep (`scripts/sweep_ict_po3.py`)

- **FVG-retest entry (`conf≥2`) is clearly better than breakout (`conf=1`)**: BTC 15m −1.9% vs −8.25%; it makes
  `rr_target` start to affect results → TP is now reachable (breakout: every rr gives identical results because TP is never hit).
- **`tp_mode=1` (TP at opposite liquidity) wins overwhelmingly** in the sweep (288 backtests, BTC/ETH 15m+1h):
  takes the whole top, winrate ~37–44%, low maxDD (~3%).
- **Most robust set = current defaults** (`conf=3, tp_mode=1, bias_len=100, mss=3`): avg PnL −0.76%,
  profitable on 2/4 markets, win ~40%, maxDD 3.4%. Higher-frequency alternative: `conf=2` (similar, ~37 trades).
- **Out-of-sample** (longer windows + pairs not swept): BTC/ETH 15m 90d ≈ −2.4…−2.7%; ETH 1h 200d **+0.88%**;
  SOL 1h 120d −3.3%. Same magnitude as in-sample → **not heavily overfit**, but **not yet a profitable edge**.
- **News filter (`news_filter`, default 2)**: blocks entries in the 12–14 UTC window + NFP days — improves
  3/4 markets, reduces drawdown (ETH 1h: +0.88%→+6.34%).
- **Swing-structure MSS (CHoCH) > old proxy**: replacing the reaction high/low with a fractal swing break
  **flips in-sample to positive**. Sweep (216 sets) → most robust set = **current defaults**
  (`conf=2, tp_mode=0, rr=1.5, bias_len=200, mss=2, swing=1`): avg PnL **+1.65%**, profitable on **3/4** markets,
  win ~38%, 57 trades, maxDD 5.1%. `swing=1` (sensitive) gives more trades; `bias_len=200` is the most stable.
- **Out-of-sample** (longer windows + SOL not swept): ETH 15m **+3.14%**, SOL 1h **+0.60%**, ETH 1h +0.19%,
  but **BTC persistently negative** (15m −2.6%, 1h −3.2%). I.e. it **wins on ETH/SOL, loses on BTC** → not yet a cross-market edge.
- **Trades often flattened at end of day (SL/TP misplaced) → added `sl_mode`**: with SL at the sweep point (far),
  ~80–90% of trades exit via the 21:00 flatten, almost NEVER hitting SL/TP → TP is meaningless. Switching to an **ATR SL**
  (`sl_mode=1`, default) makes SL/TP **reachable within the day**: win rises to ~45–50% (15m), SL starts cutting real losses.
  In exchange the trade count rises → **fee drag** (≈0.1%/round trip × many trades) pulls PnL to ~breakeven. The **1h timeframe still often flattens**
  (few candles/day) — the ATR SL suits 15m better.
- **Reducing frequency does NOT help**: raising `confluence`/`swing`/`mss_lookback` pushes low-frequency variants
  down the ranking (cuts winners too → worse net). Added `max_per_day` and compared 0/1/2 → **almost identical** (the strategy
  already only does ~1 trade/day; "100 trades" is the sum over 4 markets across 45–200 days). ⇒ fees are NOT the bottleneck.
- **The bottleneck is the MARKET, not the frequency**: over 60–200 day windows, ETH 15m **+1.46%**, ETH 1h
  **+2.67%**, SOL 1h **+1.23%** (win 53–67%) — only **BTC −2.66%** drags it down.
- **Pair-basket scan (`scripts/scan_pairs_ict_po3.py`, 14 pairs × 15m/1h):** the decisive factor is the **TIMEFRAME**:
  - **15m: 12/14 pairs POSITIVE** (60 days) — DOT +5.6%, INJ +4.8%, DOGE +4.2%, AVAX +2.7%, XRP +1.7%, BTC +1.4%,
    ETH/SOL/ADA/LTC/LINK/NEAR slightly positive; only **BNB −1.8%, SUI −2.2%** negative.
  - **1h: mostly NEGATIVE** (only SUI/ETH/DOGE positive; INJ −12.5%) → **not suited to 1h** (few candles/day, often flattened).
  - Positive on both TFs: **ETH, DOGE**.
- **Recommended basket: run on 15m**, diversified across many liquid pairs (ETH, SOL, DOT, DOGE, AVAX, XRP, LTC, ADA);
  **avoid 1h** and avoid BNB/SUI (negative on 15m). Per-pair PnL is **window-sensitive** (BTC +1.4% here but negative in other windows)
  → rely on diversification + walk-forward, don't trust a single number.
- **Walk-forward (`scripts/walkforward_ict_po3.py`, 8-pair 15m basket, 6 windows × 30 days, fixed params):**
  only **3/6 windows positive** — the first 3 (Dec–Mar) NEGATIVE, the last 3 (Mar–Jun) positive → **the edge is regime-dependent,
  NOT stable over time**. The 60-day basket scan looked good because it happened to fall in a recent favorable period.
  Per pair only **DOGE 5/6, DOT 4/6, XRP 4/6** positive more than half the time; ETH 2/6, SOL 1/6 → NOT stable.
- **v3 conclusion**: good discipline but no durable edge over time → stop v3, the MODEL needs fixing.

### v4 — fixes for 4 model flaws (not parameter tuning)

Diagnosis on real data (ETH 15m, 181 days): **54% of v3 "sweeps" were candles closing OUTSIDE the range** (genuine
breakouts) → v3 faded the trend on more than half the days. v4 fixes:
1. `reject_sweep` — a sweep is only valid when the candle **closes back inside the range** (rejection/SFP).
2. `disp_mult` — MSS must show **displacement** (candle body ≥ k×ATR), filtering out weak MSS in chop.
3. `entry_cutoff_h` — no new entries after 15h UTC (late trades die from the 21h flatten, not from being wrong).
4. `min_rr` — (tp_mode=1) skip the entry if the opposite TP is closer than k×risk, wait for a deeper retest.

**Results (BTCUSDT 15m, 180 days, default params, fee 0.05%/side):**
- PnL **+3.43%** · maxDD **3.31%** · win 58% · 12 trades.
- WEEKLY walk-forward (`scripts/walkforward_ict_po3_v4.py`): **85% of weeks non-negative** (5 positive + 17 flat + 4 negative /26),
  worst week **−1.29%**; monthly there is no disastrous month (worst −1.07%) — **positive even through the
  Dec–Mar regime where v3 lost heavily**.
- **Parameter neighbourhood all positive** (8/8 variants +1.3…+3.4%, DD <4%) → a stable plateau, not a lucky peak.
- Same-params control: the v4 fixes improve 3/4 markets vs v3 behavior (e.g. ETH 5m −1.35%→+1.48%).
- ETH 15m/BTC 5m still slightly negative over 180/60 days → **only BTC 15m is recommended** (meets the goal "stable on ≥1 pair×1 TF").

**v4 pair scan (`scripts/scan_pairs_ict_po3_v4.py`, 14 pairs × 15m/5m, ranked by % non-negative weeks):**
- **15m**: BTC and SUI stand out; XRP/DOGE look good over 120d but **fall apart when checked over 180d** (XRP +2.32% → +0.01%
  = window luck). 180d validation: **SUI +9.42%, DD 2.75%, win 69%, 88% non-negative weeks** (best in the
  program); **BTC +3.43%, DD 3.31%, 85%**. Worst week for both ~−1.2%.
- **5m**: no pair is robust enough (INJ/BNB/ETH positive but small 45-day sample, 67–83% of weeks) → **don't use 5m yet**.
- **Recommended basket: BTC + SUI, 15m** (average ~+6.4%/180d, DD ≤3.3%, diversified over 2 pairs).

**v4 verdict (against the goals)**: maxDD ✅ (3.3% < 10%) · stability ✅ (robust neighbourhood + doesn't collapse across regimes)
· "always positive every week" ⚠️ nearly met (85% of weeks non-negative, 4 small negative weeks /26 — no strategy achieves 100% in the
literal sense). Note: **12 trades/180 days** = low frequency, modest PnL (~7%/year unleveraged), many flat weeks
because there were no trades. Recommendation: **paper-trade BTC 15m with v4** to confirm forward, NOT real money yet.

**365-day check (2026-06-13, `scripts/walkforward_365_ict_po3_v4.py`)**: BTC 15m
**+3.88%, maxDD 3.31%, 18 trades**; SUI **+2.81%, DD 6.22%, 21 trades**; worst 30d window only
−2.0% — v4 **survives the adverse Nov–Dec 2025 regime** (where the vol_breakout portfolio lost −26.8%/month).
Reinforces the "stable + low DD" verdict; the price is a thin return of ~3–4%/year unleveraged.

**Leverage (2026-06-13, `scripts/leverage_ict_po3_v4.py`, 365d)**: DD scales ~linearly,
no blow-ups. **BTC ×3: +13.77%/year, maxDD 9.67% (still <10%), worst month −6.87%**;
×2: +9.17%, DD 6.53% (safer). SUI only tolerates ×1 (×2 → DD 12.16% exceeds the target).
⇒ The most disciplined way currently available to "increase profit": **paper BTC 15m ×2–3 + SUI 15m ×1**.
Note: the engine scales fees by notional but does NOT yet simulate perp funding (intraday trades held
a few hours, ~22 trades/year → small impact); liquidation at ×3 is very far away with this DD.

**14-pair basket scan on the 365-day standard (2026-06-13, `scripts/scan365_ict_po3_v4.py`)**: only
**3 pairs positive** — BTC +4.58% (DD 3.31%), **DOGE +3.96% (DD 1.70%, lowest in the basket, win 54.5%,
worst month −1.31%, 10/13 windows non-negative)**, SUI +2.81% (DD 6.22%). The other 11 pairs are all NEGATIVE
(ETH −1.1%, SOL −5.5%, XRP −6.1%, ADA −7.9%, INJ −9.0%…) — re-confirming "good over 120/180d ≠ durable"
(XRP/DOGE were borderline at 180d; only 365d separates winners from losers). **DOGE leverage**: ×3 → +11.80%
DD 5.04%; ×5 still DD 8.30% but the RECOMMENDED CAP is ×3 — DOGE was picked from 12 candidates
(multiple-comparison risk) and the sample is only 11 trades/year.

**Recommended paper basket (updated)**: **BTC ×2–3 + DOGE ×3 + SUI ×1**, 15m, capital split equally
→ expected ~+8–9%/year, estimated portfolio DD <7% (3 pairs with low correlation in trade timing).

## Known limitations (summary for code readers)

1. MSS = break of a **swing fractal** (CHoCH) formed after the sweep; needs `swing` confirming candles → entry lags by `swing` candles. Simpler than the multi-timeframe CHoCH of manual ICT.
2. `conf≥2`: enters on the **FVG retest** but fills at the **close** of the candle touching the zone (the engine does not simulate LIMIT/intrabar) → entry price is approximate, not exactly the FVG edge.
3. SL/TP are checked on `close` (no intrabar high/low peeking) to match vectorbt's close fills.
4. Sessions are fixed in UTC; London/NY DST is not handled (acceptable since crypto uses UTC).
5. **Mid-day startup**: the Asia range is only built from the day's first live candle → a bot started/restarted after 08:00 UTC misses that day's setup (the range is complete from the next day).

### Live bug fix 2026-09-23 — before this, live NEVER entered a trade

- v3/v4 anchored the sweep candle by **absolute index** (`_sweep_i`). Backtest passes a growing list so it was correct;
  the live runner passes a **sliding window** (deque) → the index shifts every candle → it never saw a swing/MSS.
  Measured on 92 real days (BTC/DOGE/SUI/INJ 15m): backtest 17 trades, old live **0 trades**.
- Fix: anchor by the sweep candle's `ts` (`_sweep_ts` + `_index_of`). Backtest is **unchanged** (verified by matching
  old/new signals), live ≡ backtest when runner lookback = 1000 (recursive EMA100/ATR converge).
  Regression: `tests/test_ict_po3_v4.py::test_sliding_window_matches_growing_list`.
- Plus a simultaneous infrastructure bug: the feed only streamed `default_tf` (1m), so the 15m bot received no candles at all (see commit `b9c0e77`).
