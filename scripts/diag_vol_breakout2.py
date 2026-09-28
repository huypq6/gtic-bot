"""Diagnostic 2: are the patterns (short>long, 16-19h negative, Monday negative) STABLE
across two 180d halves?

Run:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/diag_vol_breakout2.py
A pattern that shows up in only one half = noise/regime → do NOT put it into v2.
"""

import asyncio
from collections import defaultdict
from datetime import UTC, datetime

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines

PARAMS = {"k": 0.6, "direction": 1, "trend_len": 0, "sl_mode": 0,
          "atr_len": 14, "atr_mult": 1.5, "entry_cutoff_h": 22, "size": 0.001}
MARKETS = [("BTCUSDT", "15m"), ("ETHUSDT", "15m"), ("SOLUSDT", "15m")]
FEE = 0.0005


def _utc(ts):
    return datetime.fromtimestamp(ts / 1000, tz=UTC)


async def main() -> None:
    data = {}
    async with async_session() as s:
        for sym, tf in MARKETS:
            data[(sym, tf)] = await get_klines(s, sym, tf, limit=20000)

    all_trades = []
    for (sym, tf), candles in data.items():
        r = run_backtest("vol_breakout", "1", PARAMS, candles, 1000.0, FEE, tf, 1)
        for t in r["trades"]:
            t["sym"] = sym
        all_trades += r["trades"]

    tss = sorted(t["entry_ts"] for t in all_trades if t["entry_ts"])
    mid = tss[len(tss) // 2]
    print(f"Half split point: {_utc(mid)}\n")

    def show(label, keyf):
        b = defaultdict(lambda: [0, 0.0, 0, 0.0])  # n1, pnl1, n2, pnl2
        for t in all_trades:
            if t["pnl_pct"] is None or not t["entry_ts"]:
                continue
            k = keyf(t)
            if k is None:
                continue
            half = 0 if t["entry_ts"] < mid else 1
            b[k][half * 2] += 1
            b[k][half * 2 + 1] += t["pnl_pct"]
        print(label)
        for k, (n1, p1, n2, p2) in sorted(b.items()):
            print(f"    {k}: half1 n={n1:3d} Σ{p1:+7.2f}% | half2 n={n2:3d} Σ{p2:+7.2f}%")
        print()

    show("SIDE:", lambda t: t["side"])
    show("HOURS 16-19 vs rest:",
         lambda t: "16-19h" if 16 <= _utc(t["entry_ts"]).hour <= 19 else "other")
    show("MONDAY vs rest:", lambda t: "Mon" if _utc(t["entry_ts"]).weekday() == 0 else "other")
    show("SATURDAY vs rest:", lambda t: "Sat" if _utc(t["entry_ts"]).weekday() == 5 else "other")

    # loss tail: if losses were capped at −2.5%/trade (wide SL), how much would each half improve?
    capped = [0.0, 0.0]
    raw = [0.0, 0.0]
    for t in all_trades:
        if t["pnl_pct"] is None or not t["entry_ts"]:
            continue
        half = 0 if t["entry_ts"] < mid else 1
        raw[half] += t["pnl_pct"]
        capped[half] += max(t["pnl_pct"], -2.5)
    print(f"LOSS CAP −2.5%/trade: half1 Σ{raw[0]:+.2f}%→{capped[0]:+.2f}% | half2 "
          f"Σ{raw[1]:+.2f}%→{capped[1]:+.2f}%")


if __name__ == "__main__":
    asyncio.run(main())
