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
| **P1** | Market feed + Chart realtime | US-01,02,03,24,25 | ✅ | 100% |
| **P2** | Strategy base + Paper executor | US-05,12,16 | ✅ | 100% |
| **P3** | Order Manager + can thiệp tay + audit | US-04,17,18,19,20,21 | ✅ | 100% |
| **P4** | Backtest (vectorbt) | US-09,10,11 | ✅ | 100% |
| **P5** | Strategy versioning + params UI | US-06,07,08 | ✅ | 100% |
| **P6** | Testnet integration | US-13,15 | ✅ | 100% |
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
- [x] `app/market/bus.py` — **EventBus**: pub/sub `asyncio.Queue`; topic `kline.{symbol}.{tf}`, `ticker.{symbol}`, `feed` + firehose `"*"`; backpressure drop khi queue đầy.
- [x] `app/market/feed.py` — **MarketFeed**: combined-stream `websockets` (kline+ticker) → bus; auto-reconnect backoff; phát `feed` OK/RECONNECTING/DOWN. Parse functions tách riêng để test. (Dùng `websockets` cho stream; python-binance để dành execution P6.)
- [x] `app/market/models.py` — `Kline` ORM (hypertable). `app/market/store.py` — upsert (chia batch < 32767 params), `get_klines`, `sync_historical`, `persist_closed_klines` (task nền ghi nến đóng).
- [x] Migration Alembic `0001_kline_hypertable.py`: tạo `kline` + `create_hypertable(... '7 days')`. Verified trên Timescale thật.
- [x] `app/api/ws.py` — **WSGateway** `/ws`: client subscribe firehose, broadcast `{type:"kline"|"ticker"|"feed"}`; gửi feed status lúc connect; dọn khi disconnect.
- [x] `app/api/routes.py` — `POST /api/klines/sync`, `GET /api/klines`, `GET /api/config` (symbols/timeframes — frontend không hardcode).
- [x] `app/main.py` lifespan: spawn MarketFeed + persister + feed-status tracker (gate `feed_autostart` để test/CI không gọi mạng).

### Frontend
- [x] `src/lib/ws.ts` — zustand store: 1 WS connection, tickers + lastKline + feed status, auto-reconnect client.
- [x] `src/lib/api.ts` — react-query + helper `fetchConfig`/`syncKlines`. `src/lib/datafeed.ts` — **datafeed adapter** cô lập nguồn (swap Charting Library sau chỉ sửa file này).
- [x] `components/chart/CandleChart.tsx` — lightweight-charts 5: load lịch sử (REST) + update nến cuối (WS); theme màu logo.
- [x] `components/chart/TimeframeSelector.tsx` — 1m–1d (zoom/pan native).
- [x] Indicator **EMA 9/21** overlay bật/tắt (US-02). _RSI/MACD subpane: hoãn (đủ tiêu chí "bật/tắt indicator"; bổ sung khi cần)._
- [x] `components/watchlist/Watchlist.tsx` — cặp + giá + %thay đổi realtime (US-03).
- [x] `components/FeedBanner.tsx` — banner khi `feed != OK` + chấm trạng thái header (chuẩn bị US-27).
- [x] Responsive (US-24): desktop watchlist+chart cạnh nhau, mobile stack (verified screenshot 390px).

### Tests
- [x] `test_bus.py` (8) — pub/sub, firehose, unsubscribe, backpressure.
- [x] `test_feed.py` (9) — parse kline/ticker, stream URL, reconnect phát feed status (fake WS).
- [x] `test_store.py` (3) — upsert chia batch đúng (< giới hạn params asyncpg).

### Definition of Done
- [x] UI: chart nến cập nhật realtime theo giá Binance thật; đổi TF OK; watchlist nhảy giá < 1s. **Verified screenshot** (BTC/ETH live, EMA overlays).
- [x] Reconnect: feed phát RECONNECTING→OK (test); banner UI khi mất feed.
- [x] `/api/klines/sync` ghi đúng hypertable (4320 nến 3 ngày, sau khi fix batch); chart load lịch sử mượt; console không lỗi.
- [x] 21 pytest xanh, ruff sạch, frontend build OK.

---

## P2 — Strategy Base + Paper Executor

