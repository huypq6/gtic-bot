# ICT Power of Three (PO3) — Session AMD

> Trường phái: **Smart Money / liquidity (ICT)**. Khung gợi ý: **15m** (5m–1h chạy được). Chỉ đánh **trong ngày** (UTC), không giữ qua đêm.

## Ý tưởng

ICT **Power of Three (PO3)** mô tả vòng đời mọi cây nến / mọi phiên theo 3 pha **AMD**:

1. **Accumulation (Tích lũy)** — giá đi ngang tạo range, gom thanh khoản.
2. **Manipulation (Thao túng)** — giá **quét** (sweep) một phía của range để lấy thanh khoản (stop) rồi đảo chiều. Đây là "judas swing".
3. **Distribution (Phân phối)** — cú đẩy thật theo hướng ngược với cú quét.

Bản này áp PO3 theo **phiên trong ngày** (Session AMD), ánh xạ sang giờ **UTC** (crypto chạy 24/7):

| Phiên | Giờ UTC | Vai trò AMD |
|---|---|---|
| **Asia** | 00:00–08:00 | **Accumulation** → xác định **Asia High / Asia Low** (range của ngày) |
| **London + New York** | 08:00–21:00 | **Manipulation** (quét range Asia) → **Distribution** (cú đẩy) |
| **Flatten** | 21:00 | Đóng hết, không giữ qua ngày. 00:00 UTC sang ngày mới → reset |

Hướng giao dịch sinh từ cú quét, NHƯNG phải **thuận bias HTF** (theo blog ICT PO3 — xác định bias 4H/daily TRƯỚC, "long bias → tìm manipulation dưới open; short bias → trên open"):
- Quét **dưới** Asia Low (sell-side liquidity) → đảo lên → **LONG** — chỉ khi **bias tăng**.
- Quét **trên** Asia High (buy-side liquidity) → đảo xuống → **SHORT** — chỉ khi **bias giảm**.

### Bias / Trend filter (mặc định BẬT)

`bias_mode=1` (mặc định): lọc bằng **EMA dài** `bias_len` trên chính khung đang chạy (xấp xỉ trend 4H/daily). Bias **tăng** nếu `close > EMA(bias_len)`, **giảm** nếu `<`. Chỉ vào lệnh KHỚP hướng bias → bỏ các lệnh ngược trend (nguyên nhân chính gây thua khi chưa lọc). `bias_mode=0` = tắt (đánh 2 chiều theo cú quét). Đường **Bias EMA** được vẽ trên chart.

## Khung kỹ thuật trong dự án

- Chạy chung `Strategy.on_candle` trên **1 TF được chọn**. Mọi mốc thời gian lấy từ `ts` của nến theo **UTC** — **không** dùng `ctx.now` (không được set ở backtest).
- **Stateful**: giữ state trong instance qua các nến (range Asia, cú quét, lệnh đang mở, đã-trade-trong-ngày). Đã xác nhận runner + backtest tái dùng cùng instance.
- Tự quản **SL/TP**: engine backtest (`vbt.Portfolio.from_signals`) **không** tự áp SL/TP — thoát lệnh bằng tín hiệu `CLOSE` (hoặc đảo chiều). Vì vậy strategy tự kiểm tra giá vs SL/TP mỗi nến và phát `CLOSE`.
- Vào lệnh **MARKET** tại `close` của nến xác nhận. Engine fill tại close → **FVG/Order Block là bộ lọc xác nhận**, không phải lệnh LIMIT chờ (giữ hành vi nhất quán cả 4 mode).

## Logic mỗi nến (`on_candle`)

1. **Thời gian**: tính `date` + `hour` (UTC) từ `candles[-1]["ts"]`.
2. **Sang ngày mới** (date đổi): reset Asia range / cú quét / cờ đã-trade; nếu còn lệnh mở → `CLOSE` (chốt an toàn không qua đêm).
3. **Dựng Asia range**: từ các nến hôm nay có `hour < asia_end_h`, lấy `asia_high = max(high)`, `asia_low = min(low)`. Chỉ giao dịch khi `hour ≥ asia_end_h` (Asia đã đóng) và range có dữ liệu.
4. **Manipulation (sweep)** — trong cửa sổ `[asia_end_h, flatten_h)`, xét cú quét **đầu tiên** của ngày:
   - `high > asia_high` → ghi nhận **sweep HIGH** (setup SHORT), `sweep_extreme = high`.
   - `low < asia_low` → ghi nhận **sweep LOW** (setup LONG), `sweep_extreme = low`.
