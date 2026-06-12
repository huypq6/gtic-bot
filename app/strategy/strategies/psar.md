# Parabolic SAR — Stop and Reverse

> Trường phái: **Trend-following / trailing stop**. Khung gợi ý: 15m–1d. Hợp xu hướng rõ.

## Ý tưởng

Parabolic SAR (Welles Wilder) vẽ các "chấm" bám theo giá, đóng vai trò **trailing stop** và **đảo chiều**. Chấm nằm **dưới giá** = xu hướng tăng; khi giá chạm chấm → **đảo** sang giảm (và ngược lại). Tốc độ bám tăng dần theo hệ số gia tốc (AF).

## Công thức

```
SAR_next = SAR + AF × (EP − SAR)
EP  = đỉnh cao nhất (uptrend) / đáy thấp nhất (downtrend) kể từ khi vào xu hướng
AF  = bắt đầu = step (0.02), +step mỗi khi có EP mới, tối đa max_af (0.2)
Đảo chiều khi giá xuyên qua SAR.
```

## Quy tắc vào/ra lệnh

| Điều kiện | Hành động |
|---|---|
| SAR đảo từ giảm → **tăng** (dir −1 → +1) | **BUY** (LONG) |
| SAR đảo từ tăng → **giảm** (dir +1 → −1) | **SELL** (SHORT) |

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `step` | 0.02 | Gia tốc khởi đầu (AF). |
| `max_af` | 0.2 | Trần gia tốc. |
| `size` | 0.001 | Khối lượng. |

## Ưu / Nhược

- ✅ Trailing stop tự nhiên, luôn có điểm thoát; bám xu hướng tốt.
- ❌ **Sideway**: đảo liên tục (whipsaw) → thua nhiều lệnh nhỏ.
- ❌ Vào/ra muộn ở đầu và cuối sóng.

## Khi nào dùng

- Thị trường có xu hướng. Thường **kết hợp** chỉ báo xác nhận xu hướng (ADX, EMA) để lọc whipsaw.

## Lưu ý khi backtest

- `step` lớn → nhạy, nhiều đảo; nhỏ → mượt, trễ. Thử trên nhiều giai đoạn.
