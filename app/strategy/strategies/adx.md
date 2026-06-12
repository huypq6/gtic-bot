# ADX / DMI — Chỉ số xu hướng định hướng

> Trường phái: **Trend (lọc theo độ mạnh)**. Khung gợi ý: 1h–1d.

## Ý tưởng

Hệ thống DMI (Welles Wilder) gồm hai đường định hướng **+DI / −DI** (sức mua/bán) và **ADX** đo **độ mạnh** của xu hướng (không phân biệt hướng). Ý tưởng: chỉ giao dịch theo DI khi xu hướng đủ mạnh (ADX cao) → tránh vào lệnh trong sideway.

## Công thức (rút gọn)

```
+DM / −DM : biến động hướng lên / xuống giữa các nến
+DI = 100 × Wilder(+DM) / Wilder(TR)
−DI = 100 × Wilder(−DM) / Wilder(TR)
DX  = 100 × |+DI − −DI| / (+DI + −DI)
ADX = Wilder-smooth(DX)
```

## Quy tắc vào/ra lệnh

| Điều kiện | Hành động |
|---|---|
| `ADX ≥ adx_min` **và** +DI cắt **LÊN** −DI | **BUY** (xu hướng tăng mạnh) |
| `ADX ≥ adx_min` **và** +DI cắt **XUỐNG** −DI | **SELL** (xu hướng giảm mạnh) |

ADX < `adx_min` (sideway) → **không vào lệnh**.

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `period` | 14 | Chu kỳ DMI/ADX. |
| `adx_min` | 25 | Ngưỡng độ mạnh xu hướng để cho phép vào lệnh (25 = "đủ mạnh"). |
| `size` | 0.001 | Khối lượng. |

## Ưu / Nhược

- ✅ Bộ lọc **độ mạnh xu hướng** rất hữu ích — tránh giao dịch trong sideway.
- ❌ Trễ; bản thân ADX không cho hướng (cần DI). DI cross có thể nhiễu khi ADX ngấp nghé ngưỡng.

## Khi nào dùng

- Làm **bộ lọc** kết hợp các chiến thuật khác (chỉ vào lệnh khi ADX cao), hoặc dùng độc lập theo DI cross.

## Lưu ý khi backtest

- Thử `adx_min` 20–30. Cần đủ dữ liệu (≥ 2×period) cho ADX ổn định.
