# 10 — LIVE readiness review (2026-10-11)

Scope: everything between a strategy signal and a real Binance USDⓈ-M Futures order — runner,
ExchangeExecutor, Binance client, account sync, risk guards, restart, LIVE gates, operations.
Method: code review + unit tests (262) + a **real-exchange end-to-end run on Binance Demo Trading**
(`scripts/testnet_e2e.py`, 21/21 passed) + the 3 TESTNET bots running on d9020.

**Verdict: the order path is ready for a small, supervised LIVE trial — but NOT before the
open blockers in §2 (1 and 2) are closed.**

## 1. Verified on the real (demo) exchange

| Area | Result |
|---|---|
| Open MARKET with SL + TP placed **on the exchange** (Algo conditional, closePosition) | ✅ |
| App entry price == exchange fill (demo returns avgPrice 0 → read back, fixed `3eecbe9`) | ✅ |
| Fill rows carry exchange order id (`ext_id`), OPEN/CLOSE intent and trade link | ✅ |
| Edit SL/TP → old exchange orders cancelled, new ones placed | ✅ |
| Restart with an open position → restored, SL/TP ids reloaded, no duplicate orders | ✅ |
| Position closed by hand in the Binance app → app records CLOSED (EXTERNAL) at the real fill, leftover SL/TP cancelled | ✅ |
| Reversal → reduceOnly close then open; only the new SL/TP remain; signal close → flat | ✅ |
| Untracked position on the exchange → bot refuses to trade into it + startup alert | ✅ (new) |
| Ledger (fees, realized PnL) imported from income history; ledger sum == exchange wallet | ✅ |
| SL/TP filled by the exchange itself | ⏳ demo market too flat during the test (±0.007%); the same reconcile path passed via the manual-close case. Will be confirmed by the TESTNET bots' first SL/TP |
| Connection check: key, clock, permission, balance, one-way mode, symbols | ✅ |
| LIVE gates: `ENABLE_LIVE=1` + typing "LIVE" (account and bot), deploy script asks again | ✅ |

## 2. BLOCKERS — fix before the first LIVE order

1. **No access control.** The UI/API has no login (CORS `*`), and the Docker API on
   `d9020:2375` is open without TLS. Anyone who can reach the host can create a LIVE bot,
   close positions, or `docker inspect` the container and read `BINANCE_KEY/SECRET`.
   → Put the app behind a VPN/Tailscale (or add a login), close 2375 or switch it to TLS/SSH.
   Live key: Futures + Reading only, **withdrawals off, IP whitelist** (limits theft, not misuse).
2. **Strategy edge is unproven after fees.** The account simulation (P9c) put ict_po3 v4 at
   ≈ break-even over 365 days (fees ≈ 0.25 R per trade because the SL is ~0.4% away).
   → Go live only with TESTNET evidence: **≥ 30 closed trades, average R > 0 after fees**, and
   TESTNET-vs-PAPER divergence on the Compare page small (entry slip a few bps, R diff ≈ 0).
3. ~~**No alerts outside the browser.**~~ ✅ Done (2026-10-11): Telegram notifications, set up in
   **Settings** (token/chat/events/modes stored in the DB): trade open/close (PnL, R), order
   errors, SL/TP protection problems + untracked positions, account halt/resume, feed down/back,
   LIVE bot/account created. → Turn it on and send a test before going live.

## 3. Should fix (high)

- **Spot prices drive futures trading.** The market feed and candle history come from the
  spot stream (`stream.binance.com`) while orders and exchange SL/TP run on futures (mark
  price). Usually a few bps apart, more in fast markets. → Move feed + history to the futures
  stream so backtest, paper and live share one market (changes stored history → decide first).
- **Margin type is Binance's default (cross).** Set **isolated** per symbol when setting
  leverage, so a gap through the SL can only cost that position's margin.
- **Backups only happen on deploy.** Schedule a daily DB backup once real money is involved.
- **Feed DOWN → all bots PAUSED, no auto-resume** (by design). Open positions stay protected on
  the exchange, but someone must resume the bots — another reason for blocker 3.

## 4. Fixed during this review (`1a0a8c8`)

- Runner: one exception (exchange rejection, network, min-notional) used to end the bot's loop
  **silently** — no signals, no reconciliation, UI still "RUNNING". Now handled per message and
  per signal, audited as `ORDER_ERROR`, alerted, bot keeps running.
- Signal close: reduceOnly close is sent **before** cancelling the exchange SL/TP (a failed close
  no longer leaves the position naked); "already closed by SL/TP" is reconciled, not an error.
- LIMIT entries refused on exchange modes (resting-order fills aren't tracked → would open an
  unknown, unprotected position).
- Never trade into an exchange position the bot doesn't own; one exchange bot per symbol (API).

## 5. Go-live procedure (after §2)

1. TESTNET criteria met (§2.2) for ≥ 2 weeks; `scripts/testnet_e2e.py` passes again.
2. Live key: Futures + Reading, withdrawals OFF, IP whitelist = d9020's public IP.
3. `.env`: `BINANCE_KEY/SECRET`, `ENABLE_LIVE=1` → `scripts/deploy.sh` (asks you to type LIVE).
4. Binance: one-way mode, single-asset mode, transfer only the trial capital to USDⓈ-M.
5. Account → New account → LIVE → Check connection all green → type LIVE.
   Guards: risk 0.5%/trade, daily loss 2%, max drawdown 10%, leverage 3.
6. **One** bot, cloned from its TESTNET twin (Trading → Copy a bot). Keep the PAPER/TESTNET
   twins running → Compare shows LIVE drift.
7. Watch daily for 1–2 weeks; reconcile the app's Orders/ledger with Binance Order/Transaction
   History. Any mismatch → Stop the bot (positions stay protected by exchange SL/TP).

Re-run before every LIVE change:
`PYTHONPATH=. uv run python scripts/testnet_e2e.py XRPUSDT` (symbol no bot trades).
