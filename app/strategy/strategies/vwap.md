# VWAP Cross — Giá cắt giá trung bình theo khối lượng

> Trường phái: **Trend / Momentum** (theo dòng tiền). Khung gợi ý: 5m–1h.

## Ý tưởng

VWAP (Volume Weighted Average Price) là **giá trung bình có trọng số khối lượng** — phản ánh mức giá mà phần lớn khối lượng đã giao dịch, thường được coi là "giá hợp lý" tham chiếu của tổ chức. Giá vượt lên VWAP → phe mua chiếm ưu thế; rơi xuống → phe bán.

## Công thức

```
typical price = (high + low + close) / 3
VWAP (rolling N) = Σ(typical × volume) / Σ(volume)   trên `period` nến gần nhất
```

> Bản này dùng **rolling VWAP** theo cửa sổ `period` nến (không reset theo ngày) để phù hợp engine.

## Quy tắc vào/ra lệnh

| Điều kiện | Hành động |
|---|---|
| Giá cắt **LÊN** VWAP (prev ≤ VWAP, now > VWAP) | **BUY** (LONG) |
| Giá cắt **XUỐNG** VWAP | **SELL** (SHORT) |

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `period` | 20 | Số nến tính VWAP (cửa sổ rolling). |
| `size` | 0.001 | Khối lượng. |

## Ưu / Nhược

- ✅ Gắn với **dòng tiền thực** (volume), không chỉ giá; mốc tham chiếu trực quan.
- ❌ Trong sideway hay cắt qua lại (whipsaw); rolling VWAP khác VWAP-theo-ngày kinh điển.

## Khi nào dùng

- Khung trong ngày (intraday), thị trường có volume rõ. Hợp làm bộ lọc thiên hướng (bias) trong phiên.

## Lưu ý khi backtest

- Volume trong dữ liệu phải hợp lệ (khác 0). Thử `period` theo khung.
- Cân nhắc VWAP **neo theo ngày** (anchored) nếu cần đúng chuẩn intraday.