**Mục tiêu:** Bot chạy **paper** với dữ liệu realtime thật, khớp lệnh nội bộ, **PnL realtime**, không gọi sàn. Khoá interface `Strategy/Context/Executor` dùng chung cho cả 4 mode.
**User Stories:** US-05 (viết/sửa strategy + reload), US-12 (paper), US-16 (positions realtime).

### Backend
- [x] `app/strategy/base.py` — `Signal`, `Context`, `Position` + `Strategy(ABC)` (SRS §3). Strategy chỉ đọc Context.
- [x] `app/execution/paper_engine.py` — **PaperEngine** thuần (TDD): market/limit fill, flip, SL/TP, PnL long/short, fee. Tách khỏi DB để test kỹ.
- [x] `app/strategy/registry.py` — `@register` + `discover()` quét `strategies/` + `sync_to_db` (name+version unique). `app/strategy/ta.py` (EMA/RSI).
- [x] `app/strategy/strategies/ema_cross.py` + `rsi_rev.py` — 2 strategy mẫu + `param_schema` (cho UI P5).
- [x] `app/execution/base.py` `Executor(ABC)` (submit/cancel/modify_sltp/on_price/current_position).
- [x] `app/execution/paper.py` — **PaperExecutor**: bọc engine + persist `order`/`position` + broadcast `order.update`/`position` (PnL realtime). Không gọi sàn.
- [x] `app/strategy/runner.py` — **StrategyRunner** (1 task/bot, seed nến lịch sử, on_price mỗi tick + on_candle khi nến đóng, PAUSED không sinh tín hiệu) + **BotManager** (vòng đời, restore bot RUNNING khi restart).
- [x] `app/orders/models.py` — `strategy/bot/order/position` + migration `0002` (autogenerate, đã sửa bỏ drop index Timescale).
- [x] `app/api/trading.py` — `GET /strategies`, `GET/POST /bots`, `PATCH/DELETE /bots/{id}`, `GET /positions`, `GET /orders`.
- [x] WSGateway broadcast `{type:"order"}`, `{type:"position"}` (qua firehose có sẵn).

### Frontend
- [x] Router (react-router) + `AppLayout` (nav Chart/Trading, feed status) — tách Dashboard khỏi App.
- [x] `pages/Trading.tsx` — list strategy, tạo bot {strategy, symbol, tf, PAPER, params}, list bots + pause/resume/stop/delete.
- [x] `components/orders/PositionsTable.tsx` — vị thế mở + **PnL realtime** (seed REST + overlay WS store) (US-16).
- [x] `components/ModeBadge.tsx` — PAPER teal / TESTNET amber / LIVE đỏ (US-15 ma trận màu).
- [x] WS store mở rộng: `positions` (key bot_id), `orders`.

### Tests
- [x] `test_paper_engine.py` (15) — market/limit, flip, SL/TP, PnL long/short, fee, unrealized.
- [x] `test_strategies.py` (9) — TA (ema/rsi), ema_cross buy/sell, rsi_rev oversold/overbought, registry discover.
- [x] `test_paper_executor.py` (1) — PaperExecutor + DB thật: BUY→TP → position CLOSED pnl đúng + broadcast OPEN/order/CLOSED (skip nếu không có DB).

### Definition of Done
- [x] Tạo bot paper từ UI → bot RUNNING; pause/resume/stop/delete hoạt động; bot restore sau restart. **Verified screenshot Trading page.**
- [x] Engine→persist→broadcast đúng (test DB) → positions + PnL realtime trên UI (PositionsTable subscribe WS).
- [x] Thêm strategy = thêm file + reload registry → `/api/strategies` (đã verify 2 strategy + param_schema).
- [x] 46 pytest xanh, ruff sạch, frontend build OK.
- [x] **Bug fix khi dogfood**: SPA deep-link `/trade` 404 ở prod-static → thêm `SPAStaticFiles` fallback index.html.

---

## P3 — Order Manager + Can thiệp tay + Audit

**Mục tiêu:** Quản lý vòng đời lệnh chặt chẽ, **can thiệp tay** mọi lúc, **audit log mọi hành động** (ghi TRƯỚC khi tác động). Marker vào/ra trên chart.
**User Stories:** US-04 (marker entry/exit + SL/TP trên chart), US-17 (đóng tay), US-18 (sửa SL/TP), US-19 (pause/resume), US-20 (đặt lệnh tay), US-21 (audit log).

