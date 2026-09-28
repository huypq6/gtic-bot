"""ONE-SHOT VERDICT: vol_breakout (noise40 + chosen CB) on the UNSEEN period Jun24–Jun25.

Run:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/cb_validate_vol_breakout.py
Rule: do not iterate on this period. Run the baseline + the locked-in CB config, report, done.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines

BASE = {"k": 0.6, "k_mode": 1, "noise_len": 40, "direction": 1, "trend_len": 0, "sl_mode": 0,
        "atr_len": 14, "atr_mult": 1.5, "entry_cutoff_h": 22, "size": 0.001}
CONFIGS = {
    "baseline (cb off)": {**BASE},
    "cb LOCKED IN": {**BASE, "cb_thresh_pct": 10.0, "cb_window_d": 30, "cb_pause_d": 14},
}
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
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
    now = datetime.now(tz=UTC)
    start = now - timedelta(days=730)
    end = now - timedelta(days=360)  # stop before the already-seen period (365d)
    data = {}
    async with async_session() as s:
        for sym in SYMBOLS:
            data[sym] = await get_klines(s, sym, TF, start=start, end=end, limit=40000)
            ks = data[sym]
            print(f"  data {sym}: {len(ks)} candles "
                  f"({datetime.fromtimestamp(ks[0]['ts']/1000, tz=UTC).date()} → "
                  f"{datetime.fromtimestamp(ks[-1]['ts']/1000, tz=UTC).date()})")

    for cname, params in CONFIGS.items():
        print(f"\n{'='*96}\nCONFIG {cname}")
        for sym, candles in data.items():
            r = run_backtest("vol_breakout", "1", params, candles, 1000.0, FEE, TF, 1)
            wr = window_returns(r["equity_curve"])
            pos = sum(1 for v in wr if v > 0)
            print(f"  {sym}: pnl={r['pnl_pct']:+.2f}% maxDD={r['max_dd']:.2f}% n={r['n_trades']} | "
                  f"{pos}/{len(wr)} windows positive · " + " ".join(f"{v:+.1f}%" for v in wr))
    print("\n⚠️  Unseen period — this result IS the verdict, do not iterate further.")


if __name__ == "__main__":
    asyncio.run(main())
