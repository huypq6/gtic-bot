# 05 — Strategy Development Guide

> How to **write a new strategy**, **backtest** it, know **when it is ready to use**, and **plug it into the system**.
> Links: [SRS](04-SRS.md) §3 (interface), [Plan](00-Plan.md). Code: `app/strategy/`.

---

## 0. Philosophy (settled)

- **Strategy = 1 `.py` file** in `app/strategy/strategies/`. **Edited outside the app** (in the repo/IDE); the app only **loads & runs** it. The UI has **no code editor** — you can only tweak params + pick a version.
- **One interface runs across all 4 modes** (Backtest → Paper → Testnet → Live). Write once, run in every mode → backtest logic = live logic (guards against drift, RK-4).
- A strategy **only READS `Context`** and returns a list of `Signal`. It does **NOT** call the API/exchange, does **NOT** touch the DB, does **NOT** know which mode it is in, and does **NOT** `sleep`/do I/O. Order placement is handled by the `Executor` (swap the adapter = swap the mode).

---

## 1. Core interface (`app/strategy/base.py`)

```python
class Strategy(ABC):
    name: str            # identifier, e.g. "donchian"
    version: str         # "1", "2"... — bump when the logic changes
    default_params: dict # default params
    def __init__(self, params): self.params = {**self.default_params, **(params or {})}
    @abstractmethod
    def on_candle(self, ctx: Context) -> list[Signal]: ...
```

`on_candle` is called **every time a candle CLOSES** (closed candle), never on the candle still in progress.

### `Context` (injected by the engine — read-only)
| Field | Type | Meaning |
|---|---|---|
| `symbol` | str | Pair being processed (e.g. `BTCUSDT`) |
| `price` | float | Current price (close of the candle that just closed) |
| `candles` | list[dict] | Most recent OHLCV, **oldest → newest**. Each item: `{ts, open, high, low, close, volume}` (`ts` = ms). Historical candles are seeded when the bot starts → indicators have enough data right away. |
| `position` | `Position` \| None | Current position (None when flat) |
| `indicators` | dict | Slot for prebuilt indicators (currently strategies compute their own) |
| `now` | datetime \| None | Timestamp (may currently be None) |

### `Signal` (returned by the strategy)
| Field | Default | Meaning |
|---|---|---|
| `action` | — | `BUY` (want LONG) · `SELL` (want SHORT) · `CLOSE` (close position) · `CANCEL` (cancel pending order) |
| `symbol` | — | Pair |
| `size` | 0.0 | Quantity (base units) |
| `order_type` | `MARKET` | `MARKET` · `LIMIT` |
| `price` | None | Limit price (for `LIMIT`) |
| `sl` | None | Stop-loss (price) |
| `tp` | None | Take-profit (price) |

