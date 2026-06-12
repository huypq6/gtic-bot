# 05 — Hướng dẫn phát triển Strategy

> Cách **viết chiến thuật mới**, **backtest**, biết **khi nào dùng được**, và **nhúng vào hệ thống**.
> Liên kết: [SRS](04-SRS.md) §3 (interface), [Plan](00-Plan.md). Code: `app/strategy/`.

---

## 0. Triết lý (đã chốt)

- **Strategy = 1 file `.py`** trong `app/strategy/strategies/`. **Sửa ngoài app** (trong repo/IDE), app chỉ **load & chạy**. UI **không có code editor** — chỉ chỉnh params + chọn version.
- **Một interface chạy chung 4 mode** (Backtest → Paper → Testnet → Live). Viết 1 lần, chạy mọi mode → logic backtest = logic live (chống lệch RK-4).
- Strategy **chỉ ĐỌC `Context`**, trả về list `Signal`. **KHÔNG** gọi API/sàn, **KHÔNG** đụng DB, **KHÔNG** biết đang ở mode nào, **KHÔNG** `sleep`/I/O. Việc đặt lệnh do `Executor` lo (đổi adapter = đổi mode).

---

## 1. Interface cốt lõi (`app/strategy/base.py`)

```python
class Strategy(ABC):
    name: str            # định danh, vd "donchian"
    version: str         # "1", "2"... — tăng khi đổi logic
    default_params: dict # params mặc định
    def __init__(self, params): self.params = {**self.default_params, **(params or {})}
    @abstractmethod
    def on_candle(self, ctx: Context) -> list[Signal]: ...
```

`on_candle` được gọi **mỗi khi 1 nến ĐÓNG** (closed candle), không gọi trên nến đang chạy.

### `Context` (engine bơm vào — chỉ đọc)
| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `symbol` | str | Cặp đang xử lý (vd `BTCUSDT`) |
| `price` | float | Giá hiện tại (close nến vừa đóng) |
| `candles` | list[dict] | OHLCV gần nhất, **cũ → mới**. Mỗi phần tử: `{ts, open, high, low, close, volume}` (`ts` = ms). Đã seed nến lịch sử khi bot start → indicator có đủ dữ liệu ngay. |
| `position` | `Position` \| None | Vị thế hiện tại (None nếu đang flat) |
| `indicators` | dict | Chỗ trống cho indicator dựng sẵn (hiện strategy tự tính) |
| `now` | datetime \| None | Thời điểm (hiện có thể None) |

### `Signal` (strategy trả về)
| Field | Mặc định | Ý nghĩa |
|---|---|---|
| `action` | — | `BUY` (muốn LONG) · `SELL` (muốn SHORT) · `CLOSE` (đóng vị thế) · `CANCEL` (hủy lệnh chờ) |
| `symbol` | — | Cặp |
| `size` | 0.0 | Khối lượng (base units) |
| `order_type` | `MARKET` | `MARKET` · `LIMIT` |
| `price` | None | Giá limit (khi `LIMIT`) |
| `sl` | None | Stop-loss (giá) |
| `tp` | None | Take-profit (giá) |

**Quy ước khớp lệnh** (engine lo, strategy không cần biết chi tiết): 1 bot giữ **tối đa 1 vị thế**. `BUY` khi đang SHORT → đóng short rồi mở long (flip). `SELL` cùng chiều khi đang LONG → flip. `BUY` khi đã LONG → no-op. SL/TP được engine **giám sát mỗi tick** và tự đóng khi chạm (Paper khớp nội bộ; Testnet/Live gửi lệnh đóng thật).

---

## 2. Viết strategy mới — 7 bước + ví dụ đầy đủ

1. Tạo file mới: `app/strategy/strategies/<ten>.py`.
2. Kế thừa `Strategy`, gắn decorator `@register`.
3. Đặt `name`, `version`, `default_params`.
4. (Khuyến nghị) khai báo `param_schema` để UI render form + validate (kiểu/min/max/default).
5. Viết `on_candle(ctx)`: tính chỉ báo từ `ctx.candles`, ra quyết định, trả `list[Signal]`.
6. **Tránh nhìn tương lai (lookahead)**: chỉ dùng nến ĐÃ đóng; nếu so sánh cửa sổ, loại nến hiện tại ra.
7. Bảo đảm đủ dữ liệu: nếu thiếu nến cho chỉ báo → `return []`.

