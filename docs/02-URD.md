# URD — User Requirements Document
### Trading Bot Automation cho sàn Binance

| Mục | Nội dung |
|---|---|
| Phiên bản | 1.0 |
| Đối tượng | Single user (trader kiêm developer) |
| Liên kết | BRD v1.0 |

---

## 1. Persona

**Trader-Developer (chủ hệ thống)**
- Tự viết/sửa chiến thuật bằng Python.
- Muốn theo dõi nhiều cặp realtime trên cả desktop lẫn mobile.
- Cần kiểm chứng kỹ trước khi dùng tiền thật.
- Ưu tiên kiểm soát: muốn can thiệp tay bất cứ lúc nào.

---

## 2. User Stories (theo nhóm chức năng)

### 2.1 Biểu đồ & Theo dõi thị trường
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-01 | Là user, tôi muốn xem biểu đồ nến realtime giống sàn để phân tích | Nến/volume cập nhật realtime, đổi khung TG (1m–1D), zoom/pan |
| US-02 | Tôi muốn bật indicator (EMA, RSI, MACD…) lên chart | Overlay/subpane indicator, bật/tắt được |
| US-03 | Tôi muốn xem nhiều cặp trong watchlist | Danh sách cặp + giá + %thay đổi realtime |
| US-04 | Tôi muốn thấy điểm bot vào/ra lệnh trên chart | Marker mua/bán + SL/TP hiển thị trên nến |

### 2.2 Chiến thuật (Strategy)
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-05 | Tôi muốn viết/sửa thuật toán chiến thuật bằng Python | Thêm file strategy, hot-reload hoặc reload được |
| US-06 | Tôi muốn chỉnh params chiến thuật từ UI không cần sửa code | Form params (fast/slow/threshold…), lưu DB |
| US-07 | Tôi muốn quản lý nhiều phiên bản của một chiến thuật | Mỗi version có name+version+params, chạy song song |
| US-08 | Tôi muốn so sánh hiệu năng các version | Bảng so sánh PnL/winrate/drawdown theo version |

### 2.3 Backtest
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-09 | Tôi muốn backtest chiến thuật trên dữ liệu lịch sử | Chọn cặp + khung TG + khoảng ngày → chạy |
| US-10 | Tôi muốn xem kết quả backtest trực quan | Equity curve, trade list, metrics (PnL, winrate, MDD, Sharpe) |
| US-11 | Tôi muốn thấy lệnh backtest vẽ lên chart | Marker entry/exit trên chart lịch sử |

### 2.4 Giao dịch (Paper / Testnet / Live)
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-12 | Tôi muốn chạy bot ở chế độ giả lập (paper) với dữ liệu thật | Lệnh khớp nội bộ, PnL realtime, không gọi sàn |
| US-13 | Tôi muốn chạy bot trên Testnet sàn | Lệnh thật trên testnet.binance |
| US-14 | Tôi muốn bật Live có rào chắn an toàn | Cờ riêng + xác nhận + cảnh báo màu |
| US-15 | Tôi muốn chọn mode rõ ràng cho từng bot | Badge mode hiển thị nổi bật (PAPER/TESTNET/LIVE) |

### 2.5 Quản lý lệnh & Can thiệp thủ công
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-16 | Tôi muốn xem mọi vị thế đang mở + PnL | Bảng positions realtime |
| US-17 | Tôi muốn đóng lệnh thủ công | Nút Close → executor đóng ngay |
| US-18 | Tôi muốn sửa SL/TP thủ công | Edit SL/TP áp dụng ngay |
| US-19 | Tôi muốn pause/resume bot | Toggle, bot ngừng sinh lệnh mới |
| US-20 | Tôi muốn đặt lệnh tay xen kẽ bot | Form đặt lệnh market/limit thủ công |
| US-21 | Tôi muốn xem lịch sử & audit log mọi lệnh | Bảng log: thời gian, nguồn (bot/tay), hành động |

### 2.6 Nghiên cứu & Đề xuất
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-22 | Tôi muốn hệ thống quét cặp và đề xuất vào lệnh | Scanner chạy định kỳ, list cặp + score + tín hiệu |
| US-23 | Tôi muốn từ đề xuất mở nhanh chart/đặt lệnh | Click đề xuất → mở chart/prefill lệnh |

### 2.7 Phi chức năng (từ góc user)
| ID | User Story | Acceptance Criteria |
|---|---|---|
| US-24 | Tôi muốn truy cập từ điện thoại lẫn máy tính | Responsive web |
| US-25 | Tôi muốn dữ liệu sát realtime sàn | Cập nhật < 1s, WS không poll |
| US-26 | Tôi muốn không bị treo lệnh limit lâu | Auto-cancel theo timeout |
| US-27 | Tôi muốn được cảnh báo khi mất kết nối sàn | Banner cảnh báo + bot auto-pause |

---

## 3. Ma trận quyền theo Mode (an toàn)

| Hành động | Backtest | Paper | Testnet | Live |
|---|---|---|---|---|
| Chạy không xác nhận thêm | ✅ | ✅ | ✅ | ❌ (cần cờ + confirm) |
| Tiền thật | ❌ | ❌ | ❌ | ✅ |
| Can thiệp thủ công | ✅ | ✅ | ✅ | ✅ |
| Cảnh báo màu UI | — | xanh | vàng | đỏ |

---

## 4. Luồng người dùng chính (User Flows)

**Flow A — Thử chiến thuật mới (an toàn → thật):**
```
Viết/sửa strategy → Backtest → xem metrics → chỉnh params
   → Paper trade (realtime) → đạt kỳ vọng → Testnet → Live (bật cờ)
```

**Flow B — Giám sát & can thiệp:**
```
Dashboard → thấy vị thế + PnL → bất thường → Close/Sửa SL-TP
   hoặc Pause bot → ghi audit log
```

**Flow C — Từ đề xuất tới lệnh:**
```
Scanner đề xuất cặp → mở chart kiểm tra → đặt lệnh tay
   hoặc gán cho bot chạy
```
