# CLAUDE.md — Binance Trading Bot Platform

> File này là ngữ cảnh dự án cho Claude Code. Đọc đầu mỗi phiên.
> Tài liệu chi tiết nằm trong `docs/` (đọc khi cần): 00-Plan, 01-BRD, 02-URD, 03-ASCII-Mockups, 04-SRS.

## Tóm tắt dự án
Web app trading bot cho sàn **Binance**, **single-user**, self-hosted. Mục tiêu: tự động hóa chiến thuật có kỷ luật, kiểm chứng kỹ (backtest + paper) trước khi dùng tiền thật, realtime sát sàn, vẫn can thiệp tay được.

## Quyết định đã chốt (KHÔNG đổi nếu không có lý do)
1. **Python thuần**, single process, FastAPI + asyncio. Không Go, không microservice, không NATS/Kafka.
2. **Một sàn: Binance** → dùng `python-binance` (không ccxt).
3. **Postgres + TimescaleDB** (hypertable cho klines).
4. **Chart: lightweight-charts trước**, swap TradingView Charting Library sau (khi có public URL + được duyệt repo). Cô lập qua datafeed adapter.
5. **Strategy file-based**, sửa ngoài app (trong repo/IDE). App chỉ load & chạy. UI chỉ chỉnh params + chọn version, KHÔNG có code editor trong app.

## 4 chế độ vận hành (1 interface chạy chung)
- **Backtest**: data lịch sử, fill giả lập (vectorbt).
- **Paper**: data realtime thật, khớp lệnh nội bộ, không gọi sàn.
- **Testnet**: testnet.binance, lệnh thật môi trường giả.
- **Live**: production, TIỀN THẬT. Cần cờ env `ENABLE_LIVE=1` + xác nhận. Mặc định TẮT.

## Frontend stack (version mới nhất, 06/2026)
React 19.2.x + TypeScript 5 + Vite 6 + Tailwind **v4** (CSS-first, `@import "tailwindcss"`, không tailwind.config.js, plugin `@tailwindcss/vite`) + react-router 7 + @tanstack/react-query 5 (REST) + @tanstack/react-table 8 + zustand 5 (realtime WS state) + lightweight-charts 5 + react-hook-form 7 + zod 4 + lucide-react. Node 20+ (khuyến nghị 22 LTS).
**Phân vai state:** REST → React Query; WebSocket → Zustand.

## Cấu trúc thư mục mục tiêu
```
app/                      # backend Python
  main.py config.py db.py
  market/   feed.py bus.py
  strategy/ base.py registry.py runner.py  strategies/*.py   # SỬA CHIẾN THUẬT Ở ĐÂY
  execution/ base.py paper.py testnet.py live.py
  orders/   manager.py models.py
  backtest/ engine.py
  scanner/  research.py
  api/      routes.py ws.py
frontend/                 # React 19 + Vite + Tailwind v4
docs/                     # BRD/URD/SRS/Plan/Mockup
docker-compose.yml        # app + postgres(timescale)
```

## Interface cốt lõi (xem 04-SRS mục 3 để đầy đủ)
- `Strategy.on_candle(ctx: Context) -> list[Signal]` — chiến thuật chỉ đọc Context, không gọi API.
- `Executor.submit/cancel/modify_sltp` — đổi adapter = đổi mode.
- Cùng một file strategy chạy được cả 4 mode.

## Roadmap (làm theo phase, an toàn trước, tiền thật sau cùng)
- P1 Market feed + chart realtime
- P2 Strategy base + Paper executor
- P3 Order Manager + can thiệp tay + audit log
- P4 Backtest (vectorbt)
- P5 Strategy versioning + params UI
- P6 Testnet integration
- P7 Scanner đề xuất cặp
- P8 Live + rào chắn an toàn

## NFR bắt buộc
- Realtime < 1s: Binance WS (không poll) → EventBus → WS gateway.
- Không treo lệnh limit: auto-cancel theo `params.timeout`.
- Mất feed: auto-reconnect + bot auto-pause.
- Responsive: desktop + mobile.

## An toàn (quan trọng)
- `.env` KHÔNG commit (đưa vào .gitignore). API key chỉ trong env.
- Live key: tắt quyền rút tiền, whitelist IP VPS.
- Mọi lệnh (bot + tay) ghi `audit_log` TRƯỚC khi gọi sàn.
- Mode LIVE chỉ chạy khi `ENABLE_LIVE=1` + modal confirm gõ "LIVE".

## Quy ước làm việc
- Commit theo phase, message rõ ràng (vd `feat(p1): binance ws feed`).
- Viết test cho paper engine + strategy logic (pytest).
- Không hardcode symbol/param — đọc từ config/DB.
- Hỏi lại trước khi: chạm mode LIVE, đổi quyết định đã chốt, xóa data.

## Lệnh thường dùng (điền sau khi scaffold)
- Backend dev: `uvicorn app.main:app --reload`
- Frontend dev: `cd frontend && npm run dev`
- Full stack: `docker compose up`
- Test: `pytest`