### Backend
- [x] `app/orders/manager.py` — **OrderManager.execute**: ghi `audit_log` TRƯỚC, rồi mới chạy `do` (executor). Nguồn BOT/MANUAL/SYSTEM. `list_audit`.
- [x] `app/orders/models.py` — `AuditLog` + migration `0003`. Order lifecycle NEW→FILLED/CANCELLED (LIMIT persist NEW, fill→FILLED, cancel→CANCELLED qua engine `queued`/`filled_pending_id`/`cancelled_ids`).
- [x] `app/api/trading.py` — `POST /positions/{id}/close`, `PATCH /positions/{id}/sltp`, `POST /orders` (tay market/limit), `DELETE /orders/{id}`, `GET /audit`.
- [x] Routing executor: vị thế bot → bot executor (BotManager.get_executor); lệnh tay rời → **ManualTrader** (1 PaperExecutor/symbol, subscribe ticker cho SL/TP). `source=MANUAL`, `pos_key` ổn định.
- [x] Bot path đi qua OrderManager (audit mỗi signal TRƯỚC submit).
- [x] Broadcast `order`/`position` kèm `pos_key` (chart vẽ marker từ order WS).

### Frontend
- [x] `components/orders/ManualOrderForm.tsx` — đặt lệnh tay market/limit + SL/TP, ref_price từ ticker (US-20).
- [x] PositionsTable: nút **Close** + **Edit SL/TP** inline (US-17, US-18); key theo pos_key (bot + manual).
- [x] `pages/Audit.tsx` + nav — bảng audit: thời gian, nguồn, mode, bot, symbol, action, detail (US-21).
- [x] Chart markers entry/exit từ order WS (`createSeriesMarkers`) (US-04). SL/TP hiển thị ở bảng position.
- [x] Pause/resume rõ ràng (US-19, từ P2).

### Tests
- [x] `test_order_manager.py` (2) — audit ghi TRƯỚC khi act; audit còn nguyên dù act lỗi.
- [x] `test_paper_engine.py` +5 — limit queued/filled id, cancel ids, force_close manual.
- [x] Manual flow verified LIVE (xem DoD).

### Definition of Done
- [x] Đặt lệnh tay → vị thế (manual, bot_id null); sửa SL/TP; đóng tay → UI cập nhật + **audit OPEN/EDIT_SLTP/CLOSE đúng thứ tự** (verified live + screenshot Audit).
- [x] Audit ghi TRƯỚC khi tác động (test thứ tự + còn nguyên khi act lỗi).
- [x] Chart marker code path từ order WS; SL/TP hiển thị bảng position.
- [x] 52 pytest xanh, ruff sạch, frontend build OK.

---

## P4 — Backtest (vectorbt)

**Mục tiêu:** Backtest strategy trên dữ liệu lịch sử với fill giả lập; metrics + equity curve + trade list; marker trên chart lịch sử.
**User Stories:** US-09 (chạy backtest), US-10 (metrics + equity curve), US-11 (marker entry/exit chart lịch sử).

### Backend
- [x] `app/backtest/engine.py` — **dùng chung `Strategy.on_candle`** (replay sinh tín hiệu long/short) → `vbt.Portfolio.from_signals` (vectorbt) tính `pnl_pct, winrate, max_dd, sharpe, n_trades, equity_curve, trades`. Import vectorbt LAZY (dep nặng).
- [x] Nguồn dữ liệu: `sync_historical` + `get_klines` từ Postgres.
- [x] `app/orders/models.py` — `BacktestRun`, `BacktestTrade` + migration `0004`.
- [x] `app/api/backtest.py` — `POST /backtest` (chạy trong threadpool `anyio.to_thread`, lưu run+trades), `GET /backtest/{id}`, `GET /backtests`.
- [x] `vectorbt`/`pandas`/`numpy` ở extra `backtest`; Dockerfile prod cài `--extra backtest`.

