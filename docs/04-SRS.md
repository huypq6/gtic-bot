# SRS — Technical Design & Schema
### Binance Trading Bot Platform · single-user · Python thuần

Liên kết: [BRD](01-BRD.md) · [URD](02-URD.md) · [Plan](00-Plan.md)

---

## 1. Quyết định đã chốt (ràng buộc thiết kế)
- Một sàn: **python-binance**.
- **Postgres + TimescaleDB** (hypertable cho klines).
- Chart: **Lightweight Charts trước** (npm, miễn phí, dùng ngay) → **swap Charting Library** khi có public URL + được duyệt repo (để có drawing tools). Tách qua **datafeed adapter** để swap không đụng backend.
- Strategy **file-based, sửa ngoài app**; app chỉ load/run; UI chỉ chỉnh params + chọn version.

---

## 2. Kiến trúc runtime (single process, asyncio)

```
                         FastAPI (1 process)
  ┌──────────────────────────────────────────────────────────┐
  │  startup → tạo các asyncio task:                          │
  │                                                           │
  │  ① MarketFeed ── Binance WS ──► EventBus(asyncio.Queue)   │
  │                                     │                     │
  │  ② StrategyRunner (1 task/bot) ◄────┘                     │
  │        on_candle(ctx) → Signal ─►                         │
  │  ③ Executor (Paper|Testnet|Live) ─► đặt/hủy/sửa lệnh      │
  │        │                                                  │
  │  ④ OrderManager ── state + audit ─► Postgres              │
  │        │                                                  │
  │  ⑤ WSGateway ── broadcast giá + order ─► Frontend         │
  │                                                           │
  │  ⑥ Scanner (task định kỳ) ─► đề xuất ─► EventBus          │
  └──────────────────────────────────────────────────────────┘
```

EventBus = pub/sub in-memory trên `asyncio.Queue` (topic: `kline.{symbol}`, `signal`, `order.update`, `scan`). Đủ cho single-user; chừa cửa thay bằng Redis nếu cần.

---

## 3. Interface cốt lõi (chạy chung 4 mode)

```python
# strategy/base.py
@dataclass
class Signal:
    action: str            # BUY|SELL|CLOSE|CANCEL
    symbol: str
    size: float
    order_type: str = "MARKET"   # MARKET|LIMIT
    price: float | None = None   # cho LIMIT
    sl: float | None = None
    tp: float | None = None

@dataclass
class Context:               # engine bơm vào, strategy chỉ đọc
    symbol: str
    price: float
    candles: list            # OHLCV gần nhất
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
# execution/base.py — đổi adapter = đổi mode, strategy không biết
class Executor(ABC):
    @abstractmethod
    async def submit(self, signal: Signal) -> Order: ...
    @abstractmethod
    async def cancel(self, order_id: str) -> None: ...
    @abstractmethod
    async def modify_sltp(self, position_id, sl, tp) -> None: ...
# Paper: khớp nội bộ theo giá WS.  Testnet/Live: python-binance.
```

**Strategy registry (file-based):** mỗi file trong `strategies/` đăng ký class qua decorator; app quét, đọc `name+version+default_params`, sync vào bảng `strategy`.

---

## 4. Schema Postgres

### 4.1 ERD (rút gọn)
```
strategy ──< bot >── (mode, symbol)
   bot ──< order >── audit_log
   bot ──< position >
   bot ──< backtest_run >── backtest_trade
kline (timescale hypertable)        scan_result
```

### 4.2 DDL

