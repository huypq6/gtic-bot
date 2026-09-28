# Supertrend — Theo xu hướng dựa trên ATR

> Trường phái: **Trend-following**. Khung gợi ý: 15m–4h. Hợp xu hướng rõ.

## Ý tưởng

Supertrend vẽ một đường bám theo giá, **đổi phía** khi xu hướng đảo chiều. Dùng **ATR** (biến động) để đặt dải đệm, giúp lọc nhiễu tốt hơn đường đơn thuần. Đường nằm **dưới giá** = xu hướng tăng (long), nằm **trên giá** = xu hướng giảm (short).

## Công thức

```
hl2          = (high + low) / 2
basicUpper   = hl2 + mult × ATR(period)
basicLower   = hl2 − mult × ATR(period)
finalUpper/finalLower: làm "trượt" theo giá đóng để chống nhiễu
direction    = +1 (uptrend) nếu giá đóng trên finalUpper, −1 ngược lại (có nhớ trạng thái)
```

## Quy tắc vào/ra lệnh

| Điều kiện | Hành động |
|---|---|
| direction đảo từ −1 → **+1** | **BUY** (vào LONG) |
| direction đảo từ +1 → **−1** | **SELL** (vào SHORT) |

Chỉ vào lệnh đúng lúc **đổi chiều** (so sánh `direction[-2]` với `direction[-1]`).

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `period` | 10 | Chu kỳ ATR. |
| `mult` | 3.0 | Hệ số nhân ATR (dải đệm). Lớn → ít đổi chiều, ít nhiễu nhưng trễ. |
| `size` | 0.001 | Khối lượng. |

## Ưu / Nhược

- ✅ Bám xu hướng tốt, lọc nhiễu nhờ ATR; quy tắc rõ ràng, ít đổi chiều giả.
- ❌ Trong sideway vẫn bị whipsaw (giảm bằng `mult` lớn hơn).
- ❌ Vào trễ sau khi xu hướng đã xác lập.

## Khi nào dùng

- Thị trường có xu hướng, biến động vừa–lớn. Tăng `mult` nếu nhiễu nhiều.

## Lưu ý khi backtest

- Quét `(period, mult)`; bộ phổ biến 10/3 hoặc 7/3.
- So với Donchian/EMA cross trên cùng dữ liệu để chọn bộ lọc xu hướng phù hợp.
