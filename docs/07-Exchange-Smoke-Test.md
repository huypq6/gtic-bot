# 07 — Smoke test tài khoản sàn (P9b · Binance USDⓈ-M Futures)

P9b đã code + test bằng mock (không gọi sàn). File này là checklist chạy **khi có key thật**.
Làm TESTNET trước; LIVE chỉ sau khi TESTNET qua hết.

## 0. Chuẩn bị key
- TESTNET: đăng nhập https://testnet.binancefuture.com → API Key → `.env`:
  `BINANCE_TESTNET_KEY=... BINANCE_TESTNET_SECRET=...` (ví testnet có sẵn USDT ảo).
- LIVE (sau cùng): key Binance **chỉ bật Futures + Reading**, TẮT rút tiền, whitelist IP VPS →
  `BINANCE_KEY/SECRET` + `ENABLE_LIVE=1`.
- Tài khoản Futures để **One-way mode** (không Hedge) — app giả định 1 vị thế/cặp.
- Restart app (`docker compose up --build -d`) để đọc `.env`.

## 1. Tài khoản & đồng bộ
- [ ] Tài khoản → Tài khoản mới → Loại TESTNET → Tạo. Kỳ vọng: số dư = ví USDT Futures testnet,
      sổ cái có dòng "Số dư ban đầu trên sàn", không có `sync_error`.
- [ ] Bấm "Đồng bộ ngay" → `last_sync_at` cập nhật. Khả dụng/ký quỹ khớp trang Binance.
- [ ] Chuyển thêm USDT vào ví Futures (testnet: nút Faucet/Transfer) → ≤15s sổ cái có dòng "Nạp".
- [ ] Nhập sai key → `sync_error` hiện đỏ ("Invalid API-key"), app không sập.

## 2. Lệnh tay qua bot / khối lượng
- [ ] Tạo bot TESTNET (BTCUSDT 15m, tài khoản testnet, rủi ro 0.5%/lệnh, đòn bẩy 3–5×).
      Chưa có tín hiệu? Tạm dùng strategy tần suất cao để thử rồi xóa bot.
- [ ] Khi bot vào lệnh — trên Binance testnet kiểm:
  - [ ] đòn bẩy cặp = đòn bẩy tài khoản;
  - [ ] khối lượng đã làm tròn theo stepSize, ≈ rủi ro% × equity / khoảng cách SL;
  - [ ] có 2 lệnh điều kiện **STOP_MARKET + TAKE_PROFIT_MARKET (Close position)** — mục
        "Conditional/Algo orders". Thiếu → app phát cảnh báo "không đặt được SL/TP trên sàn" và
        tự cắt client-side (xem log).
- [ ] Sửa SL/TP trên trang Orders → lệnh điều kiện cũ bị hủy, lệnh mới đúng giá.

## 3. Đóng lệnh
- [ ] Để SL/TP khớp **trên sàn** → ≤5s vị thế trong app CLOSED, lý do SL/TP, giá = fill thật,
      PnL = realizedPnl − phí sàn; chân còn lại bị hủy (không còn lệnh điều kiện mồ côi).
- [ ] Đóng tay trong app → lệnh MARKET **reduceOnly**; không bao giờ mở vị thế ngược.
- [ ] Đóng tay trên app Binance → app ghi CLOSED lý do EXTERNAL.
- [ ] Tín hiệu đảo chiều → 2 lệnh: đóng reduceOnly rồi mở chiều mới.
- [ ] Sổ cái: REALIZED_PNL + FEE (COMMISSION) + FUNDING (nếu qua mốc funding) khớp
      Transaction History của Binance; số dư sổ = ví Futures.

## 4. Restart & rào chắn
- [ ] Có vị thế mở → restart container → bot nạp lại vị thế + id SL/TP (không đặt trùng).
- [ ] Vị thế bị SL trong lúc app tắt → sau khi bật, ghi CLOSED theo fill thật.
- [ ] Đặt "Lỗ tối đa/ngày" rất nhỏ → sau 1 lệnh thua, tín hiệu mới bị chặn (audit RISK_REJECT).

## 5. LIVE (chỉ khi 1–4 qua hết trên TESTNET)
- [ ] Không có `ENABLE_LIVE=1` → tạo tài khoản LIVE bị 403.
- [ ] Có → phải gõ "LIVE". Vốn nhỏ, rủi ro ≤0.5%/lệnh, 1 bot, theo dõi tay 1–2 tuần.

## Giới hạn đã biết
- Đối chiếu vị thế bằng polling 5s (chưa dùng user-data stream) → trễ tối đa ~5s.
- Phí trả bằng BNB không vào sổ USDT (nên tắt "dùng BNB trả phí" để sổ khớp ví).
- 1 cặp key/mode → 1 tài khoản TESTNET + 1 LIVE.
- Lệnh tay trên trang Trading vẫn chỉ PAPER.
