# URD — User Requirements Document
### Trading Bot Automation for Binance

| Item | Details |
|---|---|
| Version | 1.0 |
| Audience | Single user (trader and developer) |
| Related | BRD v1.0 |

---

## 1. Persona

**Trader-Developer (system owner)**
- Writes/edits strategies in Python themselves.
- Wants to monitor many pairs in realtime on both desktop and mobile.
- Needs thorough validation before using real money.
- Prioritizes control: wants to be able to intervene manually at any time.

---

## 2. User Stories (by functional area)

### 2.1 Charts & Market Monitoring
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-01 | As a user, I want to view realtime candlestick charts like the exchange's for analysis | Candles/volume update in realtime, switchable timeframe (1m–1D), zoom/pan |
| US-02 | I want to add indicators (EMA, RSI, MACD…) to the chart | Overlay/subpane indicators, toggleable |
| US-03 | I want to see multiple pairs in a watchlist | List of pairs + price + realtime % change |
| US-04 | I want to see the bot's entry/exit points on the chart | Buy/sell markers + SL/TP shown on the candles |

### 2.2 Strategy
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-05 | I want to write/edit strategy algorithms in Python | Add a strategy file, hot-reload or reload supported |
| US-06 | I want to tune strategy params from the UI without editing code | Params form (fast/slow/threshold…), saved to DB |
| US-07 | I want to manage multiple versions of a strategy | Each version has name+version+params, run in parallel |
| US-08 | I want to compare performance across versions | Comparison table of PnL/win rate/drawdown by version |

### 2.3 Backtest
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-09 | I want to backtest a strategy on historical data | Choose pair + timeframe + date range → run |
| US-10 | I want to see backtest results visually | Equity curve, trade list, metrics (PnL, win rate, MDD, Sharpe) |
| US-11 | I want to see backtest trades plotted on the chart | Entry/exit markers on the historical chart |

### 2.4 Trading (Paper / Testnet / Live)
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-12 | I want to run the bot in simulated (paper) mode with real data | Orders matched internally, realtime PnL, no exchange calls |
| US-13 | I want to run the bot on the exchange Testnet | Real orders on testnet.binance |
| US-14 | I want to enable Live with safety guardrails | Dedicated flag + confirmation + color warning |
| US-15 | I want to clearly choose a mode for each bot | Prominent mode badge (PAPER/TESTNET/LIVE) |

### 2.5 Order Management & Manual Intervention
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-16 | I want to see all open positions + PnL | Realtime positions table |
| US-17 | I want to close a trade manually | Close button → executor closes immediately |
| US-18 | I want to edit SL/TP manually | SL/TP edits apply immediately |
| US-19 | I want to pause/resume a bot | Toggle; the bot stops generating new orders |
| US-20 | I want to place manual orders alongside the bot | Manual market/limit order form |
| US-21 | I want to view history & an audit log of all orders | Log table: time, source (bot/manual), action |

### 2.6 Research & Suggestions
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-22 | I want the system to scan pairs and suggest entries | Scanner runs periodically, lists pairs + score + signal |
| US-23 | I want to quickly open a chart/place an order from a suggestion | Click a suggestion → open chart/prefill order |

### 2.7 Non-functional (from the user's perspective)
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-24 | I want access from both phone and computer | Responsive web |
| US-25 | I want data close to the exchange in realtime | Updates < 1s, WS with no polling |
| US-26 | I don't want limit orders left hanging for long | Auto-cancel on timeout |
| US-27 | I want to be warned when the exchange connection is lost | Warning banner + bot auto-pause |

---

## 3. Permission Matrix by Mode (safety)

| Action | Backtest | Paper | Testnet | Live |
|---|---|---|---|---|
| Runs without extra confirmation | ✅ | ✅ | ✅ | ❌ (requires flag + confirm) |
| Real money | ❌ | ❌ | ❌ | ✅ |
| Manual intervention | ✅ | ✅ | ✅ | ✅ |
| UI warning color | — | green | yellow | red |

---

## 4. Main User Flows

**Flow A — Trying a new strategy (safe → real):**
```
Write/edit strategy → Backtest → review metrics → tune params
   → Paper trade (realtime) → meets expectations → Testnet → Live (enable flag)
```

**Flow B — Monitoring & intervention:**
```
Dashboard → see positions + PnL → anomaly → Close/Edit SL-TP
   or Pause bot → write audit log
```

**Flow C — From suggestion to order:**
```
Scanner suggests a pair → open chart to check → place manual order
   or assign it to a bot
```
