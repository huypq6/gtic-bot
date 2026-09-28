# BRD — Business Requirements Document
### Trading Bot Automation for Binance

| Item | Details |
|---|---|
| Project name | Binance Trading Bot Platform |
| Document version | 1.0 |
| System type | Web app (pure Python, single-user) |
| Deployment scope | 1 user, self-hosted (VPS / personal machine) |
| Status | Draft |

---

## 1. Context & Business Objectives

### 1.1 Problem
Manual trading on Binance is time-consuming, prone to emotional decisions, hard to keep disciplined, and makes it impossible to watch many pairs 24/7. The user needs a personal platform to:
- Automate strategies with disciplined, algorithmic rules.
- Validate strategies **before** committing real money (backtest + simulation).
- Monitor in realtime, close to the exchange, without leaving orders hanging too long.
- Still retain the ability to intervene manually when needed.

### 1.2 Business Goals
| ID | Goal | Success measure |
|---|---|---|
| BG-1 | Reduce risk when trying new strategies | 100% of strategies go through backtest + paper before going live |
| BG-2 | Automate disciplined execution | The bot enters/exits trades algorithmically with no manual action |
| BG-3 | Shorten the strategy research loop | Edit algorithm → backtest → see results within minutes |
| BG-4 | Capital preservation | No losses due to wrong-environment mistakes / hanging orders |
| BG-5 | Scale to multiple strategy versions | Run ≥ 3 versions in parallel, compare performance |

### 1.3 Out of Scope
- Multi-user, permissions, billing.
- HFT / millisecond scalping (sub-ms latency).
- Multi-exchange (Binance only; design leaves room for ccxt later).
- Automated financial management / tax accounting.
- Native mobile app (responsive web only).

---

## 2. Business Requirements

### 2.1 Core functionality
| ID | Requirement | Priority |
|---|---|---|
| BR-1 | Display realtime candlestick charts like a mainstream exchange (candles, volume, indicators) | Must |
| BR-2 | Trade on the exchange's safe environment (Binance Testnet) | Must |
| BR-3 | Simulated (paper) trading: real data, orders placed & tracked internally | Must |
| BR-4 | Backtest on historical data | Must |
| BR-5 | Trade management + manual intervention (close/modify SL-TP, pause) | Must |
| BR-6 | Pair research & entry suggestions (scanner) | Should |
| BR-7 | Strategies with editable algorithms + multiple versions | Must |
| BR-8 | Audit log for all automated & manual orders | Must |

### 2.2 Business constraints
| ID | Constraint |
|---|---|
| BC-1 | Live trading must require a dedicated enable flag + confirmation, fully separated from paper/testnet |
| BC-2 | Live API key: withdrawals disabled, IP whitelist |
| BC-3 | The same strategy code must run on backtest / paper / live |
| BC-4 | Limit orders must not stay open beyond a configured threshold (auto-cancel) |

---

## 3. Operating Modes (4 Trading Modes)

| Mode | Price data | Order placement | Money | Purpose |
|---|---|---|---|---|
| **Backtest** | Historical (klines) | Simulated in the engine | Virtual | Validate the algorithm on past data |
| **Paper** | Real realtime | Matched internally (no exchange calls) | Virtual | Realtime validation on real data |
| **Testnet** | Testnet realtime | Real (testnet.binance) | Virtual | Test real order-placement integration |
| **Live** | Real realtime | Real (production) | **Real** | Trade for real |

---

## 4. Expected Benefits
- **Lower risk:** filter out weak strategies via backtest + paper before losing money.
- **Discipline:** eliminate emotional trading.
- **Research speed:** edit the algorithm and see results quickly.
- **Operational safety:** clear boundaries between modes, preventing accidental real orders.

---

## 5. Risks & Mitigation

| ID | Risk | Level | Mitigation |
|---|---|---|---|
| RK-1 | Accidentally running Live instead of Paper → losing money | High | Dedicated flag + confirmation + warning colors in the UI |
| RK-2 | Limit orders left hanging unfilled | Medium | Auto-cancel on configured timeout |
| RK-3 | Loss of WS connection to the exchange | High | Auto-reconnect + pause bot on feed loss |
| RK-4 | Logic drift between backtest and live | High | Shared Strategy/Context interface |
| RK-5 | API key leak | High | Encrypted storage, withdrawals disabled, IP whitelist |
| RK-6 | Paper slippage/fees differ from reality | Medium | Simulate fees + assumed slippage |

---

## 6. Success Criteria (Acceptance)
1. Realtime chart updates < 1s behind the exchange.
2. One strategy runs on all 4 modes without code changes.
3. Backtest returns PnL, win rate, drawdown.
4. Orders can be closed/modified manually while the bot is running.
5. Every order has a traceable audit log.
6. Live cannot be entered without enabling the flag + confirming.
