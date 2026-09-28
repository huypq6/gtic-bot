"""ict_po3 v4 (BTC+SUI 15m, 365d) with 1×/2×/3×/4× leverage — does DD stay <10%?

Run:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/leverage_ict_po3_v4.py
The engine scales per-candle returns × leverage on real equity; equity hitting 0 = liquidated.
"""

import asyncio

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

SYMBOLS = ["BTCUSDT", "SUIUSDT"]
TF = "15m"
FEE = 0.0005
WIN_MS = 30 * 24 * 3600 * 1000


def window_returns(curve: list) -> list[float]:
    t0 = curve[0][0]
    wins: dict[int, list[float]] = {}
    for ts, v in curve:
        wins.setdefault((ts - t0) // WIN_MS, [v, v])[1] = v
    return [(w[1] / w[0] - 1) * 100 for i, w in sorted(wins.items())]


async def main() -> None:
    from app.strategy.registry import discover, get

    discover()
    params = dict(get("ict_po3", "4").default_params)
    data = {}
    async with async_session() as s:
        for sym in SYMBOLS:
            await sync_historical(s, sym, TF, "365 days ago UTC")
            await s.commit()
            data[sym] = await get_klines(s, sym, TF, limit=40000)
            print(f"  data {sym}: {len(data[sym])} candles")

    for lev in (1, 2, 3, 4):
        print(f"\n{'='*92}\nLEVERAGE ×{lev}")
        for sym, candles in data.items():
            r = run_backtest("ict_po3", "4", params, candles, 1000.0, FEE, TF, lev)
            wr = window_returns(r["equity_curve"])
            worst = min(wr, default=0.0)
            liq = " ⚠️LIQUIDATED" if r["liquidated"] else ""
            print(f"  {sym}: pnl={r['pnl_pct']:+.2f}% maxDD={r['max_dd']:.2f}% "
                  f"n={r['n_trades']} worst window {worst:+.2f}%{liq}")
    print("\nGoal: pick the highest leverage that keeps maxDD < ~10% and has no disastrous month.")


if __name__ == "__main__":
    asyncio.run(main())
