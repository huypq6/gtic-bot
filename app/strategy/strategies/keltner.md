# Keltner Channel Breakout — Bứt phá kênh EMA ± ATR

> Trường phái: **Trend / Momentum (breakout)**. Khung gợi ý: 15m–1d.

## Ý tưởng

Kênh Keltner (Chester Keltner) đặt dải quanh một EMA, độ rộng theo **ATR** (biến động). Khác Bollinger (dùng độ lệch chuẩn), Keltner dùng ATR nên mượt hơn. Bản này dùng theo hướng **breakout**: giá bứt khỏi dải báo hiệu động lượng mạnh.

## Công thức

```
mid   = EMA(close, period)
upper = mid + mult × ATR(period)
lower = mid − mult × ATR(period)
```

## Quy tắc vào/ra lệnh

| Điều kiện | Hành động |
|---|---|
| `giá > dải trên` | **BUY** (bứt phá lên) |
| `giá < dải dưới` | **SELL** (bứt phá xuống) |

> Lưu ý: đây là bản **breakout** (ngược với Bollinger reversion). Tùy thị trường, có thể đảo logic thành reversion.

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `period` | 20 | Chu kỳ EMA + ATR. |
| `mult` | 2.0 | Hệ số nhân ATR (độ rộng kênh). |
| `size` | 0.001 | Khối lượng. |

## Ưu / Nhược

- ✅ Bắt động lượng/bứt phá; dải mượt nhờ ATR, ít nhiễu hơn Bollinger trong một số trường hợp.
- ❌ Breakout giả trong sideway; vào sau khi giá đã bứt.

## Khi nào dùng

- Thị trường sắp/đang có động lượng mạnh. Kết hợp lọc xu hướng để giảm breakout giả.

## Lưu ý khi backtest

- So sánh **breakout vs reversion** trên cùng dữ liệu để chọn hướng phù hợp cặp/khung.
- Thử `mult` 1.5–2.5.
