# 06 — Paper Trading Runbook (ict_po3 v4 basket)

> How to activate paper trading of the validated pair basket (ict_po3 v4) in **prod** mode and track it forward.
> Updated: 2026-06-17. Source of the basket decision: `app/strategy/strategies/ict_po3.md` (Research section).

## Recommended basket (after 365-day walk-forward)

| Pair | TF | Strategy | Target leverage | PnL/365d (backtest) | maxDD |
|---|---|---|---|---|---|
| **BTCUSDT** | 15m | ict_po3 v4 | ×2–3 | +9.2% (×2) … +13.8% (×3) | 6.5% / 9.7% |
| **DOGEUSDT** | 15m | ict_po3 v4 | ×3 | +11.8% | 5.0% |
| **SUIUSDT** | 15m | ict_po3 v4 | ×1 | +2.8% | 6.2% |

Split capital evenly → expect ~+8–9%/year, estimated portfolio DD < 7%. Leave params at **defaults** (don't tweak them).

> Only 3/14 pairs were positive over 365 days. The other 11 pairs (ETH, SOL, XRP, ADA, BNB, AVAX, DOT, LINK,
> LTC, NEAR, INJ) were all negative — do NOT add them to the basket. See `ict_po3.md` for details.

## 1. Run prod

```bash
cd ~/gtic-bot
docker compose up --build -d     # automatically runs `alembic upgrade head` + serves UI & API on :8000
```

- Open `http://localhost:8000` (or `http://<VPS-IP>:8000`).
- **PAPER mode needs no API key** — the feed uses Binance's public WebSocket, and orders are filled internally.
- The `.env` file just needs to exist (compose reads it via `env_file`). `ENABLE_LIVE` is NOT needed for paper.
- Health check: `curl -s localhost:8000/api/config` returns the watchlist + tf.

Shut down: `docker compose down` (keeps data) — the `pgdata` volume stores candle history + bots + orders.

> **DB port:** the host maps `15432:5432` (not 5432) to avoid clashing with a Postgres already running on the host.
> The app connects to the DB over the internal docker network (`db:5432`), so it is unaffected. To access the DB from the host:
> `psql -h localhost -p 15432 -U botuser tradingbot`. If you still get `port is already allocated`
> on 8000 → change `8000:8000` the same way, or `docker compose down --remove-orphans` and bring it up again.

## 2. Add pairs to the watchlist (REQUIRED before creating bots)

By default the feed only streams `BTCUSDT` + `ETHUSDT` (`settings.default_symbols`). Bots subscribe to the channel
`kline.<symbol>.15m`, so the pair must be in the feed first.

- UI: **Dashboard** page → watchlist box → add `DOGEUSDT` and `SUIUSDT`.
- (BTCUSDT is already there.)

## 3. Create 3 bots (Trading page → "Create bot (PAPER)")

All 3 bots are identical: strategy **ict_po3 v4**, TF **15m**, mode **PAPER**, **default** params.
They differ in **`size`** (quantity) — this is how leverage is expressed in paper (there's no separate leverage field).

### Size formula

```
size = (capital_allocated_to_pair × leverage) / current_price
```

Example with 1,000 virtual USDT per pair, using the price at bot creation time:

| Bot | Leverage | size (example reference price) |
|---|---|---|
| BTCUSDT | ×2–3 | `2000–3000 / BTC_price` → BTC ~100k ⇒ `0.02–0.03` |
| DOGEUSDT | ×3 | `3000 / DOGE_price` → DOGE ~0.2 ⇒ `~15000` |
| SUIUSDT | ×1 | `1000 / SUI_price` → SUI ~3 ⇒ `~330` |

> Replace the reference prices with the actual price when you create the bot. size doesn't need to be a round number.

## 4. Monitoring & correct expectations

- **Very few trades is NORMAL**: the whole basket makes ~50 trades/year (~1 trade/week). Many quiet days ≠ a bug.
- Trades only enter **after 08:00 UTC** (end of the Asia session), **no entries after 15:00 UTC**, **flatten at 21:00 UTC** —
  NO overnight holds. A trade held past 00:00 UTC ⇒ report a bug.
- **Orders** page: order list + realtime PnL. **Audit** page: every decision is logged BEFORE the fill.
- Feed lost → bots automatically **pause** + auto-reconnect (safety NFR).

### Forward confirmation criteria (4–8 weeks)

- PnL with the same sign & magnitude as the backtest: BTC ×3 ≈ +1%/month; worst monthly DD no worse than ~−7%.
- Large deviation (e.g. a −10%+ month, or several losing weeks in a row) ⇒ **stop the bots** and review before even thinking about testnet.

## 5. Next steps (do NOT jump ahead on your own)

Paper matches expectations for ≥ 4–8 weeks → consider **TESTNET** (requires a Binance testnet key) → only then LIVE
(requires `ENABLE_LIVE=1` + typing the confirmation "LIVE", a key with withdrawals disabled + VPS IP whitelist). See the Safety section of CLAUDE.md.

## Appendix — related research scripts

| Script | Purpose |
|---|---|
| `scripts/scan365_ict_po3_v4.py` | Scan 14 pairs over 365 days (basket selection) |
| `scripts/leverage_ict_po3_v4.py` | Measure DD by leverage 1–4× (level selection) |
| `scripts/walkforward_365_ict_po3_v4.py` | Walk-forward with 30-day windows |
