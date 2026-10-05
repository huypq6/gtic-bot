"""TESTNET round-trip smoke test (docs/09) — real orders on Binance Futures Demo Trading.

Uses the app's own BinanceFuturesClient (same code path as TESTNET bots):
  connection check → leverage → MARKET open (smallest allowed size) → SL/TP placed ON THE
  EXCHANGE (Algo orders) → verify they exist → cancel them → reduceOnly close → verify flat
  → closing fill + income ledger.
Never runs against LIVE (hard-coded TESTNET keys + testnet client). Cleans up on any error.

Run:  PYTHONPATH=. uv run python scripts/testnet_smoke.py [SYMBOL] [--side SELL] [--yes]
      (inside docker:  docker compose exec app python scripts/testnet_smoke.py --yes)
"""

import argparse
import asyncio
import math
import sys
import time

from app.config import settings
from app.execution.binance_futures import BinanceFuturesClient
from app.execution.preflight import overall, run_checks

OK, BAD = "\033[32m✔\033[0m", "\033[31m✘\033[0m"


def step(msg: str) -> None:
    print(f"\n▶ {msg}", flush=True)


def ceil_to(v: float, step_: float) -> float:
    n = math.ceil(v / step_ - 1e-9)
    return round(n * step_, max(0, -int(math.floor(math.log10(step_)))))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="DOGEUSDT")
    ap.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    ap.add_argument("--leverage", type=int, default=2)
    ap.add_argument("--yes", action="store_true", help="don't ask before placing orders")
    a = ap.parse_args()
    sym = a.symbol.upper()

    if not settings.binance_testnet_key or not settings.binance_testnet_secret:
        print(f"{BAD} BINANCE_TESTNET_KEY/SECRET missing in .env — see docs/09-Testnet-Setup.md")
        return 2
    c = await BinanceFuturesClient.create(
        settings.binance_testnet_key, settings.binance_testnet_secret,
        testnet=True, endpoint=settings.binance_testnet_endpoint,
    )
    assert c.testnet  # safety: this script must never talk to the live exchange
    print(f"Endpoint: {c.base_url}   symbol: {sym}   side: {a.side}")
    opened = False
    protect: dict = {}
    pos_side = "LONG" if a.side == "BUY" else "SHORT"
    close_side = "SELL" if a.side == "BUY" else "BUY"
    try:
        step("Connection check")
        checks = await run_checks(c, "TESTNET", [sym])
        for x in checks:
            mark = OK if x["status"] == "ok" else ("!" if x["status"] == "warn" else BAD)
            fix = f"\n      fix: {x['fix']}" if x["fix"] else ""
            print(f"  {mark} {x['label']}: {x['detail']}{fix}")
        if overall(checks) == "fail":
            print(f"\n{BAD} Fix the failed checks above, then run again.")
            return 1

        pos = await c.position(sym)
        if pos["amt"]:
            print(f"{BAD} {sym} already has an open position ({pos['amt']}) — "
                  "close it or pick another symbol.")
            return 1

        rules = await c.rules(sym)
        price = float((await c._raw.futures_mark_price(symbol=sym))["markPrice"])
        qty = max(rules.min_qty, ceil_to(rules.min_notional * 1.2 / price, rules.step))
        print(f"\n  mark {price}  → qty {qty} (≈ {qty * price:.2f} USDT notional, "
              f"min notional {rules.min_notional:g})")
        if not a.yes and input("Place REAL testnet orders now? [y/N] ").strip().lower() != "y":
            print("Aborted.")
            return 1
        t0 = int(time.time() * 1000)

        step(f"Set leverage {a.leverage}x")
        await c.ensure_leverage(sym, a.leverage)
        print(f"  {OK} leverage set")

        step(f"MARKET {a.side} {qty} {sym}")
        r = await c.market_order(sym, a.side, qty)
        opened = True
        print(f"  {OK} order {r['orderId']} {r['status']}  avg {r['price']}  filled {r['qty']}")
        pos = await c.position(sym)
        assert abs(pos["amt"]) > 0, "position not visible after fill"
        print(f"  {OK} exchange position {pos['amt']} @ {pos['entry']}")

        entry = pos["entry"] or r["price"]
        sl = entry * (0.97 if pos_side == "LONG" else 1.03)
        tp = entry * (1.03 if pos_side == "LONG" else 0.97)
        step(f"Place SL {sl:.6g} / TP {tp:.6g} on the exchange (Algo conditional orders)")
        protect = await c.protect(sym, pos_side, sl, tp)
        print(f"  {OK} algo ids {protect}")
        await asyncio.sleep(1)
        algo = await c.open_algo_orders(sym)
        ids = {str(o.get("algoId")) for o in algo}
        found = [k for k, v in protect.items() if v and v in ids]
        print(f"  {OK if len(found) == 2 else BAD} visible on exchange: {found} "
              f"({len(algo)} open algo order(s) on {sym})")

        step("Cancel SL/TP")
        await c.cancel_protection(sym, protect)
        protect = {}
        await asyncio.sleep(1)
        left = [o for o in await c.open_algo_orders(sym) if str(o.get("algoId")) in ids]
        print(f"  {OK if not left else BAD} remaining: {len(left)}")

        step(f"Close with reduceOnly MARKET {close_side}")
        r = await c.market_order(sym, close_side, abs(pos["amt"]), reduce_only=True)
        opened = False
        print(f"  {OK} order {r['orderId']} avg {r['price']}")
        pos = await c.position(sym)
        print(f"  {OK if not pos['amt'] else BAD} position after close: {pos['amt']}")

        step("Closing fill + ledger (what the app imports)")
        await asyncio.sleep(2)
        fill = await c.last_close_fill(sym, t0)
        print(f"  closing fill: {fill}")
        inc = [x for x in await c.income(t0) if x["symbol"] == sym]
        for x in inc:
            print(f"  income {x['type']:<14} {x['amount']:+.6f} {x['asset']}")
        acc = await c.account()
        print(f"  wallet {acc['wallet']:.2f}  available {acc['available']:.2f}")
        print(f"\n{OK} TESTNET round trip OK — the app can trade on this account.")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"\n{BAD} {type(e).__name__}: {getattr(e, 'message', e)} "
              f"(code {getattr(e, 'code', '-')})")
        return 1
    finally:
        if protect:
            await c.cancel_protection(sym, protect)
        if opened:
            try:
                pos = await c.position(sym)
                if pos["amt"]:
                    side = "SELL" if pos["amt"] > 0 else "BUY"
                    await c.market_order(sym, side, abs(pos["amt"]), reduce_only=True)
                    print("  cleanup: position closed")
            except Exception as e:  # noqa: BLE001
                print(f"  {BAD} cleanup failed — close {sym} manually on demo.binance.com: {e}")
        await c.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
