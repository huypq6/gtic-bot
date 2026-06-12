# IMPLEMENTATION PLAN — Binance Trading Bot Platform

> Kế hoạch thực thi chi tiết, có theo dõi tiến độ. Đọc cùng `CLAUDE.md`, `docs/00-Plan.md`, `docs/04-SRS.md`.
> **Quy ước trạng thái:** ⬜ Chưa làm · 🟡 Đang làm · ✅ Xong · ⏸️ Tạm dừng · ❌ Bỏ
> Cập nhật cột Status + ô `% Done` + tick `- [ ]` mỗi khi tiến hành. Ghi mốc vào [Changelog](#changelog) cuối file.

---

## 0. Quyết định nền (chốt ở bước plan)

| Hạng mục | Quyết định | Ghi chú |
|---|---|---|
| Repo | **Monorepo 1 repo**: `app/` (backend) + `frontend/` chung | |
| Dev runtime | **Vite (:5173) proxy `/api` + `/ws` → FastAPI (:8000)** | Giữ HMR React + `uvicorn --reload`. Mở **http://localhost:5173** |
| Prod runtime | **FastAPI serve `frontend/dist` (StaticFiles) tại `/`** — 1 endpoint :8000 | Build qua Dockerfile multi-stage |
| Python env | **uv** — `.venv/` riêng cho project, `uv sync` từ `pyproject.toml` + `uv.lock` | Không đụng global/project khác |
| Migration | **Alembic** (schema) + `db/init/01-extensions.sql` (Timescale extension + hypertable) | |
| DB | **Postgres 16 + TimescaleDB** (image `timescale/timescaledb`) | |
| Backtest | **vectorbt** | |
| Chart | **lightweight-charts 5** trước → swap Charting Library sau (qua datafeed adapter) | |
| Live safety | `ENABLE_LIVE=0` mặc định; mode LIVE cần cờ=1 + modal gõ "LIVE" | |

---

## 1. Bảng tiến độ tổng

| Phase | Hạng mục | User Stories | Status | % Done |
|---|---|---|---|---|
| **P0** | Scaffold: monorepo, uv, Docker dev/prod, Alembic+Timescale, single-endpoint | — | ✅ | 100% |
| **P1** | Market feed + Chart realtime | US-01,02,03,24,25 | ⬜ | 0% |
| **P2** | Strategy base + Paper executor | US-05,12,16 | ⬜ | 0% |
| **P3** | Order Manager + can thiệp tay + audit | US-04,17,18,19,20,21 | ⬜ | 0% |
| **P4** | Backtest (vectorbt) | US-09,10,11 | ⬜ | 0% |
| **P5** | Strategy versioning + params UI | US-06,07,08 | ⬜ | 0% |
| **P6** | Testnet integration | US-13,15 | ⬜ | 0% |
| **P7** | Scanner đề xuất cặp | US-22,23 | ⬜ | 0% |
| **P8** | Live + rào chắn an toàn | US-14,26,27 | ⬜ | 0% |

> Thứ tự cố ý: **an toàn (paper/backtest) trước, tiền thật (live) sau cùng.** Không nhảy phase nếu DoD phase trước chưa đạt.

---

## 2. Cấu trúc thư mục mục tiêu (sau P0)

```
gtic-bot/
├── pyproject.toml            # uv: deps backend + tool config (ruff, pytest)
├── uv.lock
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/             # migration scripts
├── db/
│   └── init/
│       └── 01-extensions.sql # CREATE EXTENSION timescaledb; (chạy lúc Postgres init)
├── app/                      # === BACKEND ===
│   ├── main.py               # FastAPI app, lifespan: spawn asyncio tasks, mount static (prod)
│   ├── config.py             # pydantic-settings đọc .env
│   ├── db.py                 # SQLAlchemy async engine + session
│   ├── deps.py               # DI: get_session, get_bus...
│   ├── market/
│   │   ├── feed.py           # Binance WS → EventBus; auto-reconnect
│   │   └── bus.py            # EventBus (asyncio.Queue pub/sub)
│   ├── strategy/
│   │   ├── base.py           # Strategy ABC, Context, Signal, Position dataclass
│   │   ├── registry.py       # @register decorator + quét strategies/, sync DB
│   │   ├── runner.py         # StrategyRunner: 1 asyncio task/bot, gọi on_candle
│   │   └── strategies/
│   │       ├── ema_cross.py  # === SỬA CHIẾN THUẬT Ở ĐÂY ===
│   │       └── rsi_rev.py
│   ├── execution/
│   │   ├── base.py           # Executor ABC: submit/cancel/modify_sltp
│   │   ├── paper.py          # khớp nội bộ theo giá WS
│   │   ├── testnet.py        # python-binance testnet
│   │   └── live.py           # python-binance prod (rào chắn)
│   ├── orders/
│   │   ├── manager.py        # state machine + ghi audit TRƯỚC khi gọi sàn
│   │   └── models.py         # SQLAlchemy models (strategy, bot, order, position, audit_log, ...)
│   ├── backtest/
│   │   └── engine.py         # vectorbt
│   ├── scanner/
│   │   └── research.py       # task định kỳ → scan_result
│   └── api/
│       ├── routes.py         # REST (xem SRS §5)
│       └── ws.py             # WSGateway: broadcast kline/ticker/order/position/feed/scan
├── frontend/                 # === FRONTEND (React 19 + Vite 6 + Tailwind v4) ===
│   ├── vite.config.ts        # proxy /api + /ws → :8000
│   ├── package.json
│   ├── index.html
│   └── src/
│       ├── main.tsx  App.tsx  routes.tsx
│       ├── lib/      api.ts (react-query) ws.ts (zustand store)
│       ├── components/  chart/ watchlist/ orders/ ...
│       └── pages/    Dashboard Strategies Backtest Scanner Audit
├── tests/                    # pytest: paper engine, strategy logic, order state
│   ├── conftest.py
│   ├── test_paper_executor.py
│   ├── test_strategy_*.py
│   └── test_order_manager.py
├── Dockerfile                # multi-stage: build frontend → python+uv runtime
├── docker-compose.yml        # PROD: postgres + app (serve static, :8000)
├── docker-compose.dev.yml    # DEV: postgres + app(--reload) + vite (:5173)
├── .dockerignore  .gitignore
├── env.example  .env (gitignore)
└── docs/
```

---

## P0 — Scaffold & Hạ tầng môi trường

**Mục tiêu:** Khung repo chạy được end-to-end rỗng: `docker compose -f docker-compose.dev.yml up` → mở http://localhost:5173 thấy trang React gọi được `/api/health` (proxy sang FastAPI) và Postgres+Timescale sẵn sàng. `uv` cô lập venv.

### Tasks
- [x] `pyproject.toml` (uv): deps backend
  - runtime: `fastapi`, `uvicorn[standard]`, `python-binance`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic-settings`, `websockets`, `httpx`
  - dev group: `pytest`, `pytest-asyncio`, `ruff`, `anyio` · **`vectorbt`/`pandas`/`numpy` chuyển sang extra `backtest`** (deps nặng numba/llvmlite, cài ở P4: `uv sync --extra backtest`)
- [x] `uv venv && uv sync` → tạo `.venv/` riêng; `uv.lock` đã tạo (commit khi user duyệt)
- [x] `app/config.py`: `Settings(BaseSettings)` đọc `.env` (DATABASE_URL, BINANCE_*, ENABLE_LIVE, APP_HOST/PORT)
- [x] `app/db.py`: async engine + `async_session` factory + `Base`
- [x] `app/main.py`: FastAPI + `lifespan` (chỗ spawn task sau) + `app/api/routes.py` `GET /api/health` → `{status:"ok"}`. Prod: mount `StaticFiles("frontend/dist")` tại `/` (chỉ khi tồn tại)
- [x] Alembic: `alembic.ini` + `alembic/env.py` async (URL từ app.config) + `script.py.mako`; `versions/` rỗng (migration đầu tạo ở P1)
- [x] `db/init/01-extensions.sql`: `CREATE EXTENSION IF NOT EXISTS timescaledb;`
- [x] `frontend/` scaffold thủ công: React 19 + TS + Vite 6; Tailwind v4 (`@import "tailwindcss"`, plugin `@tailwindcss/vite`, KHÔNG `tailwind.config.js`); + react-router 7, @tanstack/react-query 5, @tanstack/react-table 8, zustand 5, lightweight-charts 5, react-hook-form 7, zod 4, lucide-react
- [x] `frontend/vite.config.ts`: `server.proxy` `/api` + `/ws` → target (`VITE_PROXY_TARGET` ?? `http://localhost:8000`, ws auto)
- [x] Trang Dashboard rỗng gọi `/api/health` qua react-query → hiển thị "backend ok"
- [x] `Dockerfile` multi-stage: stage1 `node:24` build `frontend/dist`; stage2 `python:3.12-slim` + `uv sync --frozen --no-dev`, copy `app/`+`alembic/`+`frontend/dist`, CMD `alembic upgrade head && uvicorn ... :8000`
- [x] `docker-compose.yml` (PROD): `db` (timescaledb pg16, mount `db/init`, healthcheck, volume) + `app` (build Dockerfile, depends_on db healthy, port 8000, env_file .env)
- [x] `docker-compose.dev.yml` (DEV): `db` + `api` (uvicorn `--reload`, bind-mount `app/`, port 8000) + `web` (node:24, `npm run dev`, port 5173, mount `frontend/`)
- [x] `.gitignore`: `.env`, `.venv/`, `node_modules/`, `frontend/dist/`, `__pycache__/` đã có
- [x] CI (`.github/workflows/ci.yml`): backend `uv sync` → `ruff check` → `pytest`; frontend `npm install` → `npm run build`
- [ ] `README` mini (lệnh dev/prod/test) — _hoãn: đã có Mục 3 trong plan này; thêm README riêng nếu cần_

### Definition of Done
- [x] `uv run pytest` xanh (smoke `test_health`).
- [x] `uv run ruff check .` sạch.
- [x] Frontend `npm run build` ra `dist/` (TS + Tailwind v4 compile OK).
- [x] **Prod single-endpoint verified**: uvicorn phục vụ cả `/api/health` (JSON) lẫn `/` (UI từ dist) trên cùng 1 cổng → 200.
- [x] Alembic env.py parse OK (`alembic heads` exit 0); `db/init` bật timescaledb lúc Postgres init.
- [ ] _Cần Docker chạy thực tế để xác nhận compose dev/prod_ (cấu hình hoàn chỉnh, chưa `docker compose up` trong phiên này).

---

## P1 — Market Feed + Chart Realtime

**Mục tiêu:** Thấy chart nến **sống động sát sàn** + watchlist giá realtime. Đặt nền EventBus + WSGateway dùng lại cho mọi phase sau.
**User Stories:** US-01 (chart realtime), US-02 (indicator), US-03 (watchlist), US-24 (responsive), US-25 (<1s, WS không poll).

### Backend
- [ ] `app/market/bus.py` — **EventBus**: pub/sub in-memory trên `asyncio.Queue`; topic `kline.{symbol}.{tf}`, `ticker.{symbol}`, `feed`. API: `subscribe(topic)->queue`, `publish(topic, msg)`.
- [ ] `app/market/feed.py` — **MarketFeed**: kết nối Binance WS (`python-binance` `BinanceSocketManager` / `ThreadedWebsocketManager` hoặc websockets thuần) cho kline + ticker theo danh sách symbol/tf trong config; publish vào bus. **Auto-reconnect** backoff; khi mất → publish `feed: DOWN`/`RECONNECTING`, khi nối lại → `OK`.
- [ ] `app/orders/models.py` — bảng `kline` (hypertable) + migration; helper upsert kline đóng nến vào Postgres.
- [ ] Migration Alembic: tạo `kline` + `SELECT create_hypertable('kline','ts', chunk_time_interval => INTERVAL '7 days')` (op.execute trong version).
- [ ] `app/api/ws.py` — **WSGateway** `/ws`: client connect → subscribe topic theo symbol đang xem; broadcast `{type:"kline"|"ticker"|"feed", ...}`. Quản lý connection set, dọn khi disconnect.
- [ ] `app/api/routes.py` — `POST /api/klines/sync` (tải lịch sử về Postgres qua REST `get_historical_klines`), `GET /api/klines?symbol&tf&from&to` (đọc DB cho chart load ban đầu).
- [ ] `app/main.py` lifespan: spawn task `MarketFeed.run()`.

### Frontend
- [ ] `src/lib/ws.ts` — zustand store giữ WS connection + state realtime (giá, nến cuối, feed status). Auto-reconnect client.
- [ ] `src/lib/api.ts` — react-query hooks: `useKlines`, `useSyncKlines`.
- [ ] `components/chart/CandleChart.tsx` — lightweight-charts 5: load lịch sử (REST) + cập nhật nến cuối (WS). **Datafeed adapter** (`lib/datafeed.ts`) cô lập nguồn dữ liệu để sau swap Charting Library không đụng component.
- [ ] Chọn khung TG 1m–1D (zoom/pan native của lib).
- [ ] Indicator EMA/RSI/MACD (US-02): tính client-side hoặc nhận từ backend; overlay/subpane bật–tắt.
- [ ] `components/watchlist/Watchlist.tsx` — list cặp + giá + %thay đổi realtime (US-03).
- [ ] `components/FeedBanner.tsx` — banner cảnh báo khi `feed != OK` (chuẩn bị cho US-27).
- [ ] Responsive layout (US-24): desktop grid + mobile tab bar (theo `docs/03-ASCII-Mockups.md`).

### Tests
- [ ] `test_bus.py` — publish/subscribe đúng topic, nhiều subscriber.
- [ ] `test_feed.py` — parse message Binance WS → kline/ticker đúng; mô phỏng mất kết nối → phát `feed: DOWN` rồi reconnect (mock socket).

### Definition of Done
- Mở UI → chart nến cập nhật < 1s theo giá thật; đổi khung TG OK; watchlist nhảy giá realtime.
- Ngắt mạng giả lập → banner DOWN → tự reconnect → OK.
- `/api/klines/sync` ghi đúng vào hypertable; chart load lịch sử mượt.

---

## P2 — Strategy Base + Paper Executor

**Mục tiêu:** Bot chạy **paper** với dữ liệu realtime thật, khớp lệnh nội bộ, **PnL realtime**, không gọi sàn. Khoá interface `Strategy/Context/Executor` dùng chung cho cả 4 mode.
**User Stories:** US-05 (viết/sửa strategy + reload), US-12 (paper), US-16 (positions realtime).

### Backend
- [ ] `app/strategy/base.py` — dataclass `Signal`, `Context`, `Position` + `Strategy(ABC)` với `name/version/default_params` + `on_candle(ctx)->list[Signal]` (đúng SRS §3). **Strategy chỉ đọc Context, không gọi API.**
- [ ] `app/strategy/registry.py` — decorator `@register`; quét `strategies/*.py`; đọc metadata; **sync vào bảng `strategy`** (name+version unique). Reload được (US-05).
- [ ] `app/strategy/strategies/ema_cross.py` + `rsi_rev.py` — 2 strategy mẫu.
- [ ] `app/execution/base.py` — `Executor(ABC)`: `submit/cancel/modify_sltp`.
- [ ] `app/execution/paper.py` — **PaperExecutor**: khớp MARKET ngay theo giá WS hiện tại; LIMIT chờ giá chạm; cập nhật `order` + `position` + PnL; ghi DB. Không gọi sàn.
- [ ] `app/strategy/runner.py` — **StrategyRunner**: 1 asyncio task/bot; subscribe `kline.{symbol}.{tf}` từ bus → dựng `Context` (giá, candles, position, indicators) → gọi `on_candle` → đẩy `Signal` cho Executor → broadcast `order`/`position` qua WSGateway.
- [ ] `app/orders/models.py` — models `strategy`, `bot`, `order`, `position` + migrations (DDL SRS §4).
- [ ] `app/api/routes.py` — `GET /api/strategies`, `POST /api/bots`, `PATCH /api/bots/{id}` (pause/resume/stop/params), `DELETE /api/bots/{id}`, `GET /api/positions`.
- [ ] WSGateway thêm broadcast `{type:"order"}`, `{type:"position"}` (PnL realtime).

### Frontend
- [ ] `pages/Strategies.tsx` — list strategy (từ file registry); tạo bot {strategy, symbol, tf, mode=PAPER, params}.
- [ ] `components/orders/PositionsTable.tsx` — bảng vị thế mở + PnL realtime (@tanstack/react-table) (US-16).
- [ ] Badge mode (PAPER = xanh) — chuẩn bị ma trận màu US-15.
- [ ] Nút pause/resume/stop bot (gọi PATCH).

### Tests
- [ ] `test_paper_executor.py` — MARKET khớp đúng giá; LIMIT khớp khi chạm; PnL long/short đúng; SL/TP đóng vị thế.
- [ ] `test_strategy_ema_cross.py` / `test_strategy_rsi_rev.py` — feed chuỗi candle giả → assert đúng Signal.
- [ ] `test_runner.py` — runner gọi on_candle đúng nhịp, đẩy signal sang executor (mock).

### Definition of Done
- Tạo bot paper EMA-cross trên 1 cặp → vào/ra lệnh tự động theo nến thật; positions + PnL nhảy realtime trên UI.
- Thêm file strategy mới + reload → xuất hiện trong `/api/strategies`.
- pytest paper + strategy xanh.

---

## P3 — Order Manager + Can thiệp tay + Audit

**Mục tiêu:** Quản lý vòng đời lệnh chặt chẽ, **can thiệp tay** mọi lúc, **audit log mọi hành động** (ghi TRƯỚC khi tác động). Marker vào/ra trên chart.
**User Stories:** US-04 (marker entry/exit + SL/TP trên chart), US-17 (đóng tay), US-18 (sửa SL/TP), US-19 (pause/resume), US-20 (đặt lệnh tay), US-21 (audit log).

### Backend
- [ ] `app/orders/manager.py` — **OrderManager**: state machine `NEW→PARTIAL→FILLED/CANCELLED/REJECTED`; nguồn `BOT|MANUAL|SYSTEM`. **Mọi `submit/cancel/modify` ghi `audit_log` TRƯỚC khi gọi executor/sàn** (NFR truy vết).
- [ ] `app/orders/models.py` — bảng `audit_log` + migration.
- [ ] `app/api/routes.py` — `POST /api/positions/{id}/close` (đóng tay), `PATCH /api/positions/{id}/sltp`, `POST /api/orders` (lệnh tay market/limit), `DELETE /api/orders/{id}`, `GET /api/audit`.
- [ ] Lệnh tay xen kẽ bot: `order.bot_id` NULL + `source=MANUAL`; vẫn qua PaperExecutor ở mode paper.
- [ ] Broadcast marker (entry/exit/SL/TP) qua WS để chart vẽ (US-04).

### Frontend
- [ ] `components/orders/ManualOrderForm.tsx` — đặt lệnh tay (react-hook-form + zod) (US-20).
- [ ] PositionsTable: nút **Close**, **Edit SL/TP** inline (US-17, US-18).
- [ ] `pages/Audit.tsx` — bảng audit log: thời gian, nguồn, mode, action, detail (US-21).
- [ ] Chart markers: entry/exit + đường SL/TP từ WS (US-04).
- [ ] Toggle pause/resume rõ ràng (US-19).

### Tests
- [ ] `test_order_manager.py` — chuyển trạng thái hợp lệ; **audit_log được ghi trước** khi gọi executor (assert thứ tự); chặn transition sai.
- [ ] `test_manual_orders.py` — đóng tay / sửa SL-TP / hủy lệnh tay cập nhật đúng position + audit.

### Definition of Done
- Đóng/sửa/hủy bằng tay phản ánh ngay trên UI + có dòng audit tương ứng (đúng thứ tự ghi trước).
- Chart hiện marker vào/ra + SL/TP.
- pytest order manager xanh.

---

## P4 — Backtest (vectorbt)

**Mục tiêu:** Backtest strategy trên dữ liệu lịch sử với fill giả lập; metrics + equity curve + trade list; marker trên chart lịch sử.
**User Stories:** US-09 (chạy backtest), US-10 (metrics + equity curve), US-11 (marker entry/exit chart lịch sử).

### Backend
- [ ] `app/backtest/engine.py` — chạy strategy qua **vectorbt**: input {strategy_id, params, symbol, tf, from, to, capital, fee_rate}; output `pnl_pct, winrate, max_dd, sharpe, n_trades, equity_curve, trades[]`. **Dùng chung interface `Strategy.on_candle`** (cùng logic với live, chống RK-4).
- [ ] Nguồn dữ liệu: đọc `kline` từ Postgres; nếu thiếu → `/api/klines/sync` trước.
- [ ] `app/orders/models.py` — `backtest_run`, `backtest_trade` + migrations.
- [ ] `app/api/routes.py` — `POST /api/backtest` (chạy, lưu run), `GET /api/backtest/{run_id}`.
- [ ] Cân nhắc chạy backtest trong threadpool/executor để không chặn event loop.

### Frontend
- [ ] `pages/Backtest.tsx` — form chọn cặp/khung/khoảng ngày/capital/fee → chạy (US-09).
- [ ] `components/backtest/EquityCurve.tsx` + bảng metrics + trade list (US-10).
- [ ] Marker entry/exit vẽ trên chart lịch sử (US-11, dùng lại CandleChart).

### Tests
- [ ] `test_backtest_engine.py` — strategy đã biết kết quả → assert metrics khớp; equity curve đơn điệu đúng kỳ vọng; phí áp dụng đúng.

### Definition of Done
- Chạy backtest 1 strategy → ra metrics + equity curve + danh sách trade; marker hiện trên chart lịch sử.
- Kết quả backtest và logic paper **nhất quán** (cùng on_candle).

---

## P5 — Strategy Versioning + Params UI

**Mục tiêu:** Quản lý nhiều version 1 strategy, chỉnh params từ UI (không sửa code), so sánh hiệu năng.
**User Stories:** US-06 (params UI), US-07 (nhiều version chạy song song), US-08 (so sánh version).

### Backend
- [ ] Registry: `version` trong file là **nguồn sự thật**; sync nhiều (name, version) → bảng `strategy`. Nhiều bot chạy version khác nhau song song (US-07).
- [ ] Schema params: strategy khai báo `param_schema` (kiểu/min/max/default) để UI render form + validate.
- [ ] `app/api/routes.py` — `GET /api/strategies/{id}/params` (schema), so sánh: `GET /api/strategies/{name}/compare` (gộp backtest_run theo version).
- [ ] PATCH bot params: validate theo schema trước khi lưu.

### Frontend
- [ ] `components/strategy/ParamsForm.tsx` — render từ param_schema (react-hook-form + zod), lưu DB (US-06).
- [ ] Chọn version khi tạo bot (US-07).
- [ ] `components/strategy/VersionCompare.tsx` — bảng so sánh PnL/winrate/drawdown theo version (US-08).

### Tests
- [ ] `test_registry_versioning.py` — 2 version cùng name sync đúng, unique (name,version); params override default đúng.
- [ ] `test_params_validation.py` — params ngoài min/max bị từ chối.

### Definition of Done
- Chỉnh params từ UI → bot dùng params mới (không sửa code); 2 version chạy song song; bảng so sánh hiển thị đúng.

---

## P6 — Testnet Integration

**Mục tiêu:** Bot đặt **lệnh thật trên testnet.binance** (môi trường giả), cùng interface Executor. Badge mode rõ ràng.
**User Stories:** US-13 (chạy testnet), US-15 (badge mode nổi bật).

### Backend
- [ ] `app/execution/testnet.py` — **TestnetExecutor** qua `python-binance` (client testnet, key `BINANCE_TESTNET_*`): submit/cancel/modify ánh xạ sang API sàn; đồng bộ trạng thái lệnh về `order`/`position` (lưu `ext_id`).
- [ ] User Data Stream (WS) cập nhật fill/đổi trạng thái lệnh testnet → OrderManager.
- [ ] **Auto-cancel limit theo `params.timeout`** (NFR, chuẩn bị cho US-26): mỗi LIMIT tạo `asyncio.create_task` hủy sau timeout — áp dụng cho testnet/live.
- [ ] Audit log đầy đủ trước mỗi call sàn.
- [ ] Tạo bot mode=TESTNET; runner dùng TestnetExecutor (đổi adapter = đổi mode, strategy không biết).

### Frontend
- [ ] Badge mode TESTNET = **vàng** (US-15, ma trận màu URD §3).
- [ ] Hiển thị `ext_id` + trạng thái đồng bộ từ sàn.

### Tests
- [ ] `test_testnet_executor.py` — mock python-binance: submit/cancel ánh xạ đúng payload; map trạng thái sàn → order; ghi `ext_id`.
- [ ] `test_limit_timeout.py` — LIMIT quá `timeout` bị auto-cancel + audit `CANCEL/SYSTEM`.

### Definition of Done
- Bot testnet đặt được lệnh thật trên testnet, trạng thái đồng bộ về UI; badge vàng; limit treo tự hủy.

---

## P7 — Scanner đề xuất cặp

**Mục tiêu:** Quét cặp định kỳ, đề xuất vào lệnh (score + signal + reason); từ đề xuất mở nhanh chart/đặt lệnh.
**User Stories:** US-22 (scanner định kỳ), US-23 (từ đề xuất → chart/prefill lệnh).

### Backend
- [ ] `app/scanner/research.py` — task định kỳ (asyncio, chu kỳ config) quét danh sách cặp, tính score/signal/reason, ghi `scan_result`, publish topic `scan` lên bus → WS.
- [ ] `app/orders/models.py` — `scan_result` + migration.
- [ ] `app/api/routes.py` — `GET /api/scan`.
- [ ] WSGateway broadcast `{type:"scan", results}`.

### Frontend
- [ ] `pages/Scanner.tsx` — list cặp + score + tín hiệu realtime (US-22).
- [ ] Click đề xuất → mở chart cặp đó / prefill ManualOrderForm hoặc gán cho bot (US-23).

### Tests
- [ ] `test_scanner.py` — logic score/signal trên dữ liệu mẫu cho kết quả đúng; ghi scan_result đúng.

### Definition of Done
- Scanner chạy nền, bảng đề xuất cập nhật; click đề xuất mở chart/prefill lệnh.

---

## P8 — Live + Rào chắn an toàn

**Mục tiêu:** Mode **LIVE (tiền thật)** chỉ chạy sau nhiều rào chắn. Hoàn thiện NFR an toàn còn lại.
**User Stories:** US-14 (live có rào chắn), US-26 (không treo limit — hoàn thiện), US-27 (cảnh báo mất kết nối — hoàn thiện).
**⚠️ Trước khi bắt đầu phase này: HỎI LẠI user (theo CLAUDE.md "Hỏi lại trước khi chạm mode LIVE").**

### Backend
- [ ] `app/execution/live.py` — **LiveExecutor** qua `python-binance` prod (key `BINANCE_*`). **Chỉ khởi tạo khi `ENABLE_LIVE=1`**; nếu không → từ chối tạo bot LIVE.
- [ ] Guard tạo bot mode=LIVE: server kiểm `ENABLE_LIVE=1`; client modal gõ đúng "LIVE" mới gửi.
- [ ] Audit log bắt buộc trước mọi call; auto-cancel limit theo timeout (đã có từ P6) áp dụng live.
- [ ] Mất feed (US-27): khi `feed=DOWN` → **bot auto-pause** + push banner; nối lại không tự resume (cần xác nhận).
- [ ] Kiểm tra cấu hình key live: nhắc tắt quyền rút, whitelist IP (doc + cảnh báo, không tự thay đổi key).

### Frontend
- [ ] `components/live/EnableLiveModal.tsx` — modal confirm gõ "LIVE" + cảnh báo đỏ (US-14).
- [ ] Badge mode LIVE = **đỏ**; toàn UI bot live nhuốm cảnh báo (URD §3).
- [ ] Banner mất kết nối + trạng thái auto-pause rõ ràng (US-27).

### Tests
- [ ] `test_live_guard.py` — `ENABLE_LIVE=0` → tạo bot LIVE bị từ chối; =1 + thiếu confirm → từ chối.
- [ ] `test_feed_autopause.py` — `feed=DOWN` → bot chuyển PAUSED + audit `PAUSE/SYSTEM`.
- [ ] (KHÔNG test đặt lệnh thật trên live; chỉ mock python-binance.)

### Definition of Done
- Không thể vào LIVE nếu thiếu cờ/confirm; badge đỏ; mất feed → auto-pause + cảnh báo; mọi lệnh live có audit trước.
- Smoke test live bằng key thật (số lượng tối thiểu) do **user tự thực hiện**, không tự động hoá.

---

## 3. Lệnh thường dùng

```bash
# --- Dev (Docker, khuyến nghị) ---
docker compose -f docker-compose.dev.yml up        # → http://localhost:5173

# --- Dev (ngoài Docker) ---
uv sync                                             # cài venv .venv
uv run uvicorn app.main:app --reload                # backend :8000
cd frontend && npm install && npm run dev           # frontend :5173 (proxy → :8000)

# --- Migration ---
uv run alembic revision --autogenerate -m "..."     # tạo migration
uv run alembic upgrade head                          # áp dụng

# --- Test ---
uv run pytest                                        # backend tests
uv run ruff check .                                  # lint

# --- Prod (1 endpoint :8000) ---
docker compose up --build                            # build frontend → FastAPI serve static
```

---

## 4. Rủi ro & cách chặn (nhắc lại từ SRS)

| Rủi ro | Chặn | Phase |
|---|---|---|
| RK-1 Nhầm lệnh thật | Mode bằng config + cờ `ENABLE_LIVE` + confirm "LIVE" | P8 |
| RK-2 Treo lệnh limit | Auto-cancel theo `params.timeout` | P6 |
| RK-3 Mất feed | WS auto-reconnect + bot auto-pause | P1, P8 |
| RK-4 Lệch logic backtest vs live | **Một interface `Strategy.on_candle`** cho cả 4 mode | P2, P4 |

---

## Changelog

| Ngày | Phase | Thay đổi |
|---|---|---|
| 2026-06-12 | — | Khởi tạo IMPLEMENTATION-PLAN.md (P0–P8 chi tiết). |
| 2026-06-12 | P0 | ✅ Scaffold xong: uv venv + backend (config/db/main/health), Alembic async + Timescale init SQL, frontend React19/Vite6/Tailwind v4 + proxy, Dockerfile multi-stage + compose dev/prod, CI. Verified: pytest/ruff xanh, prod single-endpoint serve UI+API. (Còn: `docker compose up` thực tế + README.) |

<!-- Thêm dòng mỗi khi hoàn thành milestone; nhớ cập nhật cột Status + % ở Bảng tiến độ tổng. -->
