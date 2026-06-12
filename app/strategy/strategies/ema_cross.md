# EMA Crossover — Giao cắt trung bình động

> Trường phái: **Trend-following**. Có 2 phiên bản: **v1** (cơ bản) và **v2** (thêm bộ lọc gap%).

## Ý tưởng

EMA (Exponential Moving Average) làm mượt giá, đặt trọng số cao hơn cho dữ liệu gần. Dùng **hai EMA** chu kỳ khác nhau: đường **nhanh** (fast) phản ứng nhanh, đường **chậm** (slow) phản ứng chậm. Khi nhanh cắt chậm → tín hiệu đổi xu hướng.

## Công thức

```
EMA_t = giá_t × k + EMA_(t-1) × (1 − k),   k = 2 / (period + 1)
```

Xét 2 điểm cuối của mỗi EMA (`prev`, `now`):

- **Golden cross**: `fast` cắt **lên** `slow` (fast_prev ≤ slow_prev và fast_now > slow_now).
- **Death cross**: `fast` cắt **xuống** `slow`.

## Quy tắc vào/ra lệnh

| Điều kiện | Hành động |
|---|---|
| Golden cross | **BUY** (LONG) |
| Death cross | **SELL** (SHORT) |
| Ngược chiều | Flip (đóng + mở chiều mới) |

## v2 — Bộ lọc khoảng cách (gap%)

v1 trên khung nhỏ (1m) hay vào lệnh khi 2 EMA dính sát nhau → **giao cắt nhiễu**, phí ăn mòn lợi nhuận. **v2** chỉ vào lệnh khi:

```
|EMA_fast − EMA_slow| / EMA_slow × 100 ≥ gap_pct
```

→ bỏ qua giao cắt yếu, **giảm số lệnh giả**. Thực nghiệm (backtest BTC 5m): v1 ≈ −20% / 91 lệnh, v2 ≈ +3.6% / 1 lệnh — bộ lọc giảm overtrade rõ rệt.

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `fast` | 9 | Chu kỳ EMA nhanh. |
| `slow` | 21 | Chu kỳ EMA chậm (> fast). |
| `size` | 0.001 | Khối lượng. |
| `gap_pct` | 0.1 | (v2) Ngưỡng % khoảng cách 2 EMA để vào lệnh. |

## Ưu / Nhược

- ✅ Đơn giản, bắt xu hướng tốt; v2 lọc nhiễu hiệu quả.
- ❌ Trong sideway: cắt qua cắt lại liên tục (whipsaw).
- ❌ Tín hiệu trễ (EMA là chỉ báo trễ).

## Khi nào dùng

- Thị trường có xu hướng. Khung trung bình trở lên.
- Trên khung nhỏ → ưu tiên **v2** (gap filter) để giảm lệnh giả.

## Lưu ý khi backtest

- Quét cặp `(fast, slow)` nhưng cẩn thận overfit; ưu tiên cặp "tròn" phổ biến (9/21, 12/26, 50/200).
- So sánh **v1 vs v2** ở trang Backtest → "So sánh version".
