# Grid — Giao dịch lưới quanh mốc tham chiếu

> Trường phái: **Mean-reversion / harvest dao động**. Khung gợi ý: 5m–1h. Hợp thị trường đi ngang.

## Ý tưởng

Grid trading đặt một "lưới" các mức mua/bán cách đều quanh một mốc; khi giá **dao động lên xuống**, ta liên tục **mua thấp – bán cao** để gom lợi nhuận từ biên độ, không cần đoán hướng. Hợp nhất với thị trường **sideway**.

## Lưu ý mô hình

Engine ở đây cho **1 bot = 1 vị thế** (không nhiều lệnh lưới đồng thời như grid cổ điển). Bản này là **grid 1 nấc/1 vị thế**: vào lệnh khi giá lệch `step_pct` khỏi mốc, **chốt khi giá quay về mốc**, rồi lặp lại — vẫn nắm tinh thần "harvest dao động".

## Công thức & quy tắc

```
mốc (ref) = SMA(close, period)
lower = ref × (1 − step_pct%)      upper = ref × (1 + step_pct%)
```

| Trạng thái | Điều kiện | Hành động |
|---|---|---|
| Đang flat | giá ≤ lower | **BUY** (mua 1 nấc dưới mốc) |
| Đang flat | giá ≥ upper | **SELL** (bán khống 1 nấc trên mốc) |
| Đang LONG | giá ≥ ref | **CLOSE** (chốt khi về mốc) |
| Đang SHORT | giá ≤ ref | **CLOSE** (chốt khi về mốc) |

> Đây là strategy **đọc `ctx.position`** để quyết định chốt/mở.

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `period` | 20 | Chu kỳ SMA làm mốc tham chiếu. |
| `step_pct` | 1.0 | Độ rộng 1 nấc lưới (% từ mốc). |
| `size` | 0.001 | Khối lượng mỗi nấc. |

## Ưu / Nhược

- ✅ Sinh lời đều trong **sideway**; không cần đoán hướng.
- ❌ **Nguy hiểm khi trend mạnh**: giá đi một chiều xa mốc → vị thế lỗ kéo dài (không có lưới nhiều tầng để bình quân). Nên thêm SL hoặc giới hạn.
- ❌ Bản 1-nấc đơn giản hơn grid nhiều tầng cổ điển.

## Khi nào dùng

- Thị trường tích lũy/đi ngang, biên độ ổn định. Tránh giai đoạn xu hướng mạnh hoặc thêm rào chắn rủi ro.

## Lưu ý khi backtest

- Thử `step_pct` theo biến động cặp; quá nhỏ → nhiều lệnh + phí, quá lớn → ít cơ hội.
- Backtest cả giai đoạn trend để thấy rủi ro vị thế kẹt.
