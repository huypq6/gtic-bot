# 06 — Paper Trading Runbook (rổ ict_po3 v4)

> Cách kích hoạt paper-trade rổ cặp đã kiểm chứng (ict_po3 v4) ở chế độ **prod**, theo dõi forward.
> Cập nhật: 2026-06-17. Nguồn quyết định rổ cặp: `app/strategy/strategies/ict_po3.md` (mục Nghiên cứu).

## Rổ khuyến nghị (sau walk-forward 365 ngày)

| Cặp | TF | Strategy | Đòn bẩy mục tiêu | PnL/365d (backtest) | maxDD |
|---|---|---|---|---|---|
| **BTCUSDT** | 15m | ict_po3 v4 | ×2–3 | +9.2% (×2) … +13.8% (×3) | 6.5% / 9.7% |
| **DOGEUSDT** | 15m | ict_po3 v4 | ×3 | +11.8% | 5.0% |
| **SUIUSDT** | 15m | ict_po3 v4 | ×1 | +2.8% | 6.2% |

Chia vốn đều → kỳ vọng ~+8–9%/năm, DD danh mục ước < 7%. Params để **mặc định** (đừng chỉnh).

> Chỉ 3/14 cặp dương trên 365 ngày. 11 cặp còn lại (ETH, SOL, XRP, ADA, BNB, AVAX, DOT, LINK,
> LTC, NEAR, INJ) đều âm — KHÔNG thêm vào rổ. Xem `ict_po3.md` để biết chi tiết.

## 1. Chạy prod

```bash
cd ~/gtic-bot
docker compose up --build -d     # tự chạy `alembic upgrade head` + serve UI & API tại :8000
```

- Mở `http://localhost:8000` (hoặc `http://<IP-VPS>:8000`).
- **Mode PAPER không cần API key** — feed dùng WebSocket public của Binance, khớp lệnh nội bộ.
- Chỉ cần file `.env` tồn tại (compose đọc qua `env_file`). KHÔNG cần `ENABLE_LIVE` cho paper.
- Kiểm tra sống: `curl -s localhost:8000/api/config` trả về watchlist + tf.

Tắt: `docker compose down` (giữ data) — volume `pgdata` lưu lịch sử nến + bot + lệnh.

> **Cổng DB:** host map `15432:5432` (không phải 5432) để tránh đụng Postgres chạy sẵn ở host.
> App nối DB qua mạng nội bộ docker (`db:5432`) nên không ảnh hưởng. Truy cập DB từ host:
> `psql -h localhost -p 15432 -U botuser tradingbot`. Nếu vẫn báo `port is already allocated`
> ở 8000 → đổi `8000:8000` tương tự, hoặc `docker compose down --remove-orphans` rồi up lại.

## 2. Thêm cặp vào watchlist (BẮT BUỘC trước khi tạo bot)

Feed mặc định chỉ stream `BTCUSDT` + `ETHUSDT` (`settings.default_symbols`). Bot subscribe kênh
`kline.<symbol>.15m`, nên cặp phải có trong feed trước.

- UI: trang **Dashboard** → ô watchlist → thêm `DOGEUSDT` và `SUIUSDT`.
- (BTCUSDT đã có sẵn.)

## 3. Tạo 3 bot (trang Trading → "Tạo bot (PAPER)")

Cả 3 bot giống nhau: strategy **ict_po3 v4**, TF **15m**, mode **PAPER**, params **mặc định**.
Khác nhau ở **`size`** (khối lượng) — đây là cách thể hiện đòn bẩy ở paper (không có ô leverage riêng).

### Công thức size

```
size = (vốn_phân_bổ_cho_cặp × đòn_bẩy) / giá_hiện_tại
```

Ví dụ vốn ảo 1.000 USDT/cặp, lấy giá lúc tạo bot:

| Bot | Đòn bẩy | size (ví dụ giá tham khảo) |
|---|---|---|
| BTCUSDT | ×2–3 | `2000–3000 / giá_BTC` → BTC ~100k ⇒ `0.02–0.03` |
| DOGEUSDT | ×3 | `3000 / giá_DOGE` → DOGE ~0.2 ⇒ `~15000` |
| SUIUSDT | ×1 | `1000 / giá_SUI` → SUI ~3 ⇒ `~330` |

> Thay giá tham khảo bằng giá thực tại thời điểm tạo bot. size không cần tròn đẹp.

## 4. Theo dõi & kỳ vọng đúng

- **Rất ít lệnh là BÌNH THƯỜNG**: cả rổ ~50 lệnh/năm (~1 lệnh/tuần). Nhiều ngày im lặng ≠ lỗi.
- Lệnh chỉ vào **sau 8h UTC** (hết phiên Asia), **không vào sau 15h UTC**, **flatten 21h UTC** —
  KHÔNG giữ qua đêm. Thấy lệnh giữ qua 00:00 UTC ⇒ báo bug.
- Trang **Orders**: danh sách lệnh + PnL realtime. Trang **Audit**: mọi quyết định ghi log TRƯỚC khi khớp.
- Mất feed → bot tự **pause** + tự reconnect (NFR an toàn).

### Tiêu chí xác nhận forward (4–8 tuần)

- PnL cùng dấu & cùng cỡ backtest: BTC ×3 ≈ +1%/tháng; DD tháng tệ nhất không quá ~−7%.
- Lệch xa (vd tháng −10%+, hoặc nhiều tuần âm liên tiếp) ⇒ **dừng bot**, xem lại trước khi nghĩ đến testnet.

## 5. Bước sau (KHÔNG tự nhảy)

Paper khớp kỳ vọng ≥ 4–8 tuần → cân nhắc **TESTNET** (cần key testnet Binance) → mới đến LIVE
(cần `ENABLE_LIVE=1` + gõ xác nhận "LIVE", key tắt quyền rút + whitelist IP VPS). Xem CLAUDE.md mục An toàn.

## Phụ lục — scripts nghiên cứu liên quan

| Script | Mục đích |
|---|---|
| `scripts/scan365_ict_po3_v4.py` | Quét 14 cặp trên 365 ngày (chọn rổ) |
| `scripts/leverage_ict_po3_v4.py` | Đo DD theo đòn bẩy 1–4× (chọn mức) |
| `scripts/walkforward_365_ict_po3_v4.py` | Walk-forward cửa sổ 30 ngày |
