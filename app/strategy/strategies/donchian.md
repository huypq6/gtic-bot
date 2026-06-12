# Donchian Breakout — Phá kênh giá

> Trường phái: **Trend-following** (theo xu hướng). Khung gợi ý: 1h–1d. Cặp: thanh khoản cao.

## Ý tưởng

Donchian Channel do Richard Donchian đề xuất — một trong những hệ thống trend-following kinh điển (nền tảng của "Turtle Traders"). Giả thuyết: khi giá **phá vỡ** vùng dao động gần đây (đỉnh/đáy của N nến), nó thường **mở đầu một xu hướng mới** đủ mạnh để có lời.

## Công thức

Với `period = N`, tại mỗi nến đã đóng:

- **Đỉnh kênh** = giá cao nhất (`high`) của **N nến TRƯỚC** nến hiện tại.
- **Đáy kênh** = giá thấp nhất (`low`) của N nến trước.

> Loại nến hiện tại ra khỏi cửa sổ để **tránh lookahead** (không dùng chính nó để so sánh với nó).

## Quy tắc vào/ra lệnh

| Điều kiện | Hành động |
|---|---|
| `giá hiện tại > Đỉnh kênh` | **BUY** (vào LONG) — phá đỉnh |
| `giá hiện tại < Đáy kênh` | **SELL** (vào SHORT) — thủng đáy |
| Tín hiệu ngược chiều | Engine tự **đóng vị thế cũ rồi mở chiều mới** (flip) |

Quản trị rủi ro tùy chọn: bật `sl_pct` / `tp_pct` (% từ giá vào) để engine tự cắt SL/TP mỗi tick.

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `period` | 20 | Độ rộng kênh. Lớn → ít tín hiệu, bắt xu hướng dài; nhỏ → nhạy, nhiều nhiễu. |
| `size` | 0.001 | Khối lượng (base units). |
| `sl_pct` | 0 (tắt) | Stop-loss theo % từ giá vào. |
| `tp_pct` | 0 (tắt) | Take-profit theo % từ giá vào. |

## Ưu / Nhược

- ✅ Bắt được các xu hướng lớn; quy tắc đơn giản, khách quan, dễ backtest.
- ✅ Không phụ thuộc dự đoán đỉnh/đáy.
- ❌ **Sideway**: nhiều breakout giả → thua liên tiếp (whipsaw).
- ❌ Vào lệnh trễ (sau khi giá đã phá) → bỏ lỡ phần đầu sóng.

## Khi nào dùng

- Thị trường/cặp có **xu hướng rõ**, biến động đủ lớn.
- Khung **trung–dài** (1h trở lên) để giảm breakout giả.
- Cân nhắc thêm bộ lọc xu hướng (vd chỉ LONG khi giá > EMA dài) nếu muốn giảm nhiễu.

## Lưu ý khi backtest

- Thử nhiều `period` (10/20/55) trên **nhiều cặp + nhiều giai đoạn** — tránh chọn 1 giá trị "đẹp" (overfit).
- Tính cả **phí**; trend-following ít lệnh nên phí ảnh hưởng vừa phải, nhưng whipsaw vùng sideway có thể ăn mòn.
- Đánh giá `max_dd` (chuỗi thua khi sideway) và độ dài thắng trung bình.