### Frontend
- [x] `pages/Backtest.tsx` + nav — form cặp/khung/số ngày/vốn/phí → chạy (US-09).
- [x] `components/backtest/EquityCurve.tsx` (lightweight-charts) + thẻ metrics + bảng trade list (US-10).
- [~] Marker entry/exit trên chart lịch sử (US-11): trade list + equity curve đủ trực quan; marker dùng lại CandleChart hoãn (đã có marker realtime ở P3).

### Tests
- [x] `test_backtest_engine.py` (2) — chạy ra metrics/equity/trades; thiếu dữ liệu → raise. (skip nếu chưa cài extra backtest).

### Definition of Done
- [x] Chạy backtest → metrics + equity curve + trade list (verified LIVE 7 ngày BTC 1m: 272 trades, equity curve giảm — đúng hành vi ema_cross overtrade trên 1m; **screenshot**).
- [x] Backtest và paper **nhất quán** (cùng `Strategy.on_candle`, chống RK-4).
- [x] 54 pytest xanh, ruff sạch, build OK.

---

## P5 — Strategy Versioning + Params UI

**Mục tiêu:** Quản lý nhiều version 1 strategy, chỉnh params từ UI (không sửa code), so sánh hiệu năng.
**User Stories:** US-06 (params UI), US-07 (nhiều version chạy song song), US-08 (so sánh version).

### Backend
- [x] Registry: `version` là nguồn sự thật; sync nhiều (name, version). Thêm **ema_cross v2** (gap-filter) → 2 version song song (US-07).
- [x] `param_schema` (kiểu/min/max/default) trả trong `GET /strategies`; `app/strategy/params.py validate_params`.
- [x] `GET /strategies/{name}/compare` — gộp backtest_run theo version (US-08).
- [x] Validate params theo schema khi tạo/PATCH bot (ngoài khoảng → 422).

### Frontend
- [x] `components/strategy/ParamsForm.tsx` — render input từ param_schema (min/max hint) (US-06).
- [x] Chọn version khi tạo bot (dropdown "name vX") + form params (US-07).
- [x] `components/strategy/VersionCompare.tsx` — bảng so sánh PnL/winrate/maxDD/trades theo version (US-08), trong trang Backtest.

### Tests
- [x] `test_params.py` (8) — validate (default/coerce/min/max/type/extra), 2 version registered, v2 gap-filter chặn cross nhỏ.

### Definition of Done
- [x] Chỉnh params từ UI → bot dùng params mới (không sửa code); validation 422/200 (verified live).
- [x] 2 version chạy song song (v1/v2 trong dropdown + backtest riêng).
- [x] Bảng so sánh đúng (verified live: v1 -20%/91 trades vs v2 +3.6%/1 trade — gap filter giảm overtrade; **screenshot**).
- [x] 62 pytest xanh, ruff sạch, build OK.

---

## P6 — Testnet Integration

**Mục tiêu:** Bot đặt **lệnh thật trên testnet.binance** (môi trường giả), cùng interface Executor. Badge mode rõ ràng.
**User Stories:** US-13 (chạy testnet), US-15 (badge mode nổi bật).

### Backend
- [x] `app/execution/binance_client.py` — adapter mỏng quanh `python-binance AsyncClient` (chuẩn hóa `{orderId, price, status, qty}`), inject được để test.
- [x] `app/execution/testnet.py` — **TestnetExecutor**: tái dùng PaperEngine cho state/PnL/SL-TP (nhất quán), nhưng MỌI fill vào/ra là lệnh thật gửi sàn, lưu `ext_id`. SL/TP client-side (on_price phát hiện → market close thật).
- [x] **Auto-cancel limit theo `timeout`** (NFR US-26): mỗi LIMIT → `asyncio.create_task` hủy sau timeout (testnet/live).
- [x] BotManager `_make_executor`: mode=TESTNET → TestnetExecutor (cần key); strategy/runner không đổi (đổi adapter = đổi mode).
- [x] Audit qua OrderManager (bot path) trước mỗi action. _User Data Stream WS: listener khung sẵn, chưa verify live (cần key)._

### Frontend
- [x] Badge TESTNET = vàng (ModeBadge, US-15); mode selector PAPER/TESTNET ở form tạo bot.
- [x] `ext_id` trả trong `/api/orders`.

