# RSI Reversal — Đảo chiều theo RSI

> Trường phái: **Mean-reversion** (hồi quy về trung bình). Khung gợi ý: 15m–4h. Hợp thị trường dao động trong biên.

## Ý tưởng

RSI (Relative Strength Index, Welles Wilder) đo **tốc độ & độ lớn** biến động giá, dao động 0–100. Giả thuyết mean-reversion: khi giá bị đẩy **quá xa** một chiều (quá bán/quá mua), nó có xu hướng **bật ngược** về vùng cân bằng.

## Công thức

```
RS = trung bình tăng (gains) / trung bình giảm (losses)   — làm mượt Wilder
RSI = 100 − 100 / (1 + RS)
```

- `RSI < 30` → **quá bán** (oversold).
- `RSI > 70` → **quá mua** (overbought).

## Quy tắc vào/ra lệnh

| Điều kiện | Hành động | Logic |
|---|---|---|
| `RSI < oversold` | **BUY** (LONG) | bắt đáy, kỳ vọng bật lên |
| `RSI > overbought` | **SELL** (SHORT) | bắt đỉnh, kỳ vọng rơi xuống |

> Đây là chiến thuật **ngược xu hướng** — cần cẩn trọng (xem Nhược điểm).

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `period` | 14 | Chu kỳ RSI. |
| `oversold` | 30 | Ngưỡng quá bán → BUY. |
| `overbought` | 70 | Ngưỡng quá mua → SELL. |
| `size` | 0.001 | Khối lượng. |

## Ưu / Nhược

- ✅ Hiệu quả trong **sideway** / biên dao động — mua thấp bán cao.
- ✅ Tín hiệu rõ ràng, dễ hiểu.
- ❌ **Nguy hiểm trong xu hướng mạnh**: RSI có thể "quá mua/bán" kéo dài → bắt dao rơi ngược xu hướng dễ lỗ nặng.
- ❌ Không có SL thì rủi ro đuôi lớn.

## Khi nào dùng

- Thị trường **đi ngang**, biên dao động ổn định.
- Nên kết hợp **lọc xu hướng** (vd chỉ BUY khi giá còn trên EMA dài) hoặc bật SL để tránh kẹt khi thị trường breakout.

## Lưu ý khi backtest

- Thử các ngưỡng (20/80, 30/70) và `period`.
- Backtest qua cả giai đoạn **trending** lẫn **sideway** để thấy điểm yếu khi có xu hướng.
- Để ngược-xu-hướng an toàn hơn: cân nhắc chỉ vào khi RSI **thoát** khỏi vùng cực (cross back) thay vì khi đang ở trong.
