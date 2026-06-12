# Volatility Breakout (Larry Williams k-range)

> File chiến thuật: `vol_breakout.py` · version 1

## Ý tưởng

Larry Williams: **ngày biến động mạnh thường tiếp diễn** — nếu trong ngày giá thoát khỏi
vùng mở cửa một đoạn ≥ k × range hôm trước thì xác suất cao hôm nay là "ngày trend",
đi tiếp theo hướng breakout đến hết ngày. Rất phổ biến trong giới quant crypto Hàn Quốc
(Upbit/Bithumb, k≈0.5). Nguồn: cộng đồng (không peer-review) — bằng chứng mức TRUNG BÌNH-YẾU,
phải tự kiểm chứng bằng walk-forward.

## Quy tắc

| Điều kiện | Hành động |
|---|---|
| close vượt `open_ngày + k × (high_hômqua − low_hômqua)` | **BUY** (1 lần/ngày) |
| close thủng `open_ngày − k × range_hômqua` (nếu `direction=1`) | **SELL** (1 lần/ngày) |
| Nến đầu ngày UTC kế tiếp | **CLOSE** (thoát toàn bộ) |
| close chạm SL (open ngày hoặc ATR) | **CLOSE**, không re-entry chiều đó trong ngày |

Ngày tính theo **UTC** (crypto 24/7 không có giờ mở cửa thật — đây là điểm phải sweep).
Lọc trend EMA (`trend_len`>0): chỉ LONG khi close > EMA, SHORT khi close < EMA.

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `k` | 0.5 | Hệ số nhân range hôm trước. |
| `direction` | 1 | 0 = long-only · 1 = hai chiều. |
| `trend_len` | 0 | EMA lọc trend trên TF hiện tại (0 = tắt). |
| `sl_mode` | 1 | 0 = không SL · 1 = SL về open ngày · 2 = SL theo ATR. |
| `atr_len` / `atr_mult` | 14 / 1.5 | SL ATR (sl_mode=2). |
| `entry_cutoff_h` | 22 | Không vào lệnh mới sau giờ này (UTC). |
| `size` | 0.001 | Khối lượng. |

## Ưu / Nhược

- ✅ 0–1 lệnh/ngày/cặp, lãi kỳ vọng/lệnh lớn (bắt ngày trend) → chịu được phí taker.
- ✅ Chỉ cần OHLCV; logic đơn giản, ít tham số → khó overfit hơn.
- ❌ Sideways/vol thấp → chuỗi thua nhỏ liên tục (false breakout).
- ❌ Nhạy với k và mốc "mở ngày" (00:00 UTC vs giờ khác); decay sau 2018 trên BTC (báo cáo cộng đồng).

## Khi nào dùng

- Nến 15m–1h (cần fill intraday sát mức breakout). Thị trường có những ngày trend mạnh (alt vol cao).

## Lưu ý backtest

- Engine fill theo close nến → giá vào hơi xấu hơn mức breakout lý thuyết (chấp nhận được ở 15m).
- SL kiểm theo close (không intrabar) — nhất quán với các strategy khác trong repo.

## Nghiên cứu (skill strategy-research)

Bối cảnh chọn ứng viên: khảo sát web (Concretum/Quantpedia/học thuật 2020–2026) + screening 12
classic có sẵn (180d × 6 thị trường, default params → TẤT CẢ âm ở 15m; phí nghiền chiến thuật
vào-ra dày). vol_breakout được chọn vì 0–1 lệnh/ngày, lãi/lệnh lớn.

- **Sweep** (`scripts/sweep_vol_breakout.py`, 48 bộ × BTC/ETH/SOL 15m + BTC 1h, 90d):
  cao nguyên ổn định k=0.5–0.7 hai chiều đều dương 4/4 thị trường. Bộ đỉnh `k=0.6 dir=1 sl=0`
  PnL TB +20.5%, thị trường tệ nhất +9.8%, win ~50% — nhưng maxDD ~25%.
- **Long-only TỆ HƠN hai chiều** (sweep: dir=0 → 1/4 dương): short đóng góp lớn (nửa đầu 180d
  là regime giảm); nửa sau hai chiều đều dương ~+7–8% → giữ direction=1.
- **Chẩn đoán lỗ** (`scripts/diag_vol_breakout.py` + `diag_vol_breakout2.py`, 270 lệnh/180d):
  các pattern "16–19h âm", "thứ Hai âm", "thứ Bảy âm" KHÔNG ổn định qua 2 nửa → là nhiễu regime,
  KHÔNG thêm filter (tránh overfit).
- **SL không cứu DD**: cap-lỗ trên giấy (−2.5%/lệnh) cải thiện cả 2 nửa, nhưng SL THẬT
  (sl_mode=3) thoát tại close và bỏ lỡ hồi giá → SOL +18.4%→+1.7%, DD gần như không giảm.
  DD đến từ CHUỖI tuần chop thua, không phải đuôi lỗ đơn lẻ. Mặc định dùng sl_mode=0
  (exit duy nhất = đầu ngày sau) khi đánh giá; SL chỉ là tùy chọn vận hành.
- **Noise-k (k_mode=1) là fix mô hình ăn tiền** (walk-forward tuần 180d, 3 cặp 15m):
  `noise_len=40` so với k cố định 0.6: BTC +21.2% DD **9.7%** (từ +11.7/16.2), ETH +45.8%
  DD 13.7%, SOL +31.3% DD 15.9% (từ +18.4/22.6); tuần tệ nhất −11%→−6.4%; cả 2 nửa
  (OOS/IS) dương trên CẢ 3 cặp. Kỹ thuật có tài liệu gốc (systrader79), không phải fit cửa sổ.
- **Quét rổ 6 cặp** (k cố định 0.6): BTC/ETH/SOL/XRP dương, DOGE/AVAX âm nhẹ.

(Verdict cập nhật ở cuối — xem commit research mới nhất.)