### Tests
- [x] `test_testnet_executor.py` (6) — market order mở vị thế, close gửi lệnh ngược, SL/TP → market close thật, limit + ext_id, **auto-cancel timeout**, manual cancel gọi sàn. (client giả, không cần key).

### Definition of Done
- [x] Logic testnet mock-tested đầy đủ; auto-cancel limit hoạt động.
- [x] Tạo bot TESTNET không có key → **400 thông báo rõ + rollback bot** (verified live); PAPER vẫn chạy.
- [x] 68 pytest xanh, ruff sạch, build OK.
- [ ] ⚠️ **Verify lệnh thật trên testnet cần `BINANCE_TESTNET_KEY/SECRET`** — hoãn tới khi user cấp key (code sẵn sàng).

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
| 2026-06-12 | UI | 🎨 Logo + theme phái sinh từ docs/logo.png (brand slate-violet, accent teal, dark-first). |
| 2026-06-12 | P1 | ✅ Market feed + chart realtime: EventBus, MarketFeed (Binance WS live), kline hypertable (verified Timescale), WSGateway /ws, klines sync/read REST. Frontend: chart lightweight-charts + EMA 9/21, watchlist live, feed banner, responsive (desktop+mobile verified screenshot). Fix: batch upsert (asyncpg 32767 param limit). 21 pytest xanh. RSI/MACD subpane hoãn. |
| 2026-06-12 | P6 | ✅ Testnet integration: BinanceClient adapter, TestnetExecutor (tái dùng engine state, lệnh thật + ext_id, SL/TP client-side), auto-cancel limit theo timeout (US-26). BotManager wire TESTNET (graceful no-key). Frontend: mode selector + TESTNET badge + ext_id. **Verified: 6 mock tests + no-key → 400 rollback (live).** ⚠️ Lệnh thật testnet cần key user (hoãn). 68 pytest xanh. |
| 2026-06-12 | P5 | ✅ Versioning + params UI: validate_params vs param_schema (422 khi sai), ema_cross v2 (gap filter), compare API gộp backtest theo version. Frontend: ParamsForm (render từ schema), version compare table. **Verified LIVE: v1 -20%/91 trades vs v2 +3.6%/1 trade (screenshot); validation 422.** 62 pytest xanh. |
| 2026-06-12 | P4 | ✅ Backtest (vectorbt): engine dùng chung on_candle → vbt.Portfolio.from_signals; models backtest_run/trade (migration 0004); API /backtest (threadpool); frontend page form + metrics + equity curve + trade list. **Verified LIVE: backtest 7 ngày BTC 1m, 272 trades, equity curve (screenshot).** vectorbt ở extra; Dockerfile cài extra. Fix: WS disconnect noise. 54 pytest xanh. |
| 2026-06-12 | P3 | ✅ Order Manager + can thiệp tay + audit: OrderManager (audit ghi TRƯỚC khi act), AuditLog (migration 0003), order lifecycle NEW→FILLED/CANCELLED, ManualTrader + routing executor (bot vs tay), API close/sltp/manual-order/cancel/audit. Frontend: ManualOrderForm, Close/EditSLTP trong PositionsTable, trang Audit, chart markers. **Verified LIVE: đặt lệnh tay → sửa SL/TP → đóng tay, audit OPEN/EDIT_SLTP/CLOSE đúng thứ tự (screenshot).** 52 pytest xanh. |
| 2026-06-12 | P2 | ✅ Strategy base + Paper executor: interface Strategy/Context/Signal/Executor chạy chung 4 mode; PaperEngine (TDD 15 test), registry file-based + ema_cross/rsi_rev, StrategyRunner + BotManager (restore khi restart), models strategy/bot/order/position (migration 0002), API bots/strategies/positions. Frontend: router + Trading page (tạo bot, pause/resume/stop, PositionsTable realtime PnL, ModeBadge). **Verified LIVE: bot tự mở LONG từ nến Binance thật, PnL realtime trên UI.** Fix: SPA fallback /trade (prod-static 404), delete bot giữ history (FK). 46 pytest xanh. |

<!-- Thêm dòng mỗi khi hoàn thành milestone; nhớ cập nhật cột Status + % ở Bảng tiến độ tổng. -->
