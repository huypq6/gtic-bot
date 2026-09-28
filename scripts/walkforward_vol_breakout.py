"""WEEKLY walk-forward for vol_breakout — goal: "consistently positive every week, low DD".

Run:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/walkforward_vol_breakout.py

1 long backtest per (pair × TF × config), computing PnL per ISO week from equity_curve.
FIXED params from the sweep (in-sample 90d) → run 180d = the first half is out-of-sample.
"""

import asyncio
from datetime import UTC, datetime

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

BASE = {"direction": 1, "atr_len": 14, "atr_mult": 1.5, "entry_cutoff_h": 22, "size": 0.001}
CONFIGS = {
    "k0.6 sl0 (baseline)":  {**BASE, "k": 0.6, "trend_len": 0, "sl_mode": 0},
    "noise20 sl0":       {**BASE, "k": 0.6, "k_mode": 1, "noise_len": 20, "trend_len": 0,
                          "sl_mode": 0},
    "noise40 sl0":       {**BASE, "k": 0.6, "k_mode": 1, "noise_len": 40, "trend_len": 0,
                          "sl_mode": 0},
}
MARKETS = [
    ("BTCUSDT", "15m", "180 days ago UTC"),
    ("ETHUSDT", "15m", "180 days ago UTC"),
    ("SOLUSDT", "15m", "180 days ago UTC"),
]
FEE = 0.0005


def weekly_returns(equity: list) -> list[tuple[str, float]]:
    weeks: dict = {}
    for ts, v in equity:
        d = datetime.fromtimestamp(ts / 1000, tz=UTC)
        key = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
        weeks.setdefault(key, [v, v])[1] = v
    return [(k, (w[1] / w[0] - 1) * 100) for k, w in weeks.items() if w[0] > 0]


async def main() -> None:
    data = {}
    async with async_session() as s:
        for sym, tf, start in MARKETS:
            await sync_historical(s, sym, tf, start)
            await s.commit()
            data[(sym, tf)] = await get_klines(s, sym, tf, limit=20000)
            print(f"  data {sym} {tf}: {len(data[(sym, tf)])} candles")
    print()

    for cname, params in CONFIGS.items():
        print(f"{'='*92}\nCONFIG {cname}")
        for (sym, tf), candles in data.items():
            try:
                r = run_backtest("vol_breakout", "1", params, candles, 1000.0, FEE, tf, 1)
            except Exception as e:  # noqa: BLE001
                print(f"  {sym} {tf}: error {e}")
                continue
            wk = weekly_returns(r["equity_curve"])
            if len(wk) > 4:
                wk = wk[1:]
            npos = sum(1 for _, v in wk if v > 0)
            nflat = sum(1 for _, v in wk if v == 0)
            worst = min((v for _, v in wk), default=0.0)
            print(f"  {sym} {tf}: pnl={r['pnl_pct']:+.2f}% maxDD={r['max_dd']:.2f}% "
                  f"win={r['winrate']}% "
                  f"n={r['n_trades']} | weeks: {npos} positive + {nflat} flat / {len(wk)} "
                  f"({100*(npos+nflat)/max(len(wk),1):.0f}% non-negative), worst {worst:+.2f}%")
            # first half (out-of-sample relative to the 90d sweep) vs second half
            half = len(wk) // 2
            p1 = sum(v for _, v in wk[:half])
            p2 = sum(v for _, v in wk[half:])
            print(f"      first half (OOS) Σ{p1:+.2f}% | second half (IS) Σ{p2:+.2f}%")
    print("\nGoal: high % non-negative weeks, small worst week, maxDD < ~10%, OOS does not "
          "collapse.")


if __name__ == "__main__":
    asyncio.run(main())
