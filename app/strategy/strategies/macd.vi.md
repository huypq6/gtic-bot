# MACD Crossover — Giao cắt MACD / Signal

> Trường phái: **Trend / Momentum**. Khung gợi ý: 1h–1d.

## Ý tưởng

MACD (Moving Average Convergence Divergence, Gerald Appel) đo **động lượng** qua chênh lệch hai EMA. Đường **MACD** cắt đường **Signal** (EMA của MACD) báo hiệu động lượng đổi chiều.

## Công thức

```
MACD line   = EMA(close, fast) − EMA(close, slow)
Signal line = EMA(MACD line, signal)
Histogram   = MACD − Signal
```

## Quy tắc vào/ra lệnh

| Điều kiện | Hành động |
|---|---|
| MACD cắt **LÊN** Signal (mp ≤ sp và mn > sn) | **BUY** (LONG) |
| MACD cắt **XUỐNG** Signal | **SELL** (SHORT) |

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `fast` | 12 | EMA nhanh. |
| `slow` | 26 | EMA chậm. |
| `signal` | 9 | EMA của MACD line. |
| `size` | 0.001 | Khối lượng. |

## Ưu / Nhược

- ✅ Bắt động lượng/xu hướng tốt; bộ tham số 12/26/9 phổ biến, đáng tin.
- ❌ Trễ (dựa trên EMA); trong sideway hay tín hiệu giả (whipsaw).

## Khi nào dùng

- Thị trường có xu hướng/động lượng. Kết hợp lọc xu hướng dài hạn để giảm tín hiệu giả.

## Lưu ý khi backtest

- Giữ bộ tham số chuẩn trước khi tinh chỉnh; tránh overfit fast/slow/signal.
- Có thể dùng **histogram** (MACD − Signal) đổi dấu thay cho crossover để vào sớm hơn.
