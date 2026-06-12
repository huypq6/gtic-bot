# BRD — Business Requirements Document
### Trading Bot Automation cho sàn Binance

| Mục | Nội dung |
|---|---|
| Tên dự án | Binance Trading Bot Platform |
| Phiên bản tài liệu | 1.0 |
| Loại hệ thống | Web app (Python thuần, single-user) |
| Phạm vi triển khai | 1 người dùng, self-hosted (VPS / máy cá nhân) |
| Trạng thái | Draft |

---

## 1. Bối cảnh & Mục tiêu kinh doanh

### 1.1 Vấn đề
Giao dịch thủ công trên Binance tốn thời gian, dễ cảm tính, khó kỷ luật và không thể theo dõi nhiều cặp 24/7. Người dùng cần một nền tảng cá nhân để:
- Tự động hóa chiến thuật theo thuật toán có kỷ luật.
- Kiểm chứng chiến thuật **trước khi** bỏ tiền thật (backtest + giả lập).
- Theo dõi realtime sát sàn, không để lệnh treo quá lâu.
- Vẫn giữ quyền can thiệp tay khi cần.

### 1.2 Mục tiêu kinh doanh (Business Goals)
| ID | Mục tiêu | Đo lường thành công |
|---|---|---|
| BG-1 | Giảm rủi ro khi thử chiến thuật mới | 100% chiến thuật chạy backtest + paper trước khi lên live |
| BG-2 | Tự động hóa thực thi có kỷ luật | Bot vào/ra lệnh theo thuật toán không cần thao tác tay |
| BG-3 | Rút ngắn vòng lặp nghiên cứu chiến thuật | Sửa thuật toán → backtest → thấy kết quả trong phút |
| BG-4 | Bảo toàn vốn | Không thất thoát do lỗi nhầm môi trường / lệnh treo |
| BG-5 | Khả năng mở rộng nhiều phiên bản chiến thuật | Chạy song song ≥ 3 version, so sánh hiệu năng |

### 1.3 Ngoài phạm vi (Out of Scope)
- Đa người dùng, phân quyền, billing.
- HFT / scalping mili-giây (độ trễ sub-ms).
- Đa sàn (chỉ Binance; thiết kế chừa cửa cho ccxt sau).
- Quản lý tài chính/kế toán thuế tự động.
- App mobile native (chỉ web responsive).

---

## 2. Yêu cầu nghiệp vụ (Business Requirements)

### 2.1 Chức năng cốt lõi
| ID | Yêu cầu | Độ ưu tiên |
|---|---|---|
| BR-1 | Hiển thị biểu đồ nến realtime giống sàn chính thống (nến, volume, indicator) | Must |
| BR-2 | Giao dịch trên môi trường an toàn của sàn (Binance Testnet) | Must |
| BR-3 | Giao dịch giả lập (paper): dữ liệu thật, đặt lệnh & theo dõi nội bộ | Must |
| BR-4 | Backtest trên dữ liệu lịch sử | Must |
| BR-5 | Quản lý giao dịch + cho phép can thiệp thủ công (đóng/sửa SL-TP, pause) | Must |
| BR-6 | Nghiên cứu cặp & đề xuất điểm vào lệnh (scanner) | Should |
| BR-7 | Chiến thuật chỉnh sửa được thuật toán + nhiều phiên bản | Must |
| BR-8 | Audit log mọi lệnh tự động & thủ công | Must |

### 2.2 Ràng buộc nghiệp vụ
| ID | Ràng buộc |
|---|---|
| BC-1 | Live trading phải có cờ kích hoạt riêng + xác nhận, tách hẳn paper/testnet |
| BC-2 | API key Live: tắt quyền rút tiền, whitelist IP |
| BC-3 | Cùng một code chiến thuật phải chạy được trên backtest / paper / live |
| BC-4 | Không để lệnh limit treo quá ngưỡng cấu hình (auto-cancel) |

---

## 3. Chế độ vận hành (3 Trading Modes)

| Mode | Dữ liệu giá | Đặt lệnh | Tiền | Mục đích |
|---|---|---|---|---|
| **Backtest** | Lịch sử (klines) | Giả lập trong engine | Ảo | Kiểm chứng thuật toán trên quá khứ |
| **Paper** | Realtime thật | Khớp nội bộ (không gọi sàn) | Ảo | Kiểm chứng realtime, dữ liệu thật |
| **Testnet** | Realtime testnet | Thật (testnet.binance) | Ảo | Kiểm tra tích hợp đặt lệnh thật |
| **Live** | Realtime thật | Thật (production) | **Thật** | Chạy thật |

---

## 4. Lợi ích kỳ vọng (Benefits)
- **Giảm rủi ro:** lọc chiến thuật kém qua backtest + paper trước khi mất tiền.
- **Kỷ luật:** loại bỏ giao dịch cảm tính.
- **Tốc độ nghiên cứu:** sửa thuật toán và thấy kết quả nhanh.
- **An toàn vận hành:** ranh giới rõ giữa các mode, chống nhầm lệnh thật.

---

## 5. Rủi ro & Giảm thiểu

| ID | Rủi ro | Mức | Giảm thiểu |
|---|---|---|---|
| RK-1 | Nhầm chạy Live thay vì Paper → mất tiền | Cao | Cờ riêng + xác nhận + màu cảnh báo UI |
| RK-2 | Lệnh limit treo không khớp | TB | Auto-cancel theo timeout cấu hình |
| RK-3 | Mất kết nối WS với sàn | Cao | Auto-reconnect + pause bot khi mất feed |
| RK-4 | Lệch logic giữa backtest và live | Cao | Dùng chung interface Strategy/Context |
| RK-5 | Rò rỉ API key | Cao | Mã hóa lưu trữ, tắt quyền rút, whitelist IP |
| RK-6 | Slippage/fee paper khác thực tế | TB | Mô phỏng fee + slippage giả định |

---

## 6. Tiêu chí thành công (Acceptance)
1. Chart realtime cập nhật < 1s so với sàn.
2. Một chiến thuật chạy được trên cả 4 mode không sửa code.
3. Backtest trả PnL, winrate, drawdown.
4. Có thể đóng/sửa lệnh thủ công khi bot đang chạy.
5. Mọi lệnh có audit log truy vết được.
6. Không thể vào Live nếu chưa bật cờ + xác nhận.