```sql
-- Klines: hypertable cho dữ liệu lịch sử + realtime
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

-- Chiến thuật (sync từ file registry)
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

-- Bot = instance chạy 1 strategy + params + mode trên 1 symbol
CREATE TABLE bot (
  id           SERIAL PRIMARY KEY,
  strategy_id  INT REFERENCES strategy(id),
  symbol       TEXT NOT NULL,
  tf           TEXT NOT NULL DEFAULT '1h',
  mode         TEXT NOT NULL CHECK (mode IN ('PAPER','TESTNET','LIVE')),
  params       JSONB NOT NULL DEFAULT '{}',   -- override default_params
  status       TEXT NOT NULL DEFAULT 'STOPPED' -- RUNNING|PAUSED|STOPPED
                 CHECK (status IN ('RUNNING','PAUSED','STOPPED')),
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- Lệnh (bot tự động hoặc tay)
CREATE TABLE "order" (
  id          SERIAL PRIMARY KEY,
  bot_id      INT REFERENCES bot(id),          -- NULL nếu lệnh tay rời
  ext_id      TEXT,                            -- id sàn (testnet/live)
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

-- Vị thế mở/đóng
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

-- Audit log mọi hành động (NFR truy vết)
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
GET    /strategies                 # list (sync từ file)
POST   /bots                       # tạo bot {strategy_id,symbol,tf,mode,params}
PATCH  /bots/{id}                  # pause/resume/stop, đổi params
DELETE /bots/{id}
GET    /positions                  # vị thế mở
POST   /positions/{id}/close       # đóng tay
PATCH  /positions/{id}/sltp        # sửa SL/TP tay
POST   /orders                     # đặt lệnh tay
DELETE /orders/{id}                # hủy
POST   /backtest                   # chạy {strategy_id,params,symbol,tf,from,to}
GET    /backtest/{run_id}
GET    /scan                       # kết quả scanner
GET    /audit                      # log
POST   /klines/sync                # tải lịch sử về Postgres
```

### WebSocket (FastAPI `/ws`)
Server → client push:
```
{type:"kline",   symbol, tf, ohlcv}
{type:"ticker",  symbol, price, pct}
{type:"order",   order}        # cập nhật trạng thái lệnh
{type:"position",position}     # PnL realtime
{type:"feed",    status}       # OK|RECONNECTING|DOWN
{type:"scan",    results}
```

---

## 6. Đáp ứng NFR
| NFR | Cơ chế |
|---|---|
| Realtime < 1s | Binance WS (không poll) → EventBus → WSGateway |
| Không treo lệnh limit | Mỗi LIMIT tạo `asyncio.create_task` auto-cancel sau `params.timeout` |
| Mất feed | WS auto-reconnect; khi DOWN → bot auto-pause + push `feed:DOWN` |
| Responsive | React breakpoints; mobile tab bar |
| An toàn Live | mode='LIVE' cần cờ env `ENABLE_LIVE=1` + modal confirm gõ "LIVE" |

---

## 7. An toàn & cấu hình
```
.env
  BINANCE_KEY / BINANCE_SECRET          # live, tắt quyền rút, whitelist IP VPS
  BINANCE_TESTNET_KEY / _SECRET
  ENABLE_LIVE=0                         # phải =1 mới cho mode LIVE
  DATABASE_URL=postgresql://...
```
- Key mã hóa khi lưu (nếu lưu DB); ưu tiên chỉ trong env/secret manager.
- Mọi `Executor.submit` ghi `audit_log` trước khi gọi sàn.

---

## 8. Cấu trúc thư mục (chốt)
```
app/
├── main.py
├── config.py
├── db.py                  # SQLAlchemy + Timescale
├── market/  feed.py  bus.py
├── strategy/ base.py  registry.py  runner.py
│            strategies/ ema_cross.py  rsi_rev.py  ...   # SỬA Ở ĐÂY
├── execution/ base.py  paper.py  testnet.py  live.py
├── orders/   manager.py  models.py
├── backtest/ engine.py
├── scanner/  research.py
└── api/      routes.py  ws.py
frontend/ (React + TradingView Charting Library)
docker-compose.yml   # app + postgres(timescale)
```

---

## 9. Bước tiếp theo (code)
Bắt đầu **Phase 1**: `db.py` + migration schema → `market/feed.py` (Binance WS) → `api/ws.py` → React chart nhận feed. Sau đó Phase 2 (Strategy base + Paper executor).
