# 09 — Testnet setup (Binance USDⓈ-M Futures · Demo Trading)

Goal: run TESTNET bots (real orders, fake money) next to your PAPER bots. ~15 minutes.
After this, run the full validation checklist in [07-Exchange-Smoke-Test.md](07-Exchange-Smoke-Test.md).

> **Binance moved the futures testnet.** `testnet.binancefuture.com` now redirects to
> **Demo Trading** (`demo.binance.com`). Keys are created there and the app talks to
> `demo-fapi.binance.com` by default (`BINANCE_TESTNET_ENDPOINT=demo`). Verified 2026-10-05:
> both the demo and legacy hosts are up and serve the same market; prices track live within a few bps.

## 1. Create a Demo Trading API key
1. Open https://demo.binance.com (or https://testnet.binancefuture.com — it redirects) and log in
   with your Binance account. You are now in the demo environment (virtual balance).
2. Go to **API Management** (profile menu) → **Create API** → *System generated* (HMAC).
3. Copy the **API Key** and **Secret Key** — the secret is shown only once.
4. Make sure the demo Futures wallet has USDT (Demo Trading gives a virtual balance; use its
   reset/faucet if it is 0).

A normal (live) Binance key does **not** work on testnet, and a demo key does not work on live.

## 2. Put the keys in `.env` on the machine that runs the app
```env
BINANCE_TESTNET_KEY=<api key>
BINANCE_TESTNET_SECRET=<secret key>
BINANCE_TESTNET_ENDPOINT=demo     # "testnet" = legacy testnet.binancefuture.com
ENABLE_LIVE=0                     # leave LIVE locked
```
Never commit `.env` (it is git-ignored).

Restart so the app reads `.env`:
- Docker: `docker compose up -d --build` (env changes need a container **re-create**;
  `docker compose restart` does not re-read `.env`).
- Dev: stop and start `uv run uvicorn app.main:app` again.

## 3. Check the connection (in the app)
**Account → New account → Type = TESTNET → Check connection.**

| Check | Must be | If not |
|---|---|---|
| Endpoint | `https://demo-fapi.binance.com/fapi` | set `BINANCE_TESTNET_ENDPOINT` |
| Clock drift | within ±1000 ms | enable NTP: `timedatectl set-ntp true` |
| API key | accepted | wrong/expired key, or a live key → create a Demo Trading key (step 1) |
| Trading permission | enabled | edit the key, tick *Enable Futures* |
| USDT balance | > 0 | reset/faucet on demo.binance.com |
| Position mode | One-way | testnet: switched automatically (fails only if positions/orders are open — close them) |
| Multi-assets mode | off | Futures → Preferences → Single-asset mode |
| Symbols | all listed | bots on unlisted symbols cannot trade on testnet |

All green → enter a name (e.g. `Testnet`), leverage (3–5), **Create**. The balance comes from
the exchange and syncs every 15 s.

## 4. (Recommended) Round-trip smoke test — real testnet orders, ~0.01 USDT of (fake) fees
Proves the exact code path bots use: open → SL/TP placed on the exchange → cancel → reduce-only close.
```bash
# Docker
docker compose exec app python scripts/testnet_smoke.py            # asks before ordering
# Dev
PYTHONPATH=. uv run python scripts/testnet_smoke.py DOGEUSDT --yes
```
Expected last line: `✔ TESTNET round trip OK — the app can trade on this account.`
It uses the smallest allowed size, cleans up on any error, and can only talk to testnet.

## 5. Run a TESTNET bot
1. Header lens → **Testnet** (amber stripe = you are looking at testnet).
2. **Trading** → either create a bot with *Mode = TESTNET*, or on a PAPER bot click
   **Clone to… → TESTNET** (same strategy/params/symbol → directly comparable).
3. Account = the TESTNET account, size = `0.5% risk/trade` to start.
4. Watch it on **Overview**, **Orders** (lens Testnet) and, once trades close, **Compare**
   (TESTNET vs PAPER divergence = how far simulated fills are from exchange fills).

Rules:
- **One TESTNET bot per symbol.** Futures holds one position per symbol per account; two bots
  on the same symbol would close/flip each other. PAPER bots have no such limit.
- Manual orders on the Trading page are PAPER only.
- Positions are protected on the exchange (STOP_MARKET / TAKE_PROFIT_MARKET, "Close position"),
  so they stay protected even if the app is down.

## 6. Troubleshooting
| Symptom | Cause / fix |
|---|---|
| `-2015 Invalid API-key, IP, or permissions` | key not from Demo Trading, wrong endpoint, IP restriction on the key, or Futures not enabled |
| `-2014 API-key format invalid` | key pasted with spaces/quotes in `.env` |
| `-1021 Timestamp outside recvWindow` | server clock drift → NTP |
| `-4068` on position mode | close all positions/orders on demo, check again |
| Bot creation error "BINANCE_TESTNET_KEY/SECRET is required" | `.env` not loaded → re-create the container |
| Warning "could not place SL/TP on the exchange" | SL/TP too close to the price (`-2021 would immediately trigger`); the app then closes client-side. Widen SL or check the log |
| `order notional … < minimum` | position size below the symbol's min notional → raise risk % or pick another symbol |
| Account shows `sync_error` | read the message; run *Check connection* |

Next: complete [07-Exchange-Smoke-Test.md](07-Exchange-Smoke-Test.md) §1–4 on testnet. LIVE comes
only after that passes, and still needs `ENABLE_LIVE=1` + typing "LIVE".
