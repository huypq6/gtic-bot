# 07 — Exchange account smoke test (P9b · Binance USDⓈ-M Futures)

P9b has been coded + tested with mocks (no exchange calls). This file is the checklist to run **once you have real keys**.
Do TESTNET first; LIVE only after TESTNET passes completely.

## 0. Prepare keys
- TESTNET: log in at https://testnet.binancefuture.com → API Key → `.env`:
  `BINANCE_TESTNET_KEY=... BINANCE_TESTNET_SECRET=...` (the testnet wallet comes with virtual USDT).
- LIVE (last): a Binance key with **only Futures + Reading enabled**, withdrawals DISABLED, VPS IP whitelisted →
  `BINANCE_KEY/SECRET` + `ENABLE_LIVE=1`.
- Set the Futures account to **One-way mode** (not Hedge) — the app assumes 1 position per pair.
- Restart the app (`docker compose up --build -d`) so it reads `.env`.

## 1. Account & sync
- [ ] Accounts → New account → Type TESTNET → Create. Expected: balance = testnet Futures USDT wallet,
      the ledger has an "Initial exchange balance" entry, no `sync_error`.
- [ ] Click "Sync now" → `last_sync_at` updates. Available/margin match the Binance page.
- [ ] Transfer more USDT into the Futures wallet (testnet: Faucet/Transfer button) → within ≤15s the ledger has a "Deposit" entry.
- [ ] Enter a wrong key → `sync_error` shows in red ("Invalid API-key"), the app doesn't crash.

## 2. Orders via bot / position sizing
- [ ] Create a TESTNET bot (BTCUSDT 15m, testnet account, 0.5% risk/trade, 3–5× leverage).
      No signals yet? Temporarily use a high-frequency strategy to test, then delete the bot.
- [ ] When the bot enters a trade — check on Binance testnet:
  - [ ] pair leverage = account leverage;
  - [ ] quantity rounded to stepSize, ≈ risk% × equity / SL distance;
  - [ ] there are 2 conditional orders **STOP_MARKET + TAKE_PROFIT_MARKET (Close position)** — under
        "Conditional/Algo orders". Missing → the app raises a warning "could not place SL/TP on the exchange" and
        exits client-side instead (see the log).
- [ ] Edit SL/TP on the Orders page → the old conditional orders are cancelled, the new ones have the correct prices.

## 3. Closing trades
- [ ] Let SL/TP fill **on the exchange** → within ≤5s the position in the app is CLOSED, reason SL/TP, price = actual fill,
      PnL = realizedPnl − exchange fees; the other leg is cancelled (no orphaned conditional orders left).
- [ ] Close manually in the app → a **reduceOnly** MARKET order; never opens an opposite position.
- [ ] Close manually in the Binance app → the app records CLOSED with reason EXTERNAL.
- [ ] Reversal signal → 2 orders: a reduceOnly close, then open the new direction.
- [ ] Ledger: REALIZED_PNL + FEE (COMMISSION) + FUNDING (if a funding time was crossed) match
      Binance's Transaction History; ledger balance = Futures wallet.

## 4. Restart & guardrails
- [ ] With an open position → restart the container → the bot reloads the position + SL/TP ids (no duplicate orders).
- [ ] Position stopped out while the app was down → after it comes back, it is recorded CLOSED at the actual fill.
- [ ] Set "Max loss/day" very small → after 1 losing trade, new signals are blocked (audit RISK_REJECT).

## 5. LIVE (only when 1–4 have all passed on TESTNET)
- [ ] Without `ENABLE_LIVE=1` → creating a LIVE account returns 403.
- [ ] With it → you must type "LIVE". Small capital, risk ≤0.5%/trade, 1 bot, monitor manually for 1–2 weeks.

## Known limitations
- Position reconciliation uses 5s polling (no user-data stream yet) → up to ~5s delay.
- Fees paid in BNB don't go into the USDT ledger (turn off "use BNB to pay fees" so the ledger matches the wallet).
- 1 key pair per mode → 1 TESTNET account + 1 LIVE account.
- Manual orders on the Trading page are still PAPER only.
