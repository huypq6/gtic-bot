# Stochastic Oscillator — Quá mua / quá bán

> Trường phái: **Mean-reversion**. Khung gợi ý: 15m–4h. Hợp thị trường dao động.

## Ý tưởng

Stochastic (George Lane) so sánh giá đóng cửa với **biên độ cao–thấp** gần đây. Giả thuyết: trong xu hướng tăng, giá đóng gần đỉnh; trong giảm, gần đáy. Khi %K rơi vào vùng cực → kỳ vọng đảo chiều.

## Công thức

```
%K = 100 × (close − LL_period) / (HH_period − LL_period)
```
(LL/HH = đáy/đỉnh thấp/cao nhất trong `period` nến.) %K → 0 = quá bán, → 100 = quá mua.

## Quy tắc vào/ra lệnh

| Điều kiện | Hành động |
|---|---|
| `%K < oversold` (vd 20) | **BUY** — quá bán |
| `%K > overbought` (vd 80) | **SELL** — quá mua |

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `period` | 14 | Chu kỳ tính HH/LL. |
| `oversold` | 20 | Ngưỡng quá bán → BUY. |
| `overbought` | 80 | Ngưỡng quá mua → SELL. |
| `size` | 0.001 | Khối lượng. |

## Ưu / Nhược

- ✅ Nhạy, bắt đảo chiều sớm trong sideway.
- ❌ Trong **xu hướng mạnh**, %K dính vùng cực kéo dài → tín hiệu ngược xu hướng dễ lỗ.

## Khi nào dùng

- Thị trường đi ngang. Nên lọc bằng xu hướng (vd chỉ BUY khi giá trên EMA dài) hoặc thêm SL.

## Lưu ý khi backtest

- Thử ngưỡng (20/80, 30/70) và `period`. Backtest qua cả giai đoạn trending để thấy điểm yếu.