### Ví dụ: Donchian Breakout (`app/strategy/strategies/donchian.py`)

```python
from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register


@register
class DonchianBreakout(Strategy):
    name = "donchian"
    version = "1"
    default_params = {"period": 20, "size": 0.001}
    # Cho UI: render input + validate (P5).
    param_schema = {
        "period": {"type": "int", "min": 5, "max": 200, "default": 20},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params["period"]
        if len(ctx.candles) < p + 1:           # đủ dữ liệu chưa?
            return []
        window = ctx.candles[-(p + 1):-1]      # p nến TRƯỚC nến hiện tại (tránh lookahead)
        highest = max(c["high"] for c in window)
        lowest = min(c["low"] for c in window)
        if ctx.price > highest:                # phá đỉnh → vào LONG
            return [Signal("BUY", ctx.symbol, self.params["size"])]
        if ctx.price < lowest:                 # thủng đáy → vào SHORT
            return [Signal("SELL", ctx.symbol, self.params["size"])]
        return []
```

Có thể kèm SL/TP ngay trong Signal:
```python
return [Signal("BUY", ctx.symbol, self.params["size"],
               sl=ctx.price * 0.98, tp=ctx.price * 1.04)]
```

**Indicator có sẵn** (`app/strategy/ta.py`, thuần, test kỹ): `ema(values, period)`, `rsi(values, period)`, `atr(candles, period)`. Tham khảo mẫu `ema_cross.py`, `rsi_rev.py`. Thêm chỉ báo mới thì bổ sung vào `ta.py` (giữ hàm thuần để test).

---

## 3. Đăng ký & nạp vào app

- `@register` đưa class vào registry theo khóa `(name, version)`.
- `discover()` (gọi tự động) **quét toàn bộ** module trong `strategies/` để chúng tự đăng ký.
- `sync_to_db()` ghi metadata (`name`, `version`, `default_params`, `source_file`) vào bảng `strategy`. Chạy khi gọi **`GET /api/strategies`** hoặc khi tạo bot.
- **Nạp lại sau khi sửa file:** mở lại UI Trading/Backtest (gọi `/api/strategies`) hoặc **restart backend**. Đổi logic → **nhớ tăng `version`**.

> Quy tắc: **`version` trong file là nguồn sự thật.** DB chỉ lưu metadata + params của instance bot đang chạy.

---

## 4. Backtest

**Engine dùng CHUNG `on_candle`** (`app/backtest/engine.py`): replay nến lịch sử → sinh tín hiệu long/short → **vectorbt** mô phỏng portfolio. ⇒ kết quả backtest và paper/live nhất quán.

**Qua UI:** trang **Backtest** → chọn Strategy (vX), Symbol, TF, số ngày, vốn, phí → **Chạy backtest** → xem metrics + equity curve + danh sách trade. Engine tự `sync` dữ liệu lịch sử nếu thiếu.

**Qua API:**
```
POST /api/backtest
{ "strategy_id": 1, "symbol": "BTCUSDT", "tf": "1h",
  "start": "30 days ago UTC", "capital": 10000, "fee_rate": 0.001,
  "params": {"period": 20, "size": 0.001} }   # params bỏ trống → dùng default
```
Trả về: `pnl_pct, winrate, max_dd, sharpe, n_trades, equity_curve, trades`. Lưu vào `backtest_run`/`backtest_trade` để so sánh version.

**Lưu ý viết strategy để backtest đúng:**
- `on_candle` phải **tất định** (cùng input → cùng output), không dùng random/thời gian thực.
- Không lookahead (xem §2 bước 6).
- TF lớn (1h/4h/1d) backtest nhanh + ít nhiễu hơn 1m.

---

## 5. Versioning & so sánh

- Đổi logic → tạo **version mới** (vd `version = "2"`) trong cùng file (xem `ema_cross.py` có v1 + v2 lọc gap). Cả 2 version cùng tồn tại → **chạy song song** trên nhiều bot.
- So sánh hiệu năng: trang **Backtest → "So sánh version"** (gộp các backtest_run theo version: PnL/winrate/maxDD/số lệnh), hoặc `GET /api/strategies/{name}/compare`.

---

