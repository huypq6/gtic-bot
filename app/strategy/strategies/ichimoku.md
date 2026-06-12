# Ichimoku Kinko Hyo — Hệ thống cân bằng một lần nhìn

> Trường phái: **Trend-following** (đa chỉ báo). Khung gợi ý: 1h–1d. Cần nhiều dữ liệu (≥ 78 nến).

## Ý tưởng

Ichimoku (Goichi Hosoda) gộp nhiều thành phần thành một hệ thống "nhìn một lần thấy ngay" xu hướng, hỗ trợ/kháng cự và động lượng. Tín hiệu mạnh khi **nhiều thành phần đồng thuận**.

## Thành phần

| Đường | Công thức |
|---|---|
| **Tenkan-sen** (chuyển đổi) | (HH + LL) / 2 trong `conv` nến (9) |
| **Kijun-sen** (cơ sở) | (HH + LL) / 2 trong `base` nến (26) |
| **Senkou Span A** | (Tenkan + Kijun) / 2, vẽ trước `base` nến |
| **Senkou Span B** | (HH + LL) / 2 trong `span_b` nến (52), vẽ trước `base` nến |
| **Mây (Kumo)** | vùng giữa Span A và Span B |

## Quy tắc vào/ra lệnh (bản dùng ở đây)

| Điều kiện | Hành động |
|---|---|
| Tenkan cắt **LÊN** Kijun **VÀ** giá **trên** mây | **BUY** (LONG) |
| Tenkan cắt **XUỐNG** Kijun **VÀ** giá **dưới** mây | **SELL** (SHORT) |

Lọc theo mây giúp chỉ vào lệnh thuận xu hướng chính → giảm tín hiệu giả.

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `conv` | 9 | Chu kỳ Tenkan. |
| `base` | 26 | Chu kỳ Kijun + độ dịch mây. |
| `span_b` | 52 | Chu kỳ Senkou Span B. |
| `size` | 0.001 | Khối lượng. |

## Ưu / Nhược

- ✅ Bộ lọc đa tầng (cross + mây) → tín hiệu chất lượng, ít nhiễu.
- ✅ Thấy ngay vùng hỗ trợ/kháng cự (mây).
- ❌ Trễ; cần nhiều dữ liệu; tham số nhạy với khung thời gian.

## Khi nào dùng

- Thị trường có xu hướng, khung trung–dài. Là bộ lọc xu hướng tốt để kết hợp.

## Lưu ý khi backtest

- Cần đủ lịch sử (≥ span_b + base nến) cho mỗi quyết định.
- Có thể thêm điều kiện Chikou Span (giá trễ) nếu muốn chặt hơn.