5. **MSS (Market Structure Shift)** — sau khi có sweep, xác nhận đảo cấu trúc dựa trên **đỉnh/đáy phản ứng kể từ cú quét** (proxy của BOS, chỉ tham chiếu cấu trúc *sau* sweep nên không dính nhầm Asia High/Low):
   - Đợi tối thiểu `mss_lookback` nến phản ứng sau cú quét (chống fire bởi 1 nến râu).
   - Setup LONG: vào khi `close >` **đỉnh phản ứng** (max high các nến sau sweep, chưa tính nến hiện tại) → tạo higher-high.
   - Setup SHORT: vào khi `close <` **đáy phản ứng** (min low các nến sau sweep) → tạo lower-low.
6. **Confluence** (param `confluence`) — quyết định **CÁCH VÀO LỆNH**:
   - `1` = **MSS-breakout**: vào MARKET ngay tại nến MSS (giá xa SL → R:R kém, TP khó chạm — xem quan sát bên dưới).
   - `2` = **Retest FVG** (mặc định): khi MSS xảy ra + có **Fair Value Gap** cùng hướng → **VŨ TRANG** (chưa vào). Chờ giá **hồi về** mép gần FVG rồi mới vào (giá tốt hơn, **gần SL** → R:R đạt được).
     - Bullish FVG: `low[i] > high[i-2]` → mép gần = `low[i]` (đỉnh gap); retest khi nến chạm xuống ≤ mép.
     - Bearish FVG: `high[i] < low[i-2]` → mép gần = `high[i]`; retest khi nến chạm lên ≥ mép.
   - `3` = **Retest FVG + Order Block**: như `2` nhưng còn yêu cầu có nến **đối màu** (gốc OB) trong cú đẩy.
7. **Vào lệnh** (MARKET tại close):
   - `conf=1`: vào ngay khi MSS.
   - `conf≥2`: sau khi vũ trang, vào khi giá **retest** về FVG. Nếu giá **phá sâu hơn điểm quét** trước khi retest → **huỷ setup** (dò lại). Nếu hết `flatten_h` chưa retest → bỏ.
   - Đặt `traded_today = True` → **tối đa 1 lệnh/ngày**.

## SL / TP & thoát trong ngày

| Hướng | SL | Risk | TP |
|---|---|---|---|
| LONG | `sweep_low − buffer` | `entry − SL` | `entry + rr_target × risk` |
| SHORT | `sweep_high + buffer` | `SL − entry` | `entry − rr_target × risk` |

- `buffer = sl_buffer_pct% × entry` (mặc định 0.05%).
- Mỗi nến khi đang có lệnh, kiểm tra theo **close** (khớp cách fill của vectorbt):
  - LONG: `close ≤ SL` (cắt lỗ) hoặc `close ≥ TP` (chốt lời) → `CLOSE`.
  - SHORT đối xứng.
- **Flatten cuối ngày**: `hour ≥ flatten_h` hoặc sang ngày mới và còn lệnh → `CLOSE`.

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `bias_mode` | 1 | 0 = tắt lọc trend (2 chiều) · 1 = chỉ đánh thuận EMA trend HTF. |
| `bias_len` | 100 | Độ dài EMA bias (số nến ~ 4H/daily; tuỳ TF). |
| `confluence` | 3 | Cách vào: 1 = MSS-breakout (MARKET) · 2 = retest FVG · 3 = retest FVG+OB. |
| `mss_lookback` | 3 | Số nến để xác định break cấu trúc (proxy MSS). |
| `tp_mode` | 1 | TP: 0 = `rr_target` cố định · 1 = thanh khoản đối diện (đỉnh/đáy range Asia). |
| `rr_target` | 2.0 | Bội số R cho TP khi `tp_mode=0` (cũng là fallback của `tp_mode=1`). |
| `sl_buffer_pct` | 0.05 | Đệm SL ngoài điểm quét, theo % giá. |
| `asia_end_h` | 8 | Giờ UTC kết thúc phiên Asia (chốt range). |
| `flatten_h` | 21 | Giờ UTC đóng hết lệnh (kết thúc NY). |
| `news_filter` | 2 | Lọc tin: 0 = tắt · 1 = chặn vào lệnh trong khung giờ tin · 2 = + chặn ngày NFP (thứ Sáu đầu tháng). |
| `news_start_h` / `news_end_h` | 12 / 14 | Khung giờ tin US (UTC): 8:30 ET = 12:30 (hè) / 13:30 (đông). |
| `size` | 0.001 | Khối lượng. |

## Hiển thị (chart backtest)

- `plot()` vẽ **Asia High** và **Asia Low** theo **từng ngày** (đường bậc thang, pane 0) — thấy rõ range bị quét trước khi đảo chiều.
- Marker vào/ra mỗi lệnh dùng sẵn cơ chế trade của chart backtest.

## Ưu / Nhược