## 6. Khi nào "dùng được"? — quy trình an toàn

Theo **Flow A** (an toàn → tiền thật), KHÔNG nhảy bước:

```
Viết/sửa strategy → BACKTEST (nhiều cặp/khoảng) → đạt → PAPER realtime (vài ngày)
   → khớp kỳ vọng → TESTNET (lệnh thật môi trường giả) → LIVE (bật cờ + confirm)
```

**Tiêu chí gợi ý để qua mỗi cửa:**
- **Backtest đạt:** PnL dương qua **nhiều khoảng thời gian + nhiều cặp** (không chỉ 1 lần may mắn); `max_dd` chấp nhận được; `sharpe` > 0 (lý tưởng > 1); **số lệnh đủ lớn** (quá ít → dễ overfit); R:R hợp lý. Tránh tối ưu params quá khít (overfitting) — thử params lân cận xem có còn ổn.
- **Paper đạt:** chạy realtime vài ngày, hành vi (số lệnh, hướng) **khớp backtest**, PnL không lệch bất thường, không lỗi feed/treo lệnh.
- **Testnet đạt:** lệnh khớp đúng trên sàn giả, SL/TP/limit hoạt động, đồng bộ trạng thái về UI (cần `BINANCE_TESTNET_*` key).
- **Live:** chỉ sau khi qua hết. Cần `ENABLE_LIVE=1` + modal gõ "LIVE". Key live **tắt quyền rút tiền + whitelist IP**. Bắt đầu **size nhỏ**.

---

## 7. Nhúng vào hệ thống (tạo bot chạy)

**Qua UI (Trading):** chọn Strategy (vX) → Symbol → TF → **Mode** (PAPER/TESTNET/LIVE) → chỉnh **params** (form sinh từ `param_schema`) → **Tạo & chạy**. Bot là 1 instance = strategy + version + params + mode trên 1 symbol.

**Qua API:**
```
POST /api/bots
{ "strategy_id": 1, "symbol": "BTCUSDT", "tf": "1h",
  "mode": "PAPER", "params": {"period": 20} }
# LIVE: thêm "confirm": "LIVE" và cần ENABLE_LIVE=1
```

**Vận hành & theo dõi:**
- **Pause/Resume/Stop/Delete** bot ở Trading. PAUSED = vẫn quản vị thế cũ (cắt SL/TP) nhưng **không sinh lệnh mới**.
- Bot đang RUNNING **tự khôi phục sau khi restart** backend.
- **Trang Orders**: theo dõi vị thế mở realtime (mark + SL/TP + PnL, bot tự cắt) + lịch sử lệnh (lọc mode/source/status/symbol, export CSV).
- Mọi hành động ghi **audit_log** (xem trang Audit) TRƯỚC khi tác động.
- Từ **Scanner**: nút **Đánh** (1 lệnh tay theo đề xuất + SL/TP theo ATR) hoặc **Tạo bot** cho cặp đó.

---

## 8. Quy tắc & cạm bẫy

✅ Nên:
- Chỉ đọc `ctx`; trả `Signal` thuần. Logic tất định.
- `return []` khi thiếu dữ liệu.
- Đặt `size` hợp lý theo vốn; cân nhắc kèm `sl`/`tp`.
- Tăng `version` mỗi lần đổi logic.

❌ Tránh:
- Gọi mạng/sàn/DB, `sleep`, đọc thời gian thực, random trong `on_candle`.
- **Lookahead** (dùng giá nến chưa đóng / tương lai).
- Phụ thuộc trạng thái ngoài `ctx` (biến global thay đổi).
- Overfit params vào 1 đoạn dữ liệu.

---

## 9. Phụ lục — Checklist trước khi cho bot chạy thật

- [ ] File trong `strategies/`, có `@register`, `name`/`version`/`default_params`/`param_schema`.
- [ ] `on_candle` tất định, không lookahead, `return []` khi thiếu data.
- [ ] Backtest đạt trên **nhiều cặp + nhiều khoảng**; params không overfit.
- [ ] Paper realtime vài ngày khớp kỳ vọng.
- [ ] (Nếu lên sàn) Testnet OK; rồi mới LIVE với cờ + confirm + size nhỏ + key an toàn.
- [ ] Theo dõi ở trang **Orders** + **Audit**.
