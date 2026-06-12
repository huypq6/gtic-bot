# Project Plan — Ghost Trader In Chair Bot

Bộ tài liệu:
1. [`01-BRD.md`](01-BRD.md) — Business Requirements
2. [`02-URD.md`](02-URD.md) — User Requirements + User Stories
3. [`03-ASCII-Mockups.md`](03-ASCII-Mockups.md) — Wireframes

---

## 1. Tóm tắt giải pháp
Web app **Python thuần, single-user**, single-process (FastAPI + asyncio). Một interface chiến thuật chạy chung 4 mode: **Backtest → Paper → Testnet → Live**. Realtime qua WebSocket, can thiệp thủ công bất cứ lúc nào.

## 2. Tech stack chốt ✅
| Lớp | Chọn | Ghi chú quyết định |
|---|---|---|
| Web/API | FastAPI (async, WebSocket) | |
| Exchange | **python-binance** | Không đa sàn → không cần ccxt |
| Realtime nội bộ | asyncio.Queue (EventBus in-memory) | |
| DB | **Postgres + TimescaleDB** | Chốt Postgres từ đầu cho chắc, hypertable cho klines |
| Backtest | vectorbt | |
| Chart | **Lightweight Charts trước → Charting Library sau** | Xin Charting Library cần public URL (chưa có lúc đầu). Dùng Lightweight Charts ngay (npm, miễn phí), swap khi có domain + được duyệt. Drawing tools chỉ có sau khi swap. |
| Frontend | React (responsive) | |
| Strategy | **File-based, sửa ngoài app** | App chỉ load & chạy; UI chỉ chỉnh params, không editor code |
| Deploy | Docker Compose (app + postgres) / VPS gần Binance | |

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

## 4. Roadmap (theo phase, giảm rủi ro dần)

| Phase | Hạng mục | User Stories | Kết quả |
|---|---|---|---|
| **P1** | Market feed + Chart realtime | US-01,02,03,24,25 | Thấy chart sống động sát sàn |
| **P2** | Strategy base + Paper executor | US-05,12,16 | Bot paper chạy, PnL realtime |
| **P3** | Order Manager + can thiệp tay | US-17,18,19,20,21 | Đóng/sửa lệnh, audit log |
| **P4** | Backtest | US-09,10,11 | Metrics + equity curve |
| **P5** | Strategy versioning + params UI | US-06,07,08 | Nhiều version, chỉnh từ UI |
| **P6** | Testnet integration | US-13,15 | Lệnh thật môi trường giả |
| **P7** | Scanner đề xuất | US-22,23 | Quét cặp + tín hiệu |
| **P8** | Live + rào chắn an toàn | US-14,26,27 | Live có cờ + confirm |

> Thứ tự cố ý: an toàn (paper/backtest) trước, tiền thật (live) sau cùng.

## 5. Quyết định kiến trúc đáng nhớ
- **Một interface Strategy/Context** cho cả 4 mode → không lệch logic backtest vs live (rủi ro RK-4).
- **Python không nằm trên hot-path đặt lệnh phức tạp** vì single-user tải thấp → asyncio đủ, không cần Go/NATS giai đoạn này.
- **Ranh giới mode bằng config + cờ Live riêng** → chống nhầm lệnh thật (RK-1).
- **Auto-cancel limit theo timeout** → NFR "không để lệnh quá lâu" (RK-2).

## 6. Quyết định đã chốt ✅
1. **Không đa sàn** → python-binance, bỏ lớp trừu tượng ccxt.
2. **Postgres + TimescaleDB** từ đầu (không SQLite).
3. **Chart: Lightweight Charts trước, Charting Library sau.** Lý do: form xin Charting Library cần public URL/domain (chưa có lúc dev). Lightweight Charts cài ngay từ npm, miễn phí. Khi đã deploy có domain + được duyệt repo → swap sang Charting Library để có **drawing tools**.
4. **Strategy sửa ngoài app** (trong repo/IDE), app chỉ load & chạy. UI chỉ chỉnh params + chọn version, **không có code editor trong app**.

### Hệ quả kiến trúc của (4)
- Chiến thuật = file `.py` trong `app/strategy/strategies/`, đăng ký qua registry.
- App load module → đọc metadata (name, version, default params) → lưu/sync vào DB.
- Chỉnh thuật toán = sửa file + reload; chỉnh hành vi nhẹ = đổi params từ UI.
- Versioning: tăng `version` trong file là nguồn sự thật; DB lưu version + params instance đang chạy.
