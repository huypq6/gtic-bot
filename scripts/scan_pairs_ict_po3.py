"""Scan many PAIRS for ict_po3 v3 (default params) → find a "suitable pair basket".

Run:  PYTHONPATH=. uv run python scripts/scan_pairs_ict_po3.py

Params fixed (the shipped v3), vary SYMBOL × TF → rank by PnL to see which pairs
the strategy works on. Prints a table per TF + a suggested basket
(positive + enough trades + decent win rate).
"""

import asyncio

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical
from app.strategy.registry import discover, get

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT",
    "DOGEUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "NEARUSDT", "INJUSDT", "SUIUSDT",
]
TFS = [("15m", "60 days ago UTC"), ("1h", "180 days ago UTC")]
FEE = 0.0005
MIN_TRADES = 6


async def main() -> None:
    discover()
    params = dict(get("ict_po3", "3").default_params)
    print("params v3:", params, "\n")

    rows: dict = {}
    async with async_session() as s:
        for tf, start in TFS:
            for sym in SYMBOLS:
                try:
                    await sync_historical(s, sym, tf, start)
                    await s.commit()
                    candles = await get_klines(s, sym, tf, limit=20000)
                except Exception:  # noqa: BLE001
                    print(f"  {sym} {tf}: sync error (skipped)")
                    continue
                if len(candles) < 200:
                    print(f"  {sym} {tf}: insufficient data ({len(candles)})")
                    continue
                try:
                    r = run_backtest("ict_po3", "3", params, candles, 1000.0, FEE, tf, 1)
                except Exception:  # noqa: BLE001
                    continue
                rows[(sym, tf)] = r
            print(f"  …xong {tf}")

    for tf, _ in TFS:
        items = [(sym, rows[(sym, tf)]) for sym in SYMBOLS if (sym, tf) in rows]
        items.sort(
            key=lambda x: x[1]["pnl_pct"] if x[1]["pnl_pct"] is not None else -999, reverse=True
        )
        print(f"\n{'='*78}\n{tf} — ranked by PnL:")
        print(f"  {'symbol':<10} {'pnl%':>8} {'win%':>6} {'maxDD%':>7} {'trades':>6}")
        for sym, r in items:
            print(f"  {sym:<10} {r['pnl_pct']:>8.2f} {r['winrate']:>6.1f} {r['max_dd']:>7.2f} "
                  f"{r['n_trades']:>5}")

    # Suggested basket: positive on BOTH TFs (enough trades) → preferred; otherwise strongly
    # positive on 15m.
    print(f"\n{'='*78}\nSUGGESTED PAIR BASKET (≥{MIN_TRADES} trades):")
    basket = []
    for sym in SYMBOLS:
        r15 = rows.get((sym, "15m"))
        r1h = rows.get((sym, "1h"))
        def ok(r):
            return r and r["n_trades"] >= MIN_TRADES and (r["pnl_pct"] or 0) > 0
        tags = []
        if ok(r15):
            tags.append(f"15m +{r15['pnl_pct']:.2f}%")
        if ok(r1h):
            tags.append(f"1h +{r1h['pnl_pct']:.2f}%")
        if len(tags) == 2:
            basket.append((sym, " · ".join(tags), 2))
        elif len(tags) == 1:
            basket.append((sym, tags[0], 1))
    basket.sort(key=lambda x: x[2], reverse=True)
    for sym, tag, n in basket:
        mark = "★" if n == 2 else " "
        print(f"  {mark} {sym:<10} {tag}")
    if not basket:
        print("  (no pair is positive with enough trades — the strategy has no edge on the tested "
              "basket)")
    print("\n⚠️  In-sample. Walk-forward the selected pairs before trusting them.")


if __name__ == "__main__":
    asyncio.run(main())
