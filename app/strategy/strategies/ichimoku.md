# Ichimoku Kinko Hyo — Hệ thống cân bằng một lần nhìn

> Trường phái: **Trend-following** (đa chỉ báo). Khung gợi ý: 1h–1d. Cần nhiều dữ liệu (≥ 78 nến).

## Phiên bản
- **v1** (`ichimoku.py`) — thô: vào theo cross + mây, thoát khi đảo tín hiệu. KHÔNG cắt lỗ → giữ lệnh dài.
- **v2** (`ichimoku_v2.py`) — v1 + **ATR trailing stop** (`atr_mult`) để ghìm max DD, vẫn để lời chạy theo trend.

### Nghiên cứu (skill strategy-research)
- **Sweep v1** (`scripts/sweep_ichimoku.py`): bộ tốt `conv=9 base=52 span_b=52` → PnL TB +15% (3/4 thị trường),
  win ~36% NHƯNG **maxDD 33–70%** → quá cao cho mục tiêu DD thấp.
- **v2 trailing**: cắt DD rõ nhưng dao 2 lưỡi (cũng cắt lệnh thắng lớn). `atr_mult` nhỏ = DD thấp
  nhưng cắt PnL trend; cần sweep + walk-forward để chốt.
- **Khung TF (quyết định)**: ichimoku v2 trail×2, bộ conv9/base52/spanB52, cửa sổ chính xác:
  - **15m: ÂM NẶNG** (BTC −15.6%, ETH −23.3%; 56–66 lệnh whipsaw) → KHÔNG dùng 15m.
  - **1h: BTC +26.8%, win 45%, maxDD 7.1%** (chạm cả 3 mục tiêu in-sample); ETH −1.9%.
  - 4h: BTC +31% (DD 15.6%), ETH +9.3% (DD 35.7%) — lời nhưng DD cao.
  - ⇒ Trend-following cần trend dài: chạy **1h/4h**, ngược hẳn ict_po3 (intraday 15m).

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
