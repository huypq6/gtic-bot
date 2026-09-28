# SRS — Technical Design & Schema
### Binance Trading Bot Platform · single-user · pure Python

Links: [BRD](01-BRD.md) · [URD](02-URD.md) · [Plan](00-Plan.md)

---

## 1. Locked decisions (design constraints)
- Single exchange: **python-binance**.
- **Postgres + TimescaleDB** (hypertable for klines).
- Chart: **Lightweight Charts first** (npm, free, usable right away) → **swap to the Charting Library** once there is a public URL + repo access is approved (to get drawing tools). Isolated behind a **datafeed adapter** so the swap does not touch the backend.
- Strategies are **file-based and edited outside the app**; the app only loads/runs them; the UI only edits params + selects a version.

---

## 2. Runtime architecture (single process, asyncio)

```
                         FastAPI (1 process)
  ┌──────────────────────────────────────────────────────────┐
  │  startup → create asyncio tasks:                          │
  │                                                           │
  │  ① MarketFeed ── Binance WS ──► EventBus(asyncio.Queue)   │
  │                                     │                     │
  │  ② StrategyRunner (1 task/bot) ◄────┘                     │
  │        on_candle(ctx) → Signal ─►                         │
  │  ③ Executor (Paper|Testnet|Live) ─► place/cancel/modify   │
  │        │                                                  │
  │  ④ OrderManager ── state + audit ─► Postgres              │
  │        │                                                  │
  │  ⑤ WSGateway ── broadcast price + order ─► Frontend       │
  │                                                           │
  │  ⑥ Scanner (periodic task) ─► suggestions ─► EventBus     │
  └──────────────────────────────────────────────────────────┘
```

EventBus = in-memory pub/sub on top of `asyncio.Queue` (topics: `kline.{symbol}`, `signal`, `order.update`, `scan`). Sufficient for single-user; leaves the door open to swap in Redis if needed.

---

## 3. Core interfaces (shared across all 4 modes)

```python
# strategy/base.py
@dataclass
class Signal:
    action: str            # BUY|SELL|CLOSE|CANCEL
    symbol: str
    size: float
    order_type: str = "MARKET"   # MARKET|LIMIT
    price: float | None = None   # for LIMIT
    sl: float | None = None
    tp: float | None = None

@dataclass
class Context:               # injected by the engine, read-only for the strategy
    symbol: str
    price: float
    candles: list            # most recent OHLCV
    position: Position | None
    indicators: dict
    now: datetime

class Strategy(ABC):
    name: str
    version: str
    default_params: dict
    def __init__(self, params: dict): self.params = {**self.default_params, **params}
    @abstractmethod
    def on_candle(self, ctx: Context) -> list[Signal]: ...
```

```python
# execution/base.py — swap the adapter = swap the mode; the strategy is unaware
class Executor(ABC):
    @abstractmethod
    async def submit(self, signal: Signal) -> Order: ...
    @abstractmethod
    async def cancel(self, order_id: str) -> None: ...
    @abstractmethod
    async def modify_sltp(self, position_id, sl, tp) -> None: ...
# Paper: fills internally at the WS price.  Testnet/Live: python-binance.
```

**Strategy registry (file-based):** each file in `strategies/` registers its class via a decorator; the app scans them, reads `name+version+default_params`, and syncs them into the `strategy` table.

---

## 4. Postgres schema

### 4.1 ERD (simplified)
```
strategy ──< bot >── (mode, symbol)
   bot ──< order >── audit_log
   bot ──< position >
   bot ──< backtest_run >── backtest_trade
kline (timescale hypertable)        scan_result
```

### 4.2 DDL

