# 08 — Mode Workspaces: run Paper / Testnet / Live side by side

> Status: implemented (2026-10). Technical + UI design for managing several trading modes at once.

## 1. Problem

Bots of different modes already run in parallel in one process (mode is a property of each bot,
each bot gets its own executor). What was missing is a way to **see and manage each mode
separately**:

- Open positions and the bot list mixed PAPER/TESTNET/LIVE rows; only a badge told them apart.
- Each table had its own (or no) mode filter → easy to look at the wrong "world".
- No way to compare how the same strategy behaves across modes, which is the core loop once Live
  is on: **live runs the trusted version, paper/testnet keep evaluating candidates and shadowing
  live** to detect drift (slippage, missed signals, worse R).

## 2. Goals / non-goals

Goals
1. One global **mode lens** (All · Paper · Testnet · Live) that scopes every page.
2. An **Overview** page: one card per mode — bots, open positions, equity, today + 7-day results.
3. A **Compare** page: per strategy × symbol × TF, results per mode/version side by side, plus
   **live-vs-paper divergence** of paired trades (entry slippage, R difference, missed trades).
4. **Clone a bot to another mode** (shadow a live bot in paper, promote a paper candidate).

Non-goals
- No change to execution / risk / LIVE guardrails. The lens only filters what is *shown*.
  Creating a LIVE bot (also by cloning) still needs `ENABLE_LIVE=1` + typing "LIVE".
