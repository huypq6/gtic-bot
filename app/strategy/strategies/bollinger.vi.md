# Bollinger Bands Reversion — Hồi quy về dải giữa

> Trường phái: **Mean-reversion**. Khung gợi ý: 15m–4h. Hợp thị trường dao động trong biên.

## Ý tưởng

Dải Bollinger (John Bollinger) gồm: **dải giữa** = SMA(period), **dải trên/dưới** = giữa ± mult × độ lệch chuẩn. Khoảng ±2σ bao phủ ~95% biến động. Giả thuyết mean-reversion: giá chạm **dải biên** thường bị "kéo" về dải giữa.

## Công thức

```
mid   = SMA(close, period)
sd    = stdev(close, period)
upper = mid + mult × sd
lower = mid − mult × sd
```

## Quy tắc vào/ra lệnh

| Điều kiện | Hành động |
|---|---|
| `giá ≤ dải dưới` | **BUY** — quá bán, kỳ vọng bật về mid |
| `giá ≥ dải trên` | **SELL** — quá mua, kỳ vọng rơi về mid |

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `period` | 20 | Chu kỳ SMA + độ lệch chuẩn. |
| `mult` | 2.0 | Hệ số nhân độ lệch chuẩn (độ rộng dải). |
| `size` | 0.001 | Khối lượng. |

## Ưu / Nhược

- ✅ Hiệu quả khi thị trường **sideway**, biên ổn định.
- ❌ Khi **bứt phá xu hướng** (band expansion), giá có thể "đi men theo dải" → bắt ngược dễ lỗ.
- ❌ Không SL thì rủi ro đuôi lớn (giống mọi mean-reversion).

## Khi nào dùng

- Thị trường tích lũy/đi ngang. Cân nhắc lọc bằng độ rộng dải (squeeze) hoặc thêm SL.

## Lưu ý khi backtest

- Thử `mult` 1.5–2.5 và `period`. Backtest cả giai đoạn trend để thấy điểm yếu.