```sql
-- Klines: hypertable for historical + realtime data
CREATE TABLE kline (
  symbol      TEXT        NOT NULL,
  tf          TEXT        NOT NULL,          -- 1m,5m,1h,1d
  ts          TIMESTAMPTZ NOT NULL,
  open        NUMERIC     NOT NULL,
  high        NUMERIC     NOT NULL,
  low         NUMERIC     NOT NULL,
  close       NUMERIC     NOT NULL,
  volume      NUMERIC     NOT NULL,
  PRIMARY KEY (symbol, tf, ts)
);
SELECT create_hypertable('kline','ts', chunk_time_interval => INTERVAL '7 days');

-- Strategies (synced from the file registry)
CREATE TABLE strategy (
  id             SERIAL PRIMARY KEY,
  name           TEXT NOT NULL,
  version        TEXT NOT NULL,
  default_params JSONB NOT NULL DEFAULT '{}',
  source_file    TEXT,
  is_active      BOOLEAN DEFAULT TRUE,
  created_at     TIMESTAMPTZ DEFAULT now(),
  UNIQUE (name, version)
);

-- Bot = an instance running 1 strategy + params + mode on 1 symbol
CREATE TABLE bot (
  id           SERIAL PRIMARY KEY,
  strategy_id  INT REFERENCES strategy(id),
  symbol       TEXT NOT NULL,
  tf           TEXT NOT NULL DEFAULT '1h',
  mode         TEXT NOT NULL CHECK (mode IN ('PAPER','TESTNET','LIVE')),
  params       JSONB NOT NULL DEFAULT '{}',   -- overrides default_params
  status       TEXT NOT NULL DEFAULT 'STOPPED' -- RUNNING|PAUSED|STOPPED
                 CHECK (status IN ('RUNNING','PAUSED','STOPPED')),
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- Orders (automated by a bot or manual)
CREATE TABLE "order" (
  id          SERIAL PRIMARY KEY,
  bot_id      INT REFERENCES bot(id),          -- NULL for a standalone manual order
  ext_id      TEXT,                            -- exchange id (testnet/live)
  source      TEXT NOT NULL CHECK (source IN ('BOT','MANUAL','SYSTEM')),
  mode        TEXT NOT NULL,
  symbol      TEXT NOT NULL,
  side        TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
  type        TEXT NOT NULL CHECK (type IN ('MARKET','LIMIT')),
  qty         NUMERIC NOT NULL,
  price       NUMERIC,
  status      TEXT NOT NULL                    -- NEW|FILLED|CANCELLED|REJECTED
                CHECK (status IN ('NEW','FILLED','PARTIAL','CANCELLED','REJECTED')),
  sl          NUMERIC, tp NUMERIC,
  filled_qty  NUMERIC DEFAULT 0,
  avg_price   NUMERIC,
  fee         NUMERIC DEFAULT 0,
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Open/closed positions
CREATE TABLE position (
  id          SERIAL PRIMARY KEY,
  bot_id      INT REFERENCES bot(id),
  mode        TEXT NOT NULL,
  symbol      TEXT NOT NULL,
  side        TEXT NOT NULL CHECK (side IN ('LONG','SHORT')),
  qty         NUMERIC NOT NULL,
  entry_price NUMERIC NOT NULL,
  sl          NUMERIC, tp NUMERIC,
  status      TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED')),
  exit_price  NUMERIC,
  pnl         NUMERIC,
  opened_at   TIMESTAMPTZ DEFAULT now(),
  closed_at   TIMESTAMPTZ
);

-- Audit log of every action (traceability NFR)
CREATE TABLE audit_log (
  id         BIGSERIAL PRIMARY KEY,
  ts         TIMESTAMPTZ DEFAULT now(),
  source     TEXT NOT NULL,     -- BOT|MANUAL|SYSTEM
  mode       TEXT,
  bot_id     INT,
  symbol     TEXT,
  action     TEXT NOT NULL,     -- OPEN|CLOSE|EDIT_SLTP|CANCEL|PAUSE|RESUME|RECONNECT
  detail     JSONB
);

-- Backtest
CREATE TABLE backtest_run (
  id          SERIAL PRIMARY KEY,
  strategy_id INT REFERENCES strategy(id),
  params      JSONB, symbol TEXT, tf TEXT,
  from_ts     TIMESTAMPTZ, to_ts TIMESTAMPTZ,
  capital     NUMERIC, fee_rate NUMERIC,
  pnl_pct     NUMERIC, winrate NUMERIC, max_dd NUMERIC, sharpe NUMERIC,
  n_trades    INT,
  equity_curve JSONB,           -- [[ts,equity],...]
  created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE backtest_trade (
  id        SERIAL PRIMARY KEY,
  run_id    INT REFERENCES backtest_run(id) ON DELETE CASCADE,
  side      TEXT, entry_ts TIMESTAMPTZ, entry NUMERIC,
  exit_ts   TIMESTAMPTZ, exit NUMERIC, pnl_pct NUMERIC
);

-- Scanner
CREATE TABLE scan_result (
  id        SERIAL PRIMARY KEY,
  ts        TIMESTAMPTZ DEFAULT now(),
  symbol    TEXT, score NUMERIC, signal TEXT, reason TEXT
);
```