- No separate processes or DBs per mode (decision #1: single process stays).
- Manual orders stay PAPER-only (unchanged).

## 3. Concepts

| Term | Meaning |
|---|---|
| Mode lens | UI-wide filter `"" (All) \| PAPER \| TESTNET \| LIVE`, persisted per browser |
| Shadow bot | A PAPER (or TESTNET) bot with the same strategy version/params/symbol/TF as a LIVE bot — the reference for "what the model expected" |
| Candidate bot | A PAPER/TESTNET bot running a newer version or params, evaluated before promotion |
| Pair | A trade in mode A and a trade in mode B of the same strategy version, symbol, TF and side, opened within one candle of each other |

Recommended workflow once Live is on:

```
            new idea / v5                    trusted v4
backtest ──► PAPER candidate ──► TESTNET ──► LIVE ◄──┐
                     ▲                               │ clone (shadow)
                     └──────── compare ◄──── PAPER shadow v4
```

## 4. Technical design

### 4.1 Backend (FastAPI)

Mode filter added to the list endpoints that lacked it (all optional, empty = all modes):

| Endpoint | Change |
|---|---|
| `GET /api/bots?mode=` | filter `bot.mode` |
| `GET /api/positions?mode=` | filter `position.mode` |
| `GET /api/audit?mode=` | filter `audit_log.mode` |
| `GET /api/trades`, `GET /api/orders` | already had `mode` |

New router `app/api/modes.py`:

**`GET /api/modes/summary`** → one object per mode (always PAPER, TESTNET, LIVE):
```json
{"mode": "PAPER",
 "bots": {"RUNNING": 2, "PAUSED": 0, "STOPPED": 1},
 "open_positions": 1, "open_risk": 12.3,
 "today": {"trades": 3, "pnl": 4.1},
 "week":  {"trades": 14, "wins": 8, "pnl": 21.0, "sum_r": 3.4}}
```
DB-only aggregation (no candle reads), cheap enough to poll every 5 s. Account equity on the
Overview cards comes from the existing `GET /api/accounts` (live snapshot incl. unrealized PnL).
`today` = closed since 00:00 UTC (same day boundary as the daily-loss guard).

**`GET /api/compare?days=30&symbol=`** → closed positions in the window, grouped:
```json
{"groups": [{
   "strategy": "ict_po3", "symbol": "SUIUSDT", "tf": "15m",
   "rows": [ {"mode": "LIVE",  "version": "4", "trades": 10, "wins": 6, "win_rate": 60,
              "sum_r": 3.2, "avg_r": 0.32, "pnl": 41.0, "fees": 3.1, "bots": [7]},
             {"mode": "PAPER", "version": "4", ...},
             {"mode": "PAPER", "version": "5", ...} ],
   "divergence": [ {"a": "LIVE", "b": "PAPER", "version": "4", "paired": 9,
                    "only_a": 1, "only_b": 2,
                    "entry_slip_bps": 3.4, "exit_slip_bps": 1.2, "r_diff": -0.08} ] }]}
```
Pure logic lives in `app/orders/compare.py` (unit-tested, no DB):
- `group_stats(trades)` — per (strategy name, symbol, tf) → per (mode, version) stats.
  R per trade = net pnl / (|entry − init_sl| × qty) (same 1R definition as Trade results).
- `pair_trades(a, b, window_ms)` — greedy nearest-time matching, same side, `|Δopen| ≤ window`
  (window = 1 TF candle). Each trade is used at most once.
- Divergence is computed only between modes running the **same version**
  (LIVE↔PAPER, LIVE↔TESTNET, TESTNET↔PAPER). Slippage sign: positive bps = A got a *worse*
  price than B (adverse), for both entry and exit, side-aware.

The strategy "name" and "version" come from the position snapshot (`position.strategy`,
e.g. `"ict_po3 v4"`), so results survive bot deletion. Manual trades (no strategy) are excluded.

### 4.2 Frontend

State: new Zustand store `lib/modeLens.ts`
```ts
type Lens = "" | "PAPER" | "TESTNET" | "LIVE";
useModeLens: { lens: Lens; setLens(l: Lens): void }   // persisted in localStorage("gtic.lens")
```
Zustand (not React Query) because it is client UI state shared by every page. Query keys include
the lens so React Query caches each world separately.

| Place | Behaviour under lens |
|---|---|
| Header | `ModeLens` segmented control + per-mode running-bot count from `/modes/summary`; colored stripe under the header (amber TESTNET, red LIVE) |
| Overview (new, `/overview`) | 3 mode cards; clicking a card sets the lens and opens Trading |
| Trading | bot list filtered (client-side, one cache); *Create bot* mode follows the lens; positions filtered; bot row action **Clone to…** |
| Orders | positions / trade results / fill history all use the lens (the per-table Mode selects are replaced by the global lens); "Showing X only · Show all modes" note on top |
| Account | account tabs filtered to the lens mode; *New account* mode defaults to the lens |
| Compare (new, `/compare`) | not filtered — it is the cross-mode view by design (lens only highlights) |
| Audit | filtered |
| Realtime positions (WS) | filtered client-side by `msg.mode` |

Clone: the bot row's **Clone to…** menu (Paper / Testnet / Live) pre-fills the *Create bot* form
with the bot's strategy version, symbol, TF, params and sizing, and the target mode; the user then
presses *Create*. Reusing the form keeps every guard (LIVE modal, account/mode check) in one path —
no new backend endpoint.

### 4.3 Safety

- Lens = view filter only; it never changes which bots run or where orders go.
- LIVE lens shows a persistent red stripe "LIVE — real money" so it is impossible to mistake.
- Cloning to LIVE goes through `EnableLiveModal` + backend `ENABLE_LIVE` check, as before.
- Compare reads closed positions only.

## 5. UI design (ASCII)

### 5.1 Header with mode lens
```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ [logo] GTIC  Overview Chart Library Trading Orders Compare Account Backtest …        │
│                         ┌─────┬────────┬──────────┬────────┐                          │
│                         │ All │ Paper 2│ Testnet 1│ Live 0 │   v1.x  VI  ☾  ● OK      │
│                         └─────┴────────┴──────────┴────────┘                          │
├══════════════════════════ TESTNET — exchange sandbox ════════════════════════════════┤ ← amber stripe
```
(LIVE: red stripe "LIVE — real money". All/Paper: no stripe.) Numbers = running bots.
On mobile the segmented control wraps to its own row under the nav.

### 5.2 Overview
```
┌─ PAPER ──────────────────┐ ┌─ TESTNET ────────────────┐ ┌─ LIVE ───────────────────┐
│ Paper main   1,020.44 $  │ │ Testnet     4,980.10 $   │ │ no LIVE account          │
│ Bots  ● 2 run · 1 stop   │ │ Bots  ● 1 run            │ │ Bots  —                  │
│ Open  1 pos · risk $12   │ │ Open  0                  │ │ Open  —                  │
│ Today 3 trades  +$4.10   │ │ Today 1 trade   −$1.20   │ │                          │
│ 7d   14 tr · 57% · +3.4R │ │ 7d    5 tr · 40% · −0.6R │ │                          │
│                 [Open →] │ │                 [Open →] │ │  (ENABLE_LIVE=1 needed)  │
└──────────────────────────┘ └──────────────────────────┘ └──────────────────────────┘
```

### 5.3 Compare
```
Compare modes & versions   Period [7d|30d|90d|All]   Symbol [_______]

ict_po3 · SUIUSDT · 15m
 Mode     Ver  Trades  Win%   Total R  Avg R   PnL      Fees
 LIVE     v4     10     60%   +3.20R   +0.32  +$41.00  $3.10
 PAPER    v4     12     58%   +4.10R   +0.34  +$2.05   $0.20   ← shadow
 PAPER    v5      9     67%   +4.80R   +0.53  +$2.40   $0.15   ← candidate
 Divergence (same version)
 LIVE vs PAPER v4   paired 9 · only LIVE 1 · only PAPER 3
                    entry slip +3.4 bps · exit slip +1.2 bps · R diff −0.08R/trade
```

### 5.4 Clone
```
 [LIVE] ict_po3 v4  SUIUSDT · 15m  ● RUNNING  …        ▶ ⏸ ■ ⧉Clone ▾  🗑
                                                         ├ to PAPER   (shadow)
                                                         ├ to TESTNET
                                                         └ to LIVE    (needs confirm)
```

## 6. Test plan
- `tests/test_compare.py`: grouping/stats, R, pairing window & side, one-to-one matching,
  slippage sign for LONG/SHORT, version isolation.
- API smoke: `/api/modes/summary`, `/api/compare`, mode filters on bots/positions/audit.
- UI: switch the lens → every page filters; LIVE stripe; clone pre-fills the form.
