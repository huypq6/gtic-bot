---
name: strategy-research
description: Use when researching/validating a trading strategy in gtic-bot before trusting it (backtest → param sweep → pair scan → walk-forward → honest verdict). Goal = ổn định theo thời gian, PnL dương đều (mỗi tuần/kỳ), max DD thấp. Triggers - "nghiên cứu/kiểm chứng chiến lược X", "tối ưu strategy", "thử <strategy>", "walk-forward", "có nên chạy thật", "tìm rổ cặp".
---

# Strategy Research (gtic-bot)

Quy trình kiểm chứng MỘT chiến lược trước khi tin / chạy tiền thật. Đúc kết từ vụ ict_po3.

## Mục tiêu đánh giá (PASS/FAIL rõ ràng)
- **Ổn định theo thời gian**: dương ở **≥ ~2/3 cửa sổ walk-forward** (không chỉ regime gần đây).
- **PnL dương đều** (lý tưởng dương mỗi tuần/kỳ), không dồn vào 1 giai đoạn.
- **Max DD thấp** (ưu tiên < ~10%).
- **Trung thực tuyệt đối**: không đạt → KHÔNG khuyến nghị tiền thật; nói thẳng, không tô hồng.

## Nguyên tắc
- Mỗi thay đổi strategy → cập nhật `app/strategy/strategies/<name>.md` (tài liệu Library) CÙNG commit.
- Sweep/scan/walk-forward dùng `app.backtest.engine.run_backtest` **in-process** (không ghi DB):
  `run_backtest(name, version, params, candles, 1000.0, FEE, tf, 1)`; nạp nến qua
  `app.market.store.get_klines/sync_historical`; `discover()` + `get(name,ver).default_params` lấy mặc định.
- Phí mặc định `FEE=0.0005` (futures taker). Thời gian từ `ts` nến (UTC). Chạy script:
  `PYTHONPATH=. uv run python scripts/<script>.py`.
- **Cảnh báo overfit**: sweep là IN-SAMPLE. Bộ "đẹp" trên 1 cửa sổ gần đây thường là regime-luck →
  PHẢI xác nhận bằng walk-forward (bước 4) mới kết luận.

## Quy trình (theo thứ tự)

### 1. Verify
- Đọc `app/strategy/strategies/<name>.py` + `.md`. `uv run pytest -q` phải xanh.
- Nếu sửa logic: viết test (TDD) bằng nến tổng hợp dựng đúng kịch bản (xem `tests/test_ict_po3.py`).
- Kiểm phân bố EXIT (flatten vs TP vs SL): nếu đa số flatten/hết-giờ → SL/TP đặt sai (xa), sửa trước.

### 2. Param sweep — tìm bộ bền
- Sao chép `scripts/sweep_ict_po3.py` → `scripts/sweep_<name>.py`; sửa `build_grid()` cho params của strategy,
  đổi `run_backtest("<name>","<ver>",...)`.
- Xếp theo **độ bền** (số thị trường dương) rồi PnL TB; lọc `MIN_TOTAL_TRADES` bỏ mẫu nhỏ.

### 3. Pair scan — tìm rổ cặp & khung hợp
- Sao chép `scripts/scan_pairs_ict_po3.py` → `scripts/scan_pairs_<name>.py`; dùng bộ params tốt nhất.
- Quét ~12–14 cặp thanh khoản × {15m, 1h}. Xác định KHUNG + cặp mà strategy ăn (thường khung quyết định).

### 4. Walk-forward — BẮT BUỘC (phán quyết)
- Sao chép `scripts/walkforward_ict_po3.py` → `scripts/walkforward_<name>.py`; rổ cặp tốt, params CỐ ĐỊNH.
- Chia lịch sử thành N cửa sổ tuần tự (~30 ngày). Dương kỳ-gần-đây nhưng âm kỳ-xa = regime-luck = TRƯỢT.
- **Tối thiểu 365 ngày, cho CẢ ứng viên lẫn chuẩn so sánh** (bài học vol_breakout 06/2026: đẹp toàn diện
  trên 180d — OOS giữ, robust lân cận, danh mục DD <10% — vẫn nổ −27%/tháng ở regime Nov–Dec 2025
  ngoài cửa sổ phát triển; trong khi ict_po3 v4 sống cả năm).

### 5. Verdict → ghi vào `<name>.md`
- Đối chiếu 3 mục tiêu. ĐẠT → đề xuất paper → testnet (vẫn theo dõi forward). KHÔNG ĐẠT → dừng ở
  nghiên cứu/paper. Nếu sweep/scan chỉ đưa về ~hòa: **cần ALPHA mới, không tinh chỉnh tham số thêm** (có trần).

## Bài học ict_po3 (đừng lặp lại)
- Tinh chỉnh (bias, retest, ATR-SL, lọc tin, chọn cặp) chỉ đưa ict_po3 về ~hòa; walk-forward 3/6 cửa sổ
  dương → KHÔNG có edge bền. Hạ tầng tốt nhưng thiếu alpha.
- Đẹp trên 60 ngày gần đây ≠ có edge: walk-forward lật ra phụ thuộc regime.