---

## 5. API (REST + WebSocket)

### REST
```
GET    /strategies                 # list (synced from files)
POST   /bots                       # create a bot {strategy_id,symbol,tf,mode,params}
PATCH  /bots/{id}                  # pause/resume/stop, change params
DELETE /bots/{id}
GET    /positions                  # open positions
POST   /positions/{id}/close       # manual close
PATCH  /positions/{id}/sltp        # manually edit SL/TP
POST   /orders                     # place a manual order
DELETE /orders/{id}                # cancel
POST   /backtest                   # run {strategy_id,params,symbol,tf,from,to}
GET    /backtest/{run_id}
GET    /scan                       # scanner results
GET    /audit                      # log
POST   /klines/sync                # download history into Postgres
```

### WebSocket (FastAPI `/ws`)
Server → client push:
```
{type:"kline",   symbol, tf, ohlcv}
{type:"ticker",  symbol, price, pct}
{type:"order",   order}        # order status update
{type:"position",position}     # realtime PnL
{type:"feed",    status}       # OK|RECONNECTING|DOWN
{type:"scan",    results}
```

---

## 6. Meeting the NFRs
| NFR | Mechanism |
|---|---|
| Realtime < 1s | Binance WS (no polling) → EventBus → WSGateway |
| No stale limit orders | Each LIMIT order spawns an `asyncio.create_task` that auto-cancels it after `params.timeout` |
| Feed loss | WS auto-reconnect; when DOWN → bots auto-pause + push `feed:DOWN` |
| Responsive | React breakpoints; mobile tab bar |
| Live safety | mode='LIVE' requires env flag `ENABLE_LIVE=1` + a confirm modal where you type "LIVE" |

---

## 7. Security & configuration
```
.env
  BINANCE_KEY / BINANCE_SECRET          # live; withdrawals disabled, VPS IP whitelisted
  BINANCE_TESTNET_KEY / _SECRET
  ENABLE_LIVE=0                         # must be =1 to allow LIVE mode
  DATABASE_URL=postgresql://...
```
- Keys are encrypted at rest (if stored in the DB); prefer keeping them only in env/a secret manager.
- Every `Executor.submit` writes to `audit_log` before calling the exchange.

---

## 8. Directory structure (locked)
```
app/
├── main.py
├── config.py
├── db.py                  # SQLAlchemy + Timescale
├── market/  feed.py  bus.py
├── strategy/ base.py  registry.py  runner.py
│            strategies/ ema_cross.py  rsi_rev.py  ...   # EDIT HERE
├── execution/ base.py  paper.py  testnet.py  live.py
├── orders/   manager.py  models.py
├── backtest/ engine.py
├── scanner/  research.py
└── api/      routes.py  ws.py
frontend/ (React + TradingView Charting Library)
docker-compose.yml   # app + postgres(timescale)
```

---

## 9. Next steps (code)
Start with **Phase 1**: `db.py` + schema migration → `market/feed.py` (Binance WS) → `api/ws.py` → React chart consuming the feed. Then Phase 2 (Strategy base + Paper executor).