- ✅ Bám logic ICT (liquidity sweep + đảo chiều), R:R cố định 2R, kỷ luật trong ngày, không rủi ro qua đêm.
- ✅ Lọc bias HTF (chỉ đánh thuận trend) + chỉ 1 lệnh/ngày → ít overtrade, ít lệnh ngược trend.
- ❌ MSS dùng proxy **break N nến**, không phải swing-structure đầy đủ → có thể vào sớm/trễ so với ICT thủ công.
- ❌ FVG/OB là **bộ lọc xác nhận** (vào MARKET tại close), không mô phỏng lệnh LIMIT chờ tại FVG → fill thực tế (paper/live) có thể khác giá tối ưu ICT.
- ❌ Range Asia kém ý nghĩa vào ngày tin lớn/biến động bất thường (NFP/CPI…).

## Khi nào dùng

- Cặp thanh khoản tốt (BTCUSDT, ETHUSDT), khung **15m**. Ngày có phiên Asia tạo range rõ rồi London/NY quét.
- Tăng `confluence` (2→3) khi muốn ít lệnh, chất lượng cao hơn; giảm về 1 khi muốn nhiều tín hiệu để khảo sát.

## Lưu ý khi backtest

- Cần nhiều ngày dữ liệu (đặt "số ngày" ≥ 14) để có đủ mẫu phiên. Tham số chỉnh trực tiếp trên form backtest (bias_mode, confluence, bias_len, rr_target…).
- Quét `(bias_mode, bias_len, confluence, mss_lookback, rr_target)`; mặc định 1 / 200 / 2 / 3 / 2.0.
- Kiểm chứng: số lệnh ≤ số ngày (tối đa 1/ngày); không lệnh nào giữ qua 00:00 UTC.

### Quan sát thực nghiệm + quét tham số (`scripts/sweep_ict_po3.py`)

- **Entry retest FVG (`conf≥2`) tốt hơn hẳn breakout (`conf=1`)**: BTC 15m −1.9% vs −8.25%; làm
  `rr_target` bắt đầu ảnh hưởng kết quả → TP đã chạm được (breakout: mọi rr y hệt vì TP không bao giờ chạm).
- **`tp_mode=1` (TP về thanh khoản đối diện) thắng áp đảo** trong sweep (288 backtest, BTC/ETH 15m+1h):
  chiếm toàn bộ top, winrate ~37–44%, maxDD thấp (~3%).
- **Bộ bền nhất = mặc định hiện tại** (`conf=3, tp_mode=1, bias_len=100, mss=3`): PnL TB −0.76%,
  lời 2/4 thị trường, win ~40%, maxDD 3.4%. Alt nhiều lệnh hơn: `conf=2` (tương tự, ~37 lệnh).
- **Out-of-sample** (cửa sổ dài hơn + cặp chưa sweep): BTC/ETH 15m 90d ≈ −2.4…−2.7%; ETH 1h 200d **+0.88%**;
  SOL 1h 120d −3.3%. Cùng độ lớn với in-sample → **không overfit nặng**, nhưng **chưa phải edge có lời**.
- **Lọc tin (`news_filter`, mặc định 2)**: chặn vào lệnh khung 12–14 UTC + ngày NFP cải thiện
  **3/4 thị trường** và giảm drawdown rõ (ETH 1h 200d: +0.88% → **+6.34%**, win 56%→78%, DD 2.1%→1.1%);
  trung bình 4 thị trường lật từ −1.67% sang **+0.36%**. BTC 15m hơi xấu đi (mẫu nhỏ). NFP-day (=2)
  bằng window-only trên dữ liệu thử (không hại). Lưu ý: thị trường dương (ETH 1h, 9 lệnh) mẫu nhỏ → có thể may.
- **Kết luận thẳng**: với lọc tin, ở mức **hòa vốn ± nhẹ, drawdown thấp** — KHẢ QUAN hơn nhưng mẫu nhỏ,
  CHƯA nên tiền thật. Hướng tiếp: walk-forward nhiều cửa sổ, xét lại proxy MSS (swing-structure thật).

## Giới hạn đã biết (tóm tắt cho người đọc code)

1. MSS = phá đỉnh/đáy phản ứng sau sweep (đợi ≥ `mss_lookback` nến), proxy của BOS — không phải CHoCH/swing-structure đầy đủ.
2. `conf≥2`: vào tại **retest FVG** nhưng fill ở **close** của nến chạm vùng (engine không mô phỏng LIMIT/intrabar) → giá vào xấp xỉ, không chính xác mép FVG.
3. SL/TP kiểm theo `close` (không peek intrabar high/low) để khớp fill close của vectorbt.
4. Phiên cố định theo UTC; chưa xử lý DST của London/NY (crypto dùng UTC nên chấp nhận được).
