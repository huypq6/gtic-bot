"""Walk-forward THEO TUẦN cho vol_breakout — đo mục tiêu "dương đều mỗi tuần, DD thấp".

Chạy:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/walkforward_vol_breakout.py

1 backtest dài / (cặp × TF × config), tính PnL từng tuần ISO từ equity_curve.
Params CỐ ĐỊNH từ sweep (in-sample 90d) → chạy 180d = nửa đầu là out-of-sample.
"""

import asyncio
from datetime import datetime, timezone

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

BASE = {"direction": 1, "atr_len": 14, "atr_mult": 1.5, "entry_cutoff_h": 22, "size": 0.001}
CONFIGS = {
    "k0.6 sl0 (chuẩn)":  {**BASE, "k": 0.6, "trend_len": 0, "sl_mode": 0},
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
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
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
            print(f"  data {sym} {tf}: {len(data[(sym, tf)])} nến")
    print()

    for cname, params in CONFIGS.items():
        print(f"{'='*92}\nCONFIG {cname}")
        for (sym, tf), candles in data.items():
            try:
                r = run_backtest("vol_breakout", "1", params, candles, 1000.0, FEE, tf, 1)
            except Exception as e:  # noqa: BLE001
                print(f"  {sym} {tf}: lỗi {e}")
                continue
            wk = weekly_returns(r["equity_curve"])
            if len(wk) > 4:
                wk = wk[1:]
            npos = sum(1 for _, v in wk if v > 0)
            nflat = sum(1 for _, v in wk if v == 0)
            worst = min((v for _, v in wk), default=0.0)
            print(f"  {sym} {tf}: pnl={r['pnl_pct']:+.2f}% maxDD={r['max_dd']:.2f}% win={r['winrate']}% "
                  f"n={r['n_trades']} | tuần: {npos} dương + {nflat} đứng / {len(wk)} "
                  f"({100*(npos+nflat)/max(len(wk),1):.0f}% không âm), tệ nhất {worst:+.2f}%")
            # nửa đầu (out-of-sample so với sweep 90d) vs nửa sau
            half = len(wk) // 2
            p1 = sum(v for _, v in wk[:half])
            p2 = sum(v for _, v in wk[half:])
            print(f"      nửa đầu (OOS) Σ{p1:+.2f}% | nửa sau (IS) Σ{p2:+.2f}%")
    print("\nMục tiêu: %tuần-không-âm cao, tuần tệ nhất nhỏ, maxDD < ~10%, OOS không sập.")


if __name__ == "__main__":
    asyncio.run(main())
