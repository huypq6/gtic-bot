"""WEEKLY walk-forward for ict_po3 v4 — directly measures the goal "positive every week".

Run:  PYTHONPATH=. uv run python scripts/walkforward_ict_po3_v4.py

Runs 1 long backtest per (pair × TF × config), then computes PnL PER (ISO) WEEK from equity_curve →
% positive weeks, worst week, maxDD. FIXED params (no re-optimization) = out-of-sample by week.
"""

import asyncio
from datetime import UTC, datetime

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

BASE = {"bias_mode": 1, "bias_len": 100, "confluence": 2, "mss_lookback": 2, "swing": 1,
        "tp_mode": 1, "rr_target": 2.0, "sl_mode": 1, "atr_len": 14, "atr_mult": 1.0,
        "sl_buffer_pct": 0.05, "news_filter": 2, "reject_sweep": 1, "size": 0.001}
CONFIGS = {
    "tight (cutoff15)": {**BASE, "disp_mult": 0.5, "entry_cutoff_h": 15, "min_rr": 0.0},
    "medium (cutoff18+minrr)": {**BASE, "disp_mult": 0.5, "entry_cutoff_h": 18, "min_rr": 1.0},
}
MARKETS = [
    ("ETHUSDT", "15m", "180 days ago UTC", 17280),
    ("BTCUSDT", "15m", "180 days ago UTC", 17280),
    ("ETHUSDT", "5m", "60 days ago UTC", 17280),
    ("BTCUSDT", "5m", "60 days ago UTC", 17280),
]
FEE = 0.0005


def weekly_returns(equity: list) -> list[tuple[str, float]]:
    """equity [[ts_ms, value]] → [(iso_week, pnl%)]."""
    weeks: dict = {}
    for ts, v in equity:
        d = datetime.fromtimestamp(ts / 1000, tz=UTC)
        key = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
        weeks.setdefault(key, [v, v])[1] = v  # [first, last]
    return [(k, (w[1] / w[0] - 1) * 100) for k, w in weeks.items() if w[0] > 0]


async def main() -> None:
    data = {}
    async with async_session() as s:
        for sym, tf, start, lim in MARKETS:
            await sync_historical(s, sym, tf, start)
            await s.commit()
            data[(sym, tf)] = await get_klines(s, sym, tf, limit=lim)
            print(f"  data {sym} {tf}: {len(data[(sym, tf)])} candles")
    print()

    for cname, params in CONFIGS.items():
        print(f"{'='*86}\nCONFIG {cname}: disp={params['disp_mult']} "
              f"cutoff={params['entry_cutoff_h']} min_rr={params['min_rr']}")
        for (sym, tf), candles in data.items():
            try:
                r = run_backtest("ict_po3", "4", params, candles, 1000.0, FEE, tf, 1)
            except Exception as e:  # noqa: BLE001
                print(f"  {sym} {tf}: error {e}")
                continue
            wk = weekly_returns(r["equity_curve"])
            # drop the first week (EMA warmup bias) if ≥ 4 weeks
            if len(wk) > 4:
                wk = wk[1:]
            npos = sum(1 for _, v in wk if v > 0)
            nflat = sum(1 for _, v in wk if v == 0)
            worst = min((v for _, v in wk), default=0.0)
            print(f"  {sym} {tf}: pnl={r['pnl_pct']:+.2f}% maxDD={r['max_dd']:.2f}% "
                  f"win={r['winrate']}% "
                  f"n={r['n_trades']} | weeks: {npos} positive + {nflat} flat / {len(wk)} "
                  f"({100*(npos+nflat)/max(len(wk),1):.0f}% non-negative), worst {worst:+.2f}%")
    print("\nGoal: high % non-negative weeks (ideally 100%), small worst week, maxDD < ~10%.")


if __name__ == "__main__":
    asyncio.run(main())