**Fill conventions** (handled by the engine, the strategy doesn't need the details): a bot holds **at most 1 position**. `BUY` while SHORT → close the short then open a long (flip). An opposite-side `SELL` while LONG → flip. `BUY` while already LONG → no-op. SL/TP are **monitored by the engine on every tick** and closed automatically when hit (Paper fills internally; Testnet/Live send a real close order).

---

## 2. Writing a new strategy — 7 steps + a complete example

1. Create a new file: `app/strategy/strategies/<name>.py`.
2. Subclass `Strategy` and add the `@register` decorator.
3. Set `name`, `version`, `default_params`.
4. (Recommended) declare `param_schema` so the UI can render a form + validate (type/min/max/default).
5. Write `on_candle(ctx)`: compute indicators from `ctx.candles`, make a decision, return `list[Signal]`.
6. **Avoid looking into the future (lookahead)**: only use CLOSED candles; when comparing against a window, exclude the current candle.
7. Make sure there is enough data: if there aren't enough candles for the indicator → `return []`.

### Example: Donchian Breakout (`app/strategy/strategies/donchian.py`)

```python
from app.strategy.base import Context, Signal, Strategy
from app.strategy.registry import register


@register
class DonchianBreakout(Strategy):
    name = "donchian"
    version = "1"
    default_params = {"period": 20, "size": 0.001}
    # For the UI: render inputs + validate (P5).
    param_schema = {
        "period": {"type": "int", "min": 5, "max": 200, "default": 20},
        "size": {"type": "float", "min": 0.0, "default": 0.001},
    }

    def on_candle(self, ctx: Context) -> list[Signal]:
        p = self.params["period"]
        if len(ctx.candles) < p + 1:           # enough data yet?
            return []
        window = ctx.candles[-(p + 1):-1]      # p candles BEFORE the current one (avoid lookahead)
        highest = max(c["high"] for c in window)
        lowest = min(c["low"] for c in window)
        if ctx.price > highest:                # breaks the high → go LONG
            return [Signal("BUY", ctx.symbol, self.params["size"])]
        if ctx.price < lowest:                 # breaks the low → go SHORT
            return [Signal("SELL", ctx.symbol, self.params["size"])]
        return []
```

You can attach SL/TP directly in the Signal:
```python
return [Signal("BUY", ctx.symbol, self.params["size"],
               sl=ctx.price * 0.98, tp=ctx.price * 1.04)]
```

**Built-in indicators** (`app/strategy/ta.py`, pure, well tested): `ema(values, period)`, `rsi(values, period)`, `atr(candles, period)`. See the samples `ema_cross.py`, `rsi_rev.py`, `donchian.py`. To add a new indicator, add it to `ta.py` (keep functions pure so they are testable).

### Methodology docs (shown in the Library)

- Set `description` (a one-line tagline) on the class → shown on the card in the **Library** page.
- Write a file **`app/strategy/strategies/<name>.md`** (next to the code file) describing it in detail: idea, formulas, entry/exit rules, params, pros/cons, when to use it, backtest notes. This file is rendered as a readable document when you click **"Methodology"** in the Library (`GET /api/strategies/{name}/doc`). See the samples `donchian.md`, `ema_cross.md`, `rsi_rev.md`.
- Optional: a Vietnamese translation can live next to it as **`<name>.vi.md`**; it is served instead of `<name>.md` when the UI language is Vietnamese.

---

## 3. Registering & loading into the app

- `@register` adds the class to the registry under the key `(name, version)`.
- `discover()` (called automatically) **scans every** module in `strategies/` so they register themselves.
- `sync_to_db()` writes the metadata (`name`, `version`, `default_params`, `source_file`) to the `strategy` table. It runs when **`GET /api/strategies`** is called or when a bot is created.
- **Reloading after editing a file:** reopen the Trading/Backtest UI (which calls `/api/strategies`) or **restart the backend**. Changed the logic → **remember to bump `version`**.

> Rule: **the `version` in the file is the source of truth.** The DB only stores metadata + params of running bot instances.

---

## 4. Backtest

**The engine uses the SAME `on_candle`** (`app/backtest/engine.py`): it replays historical candles → generates long/short signals → **vectorbt** simulates the portfolio. ⇒ backtest and paper/live results are consistent.

**Via the UI:** **Backtest** page → pick Strategy (vX), Symbol, TF, number of days, capital, fee → **Run backtest** → view metrics + equity curve + trade list. The engine automatically `sync`s historical data if it is missing.

**Via the API:**
```
POST /api/backtest
{ "strategy_id": 1, "symbol": "BTCUSDT", "tf": "1h",
  "start": "30 days ago UTC", "capital": 10000, "fee_rate": 0.001,
  "params": {"period": 20, "size": 0.001} }   # leave params empty → use defaults
```
Returns: `pnl_pct, winrate, max_dd, sharpe, n_trades, equity_curve, trades`. Stored in `backtest_run`/`backtest_trade` for comparing versions.

**Writing a strategy so it backtests correctly:**
- `on_candle` must be **deterministic** (same input → same output); no randomness/wall-clock time.
- No lookahead (see §2 step 6).
- Larger TFs (1h/4h/1d) backtest faster + are less noisy than 1m.

---

## 5. Versioning & comparison

- Changed the logic → create a **new version** (e.g. `version = "2"`) in the same file (see `ema_cross.py`, which has v1 + v2 with a gap filter). Both versions coexist → they can **run side by side** on multiple bots.
- Compare performance: **Backtest → "Compare versions"** page (groups backtest_runs by version: PnL/winrate/maxDD/number of trades), or `GET /api/strategies/{name}/compare`.

---

## 6. When is it "ready to use"? — the safe process

Follow **Flow A** (safe → real money), do NOT skip steps:

```
Write/edit strategy → BACKTEST (many pairs/periods) → passes → realtime PAPER (a few days)
   → matches expectations → TESTNET (real orders, fake environment) → LIVE (flag on + confirm)
```

**Suggested criteria to pass each gate:**
- **Backtest passes:** positive PnL across **many time periods + many pairs** (not just one lucky run); acceptable `max_dd`; `sharpe` > 0 (ideally > 1); **a large enough number of trades** (too few → easy to overfit); sensible R:R. Avoid fitting params too tightly (overfitting) — try neighbouring params to see whether it still holds up.
- **Paper passes:** run realtime for a few days; behaviour (number of trades, direction) **matches the backtest**, PnL doesn't deviate abnormally, no feed errors/stuck orders.
- **Testnet passes:** orders fill correctly on the fake exchange, SL/TP/limit work, state syncs back to the UI (requires `BINANCE_TESTNET_*` keys).
- **Live:** only after passing everything else. Requires `ENABLE_LIVE=1` + the modal where you type "LIVE". Live key: **withdrawals disabled + IP whitelist**. Start with a **small size**.

---

## 7. Plugging into the system (creating a running bot)

**Via the UI (Trading):** pick Strategy (vX) → Symbol → TF → **Mode** (PAPER/TESTNET/LIVE) → adjust **params** (form generated from `param_schema`) → **Create & run**. A bot is one instance = strategy + version + params + mode on 1 symbol.

**Via the API:**
```
POST /api/bots
{ "strategy_id": 1, "symbol": "BTCUSDT", "tf": "1h",
  "mode": "PAPER", "params": {"period": 20} }
# LIVE: add "confirm": "LIVE" and requires ENABLE_LIVE=1
```

**Operation & monitoring:**
- **Pause/Resume/Stop/Delete** bots on the Trading page. PAUSED = still manages the existing position (SL/TP exits) but **generates no new orders**.
- RUNNING bots **automatically recover after a backend restart**.
- **Orders page**: monitor open positions in realtime (mark + SL/TP + PnL, bot exits automatically) + order history (filter by mode/source/status/symbol, CSV export).
- Every action is written to the **audit_log** (see the Audit page) BEFORE it takes effect.
- From the **Scanner**: the **Trade** button (1 manual order per the suggestion + ATR-based SL/TP) or **Create bot** for that pair.

---

## 8. Rules & pitfalls

✅ Do:
- Only read `ctx`; return plain `Signal`s. Deterministic logic.
- `return []` when data is insufficient.
- Set a sensible `size` for your capital; consider attaching `sl`/`tp`.
- Bump `version` every time the logic changes.

❌ Avoid:
- Network/exchange/DB calls, `sleep`, reading wall-clock time, randomness inside `on_candle`.
- **Lookahead** (using prices from unclosed / future candles).
- Depending on state outside `ctx` (mutable global variables).
- Overfitting params to a single stretch of data.

---

## 9. Appendix — Checklist before letting a bot trade for real

- [ ] File lives in `strategies/`, has `@register`, `name`/`version`/`default_params`/`param_schema`.
- [ ] `on_candle` is deterministic, no lookahead, `return []` when data is missing.
- [ ] Backtest passes on **many pairs + many periods**; params not overfit.
- [ ] Realtime paper for a few days matches expectations.
- [ ] (If going to the exchange) Testnet OK; only then LIVE with the flag + confirm + small size + safe key.
- [ ] Monitor on the **Orders** + **Audit** pages.
