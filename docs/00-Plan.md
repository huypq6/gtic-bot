# Project Plan — Ghost Trader In Chair Bot

Document set:
1. [`01-BRD.md`](01-BRD.md) — Business Requirements
2. [`02-URD.md`](02-URD.md) — User Requirements + User Stories
3. [`03-ASCII-Mockups.md`](03-ASCII-Mockups.md) — Wireframes

---

## 1. Solution summary
A **pure-Python, single-user** web app, single-process (FastAPI + asyncio). One strategy interface runs across all 4 modes: **Backtest → Paper → Testnet → Live**. Realtime via WebSocket, with manual intervention possible at any time.

## 2. Finalized tech stack ✅
| Layer | Choice | Decision notes |
|---|---|---|
| Web/API | FastAPI (async, WebSocket) | |
| Exchange | **python-binance** | Single exchange → no need for ccxt |
| Internal realtime | asyncio.Queue (in-memory EventBus) | |
| DB | **Postgres + TimescaleDB** | Committed to Postgres from day one to be safe; hypertable for klines |
| Backtest | vectorbt | |
| Chart | **Lightweight Charts first → Charting Library later** | Applying for the Charting Library requires a public URL (not available at first). Use Lightweight Charts right away (npm, free), swap once there is a domain + approval. Drawing tools only become available after the swap. |
| Frontend | React (responsive) | |
| Strategy | **File-based, edited outside the app** | The app only loads & runs; the UI only edits params, no code editor |
| Deploy | Docker Compose (app + postgres) / VPS close to Binance | |

## 3. Module map
```
app/
├── market/      feed.py (Binance WS), bus.py (EventBus)
├── strategy/    base.py (ABC+Context), runner.py, strategies/*.py
├── execution/   base.py, paper.py, testnet.py, live.py
├── orders/      manager.py (state+audit), models.py
├── backtest/    engine.py (vectorbt)
├── scanner/     research.py
├── api/         ws.py, routes.py
└── db.py
```

## 4. Roadmap (by phase, reducing risk step by step)

| Phase | Item | User Stories | Outcome |
|---|---|---|---|
| **P1** | Market feed + realtime chart | US-01,02,03,24,25 | Live chart that tracks the exchange closely |
| **P2** | Strategy base + Paper executor | US-05,12,16 | Paper bot running, realtime PnL |
| **P3** | Order Manager + manual intervention | US-17,18,19,20,21 | Close/modify orders, audit log |
| **P4** | Backtest | US-09,10,11 | Metrics + equity curve |
| **P5** | Strategy versioning + params UI | US-06,07,08 | Multiple versions, tunable from the UI |
| **P6** | Testnet integration | US-13,15 | Real orders in a sandbox environment |
| **P7** | Scanner suggestions | US-22,23 | Pair scanning + signals |
| **P8** | Live + safety guardrails | US-14,26,27 | Live behind a flag + confirmation |

> Intentional ordering: safety (paper/backtest) first, real money (live) last.

## 5. Notable architectural decisions
- **One Strategy/Context interface** for all 4 modes → no logic drift between backtest and live (risk RK-4).
- **Python is not on a complex order-placement hot path** because single-user load is low → asyncio is enough, no need for Go/NATS at this stage.
- **Mode boundaries via config + a separate Live flag** → prevents accidental real orders (RK-1).
- **Auto-cancel limit orders on timeout** → NFR "don't leave orders open too long" (RK-2).

## 6. Finalized decisions ✅
1. **Single exchange** → python-binance, drop the ccxt abstraction layer.
2. **Postgres + TimescaleDB** from the start (no SQLite).
3. **Chart: Lightweight Charts first, Charting Library later.** Reason: the Charting Library application form requires a public URL/domain (not available during development). Lightweight Charts installs straight from npm, free. Once deployed with a domain + repo approval → swap to the Charting Library to get **drawing tools**.
4. **Strategies are edited outside the app** (in the repo/IDE); the app only loads & runs them. The UI only edits params + selects a version, **no in-app code editor**.

### Architectural consequences of (4)
- Strategy = a `.py` file in `app/strategy/strategies/`, registered via the registry.
- The app loads the module → reads metadata (name, version, default params) → saves/syncs to the DB.
- Changing the algorithm = edit the file + reload; light behavior tweaks = change params from the UI.
- Versioning: bumping `version` in the file is the source of truth; the DB stores the version + params of the running instance.
