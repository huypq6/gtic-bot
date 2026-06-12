"""Walk-forward THEO TUẦN cho ict_po3 v4 — đo trực tiếp mục tiêu "dương sau mỗi tuần".

Chạy:  PYTHONPATH=. uv run python scripts/walkforward_ict_po3_v4.py

Chạy 1 backtest dài / (cặp × TF × config), rồi tính PnL TỪNG TUẦN (ISO) từ equity_curve →
%tuần dương, tuần xấu nhất, maxDD. Params CỐ ĐỊNH (không re-optimize) = out-of-sample theo tuần.
"""

import asyncio
from datetime import datetime, timezone

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

BASE = {"bias_mode": 1, "bias_len": 100, "confluence": 2, "mss_lookback": 2, "swing": 1,
        "tp_mode": 1, "rr_target": 2.0, "sl_mode": 1, "atr_len": 14, "atr_mult": 1.0,
        "sl_buffer_pct": 0.05, "news_filter": 2, "reject_sweep": 1, "size": 0.001}
CONFIGS = {
    "chặt (cutoff15)": {**BASE, "disp_mult": 0.5, "entry_cutoff_h": 15, "min_rr": 0.0},
    "vừa (cutoff18+minrr)": {**BASE, "disp_mult": 0.5, "entry_cutoff_h": 18, "min_rr": 1.0},
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
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
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
            print(f"  data {sym} {tf}: {len(data[(sym, tf)])} nến")
    print()

    for cname, params in CONFIGS.items():
        print(f"{'='*86}\nCONFIG {cname}: disp={params['disp_mult']} cutoff={params['entry_cutoff_h']} min_rr={params['min_rr']}")
        for (sym, tf), candles in data.items():
            try:
                r = run_backtest("ict_po3", "4", params, candles, 1000.0, FEE, tf, 1)
            except Exception as e:  # noqa: BLE001
                print(f"  {sym} {tf}: lỗi {e}")
                continue
            wk = weekly_returns(r["equity_curve"])
            # bỏ tuần đầu (warmup bias EMA) nếu ≥ 4 tuần
            if len(wk) > 4:
                wk = wk[1:]
            npos = sum(1 for _, v in wk if v > 0)
            nflat = sum(1 for _, v in wk if v == 0)
            worst = min((v for _, v in wk), default=0.0)
            print(f"  {sym} {tf}: pnl={r['pnl_pct']:+.2f}% maxDD={r['max_dd']:.2f}% win={r['winrate']}% "
                  f"n={r['n_trades']} | tuần: {npos} dương + {nflat} đứng / {len(wk)} "
                  f"({100*(npos+nflat)/max(len(wk),1):.0f}% không âm), tệ nhất {worst:+.2f}%")
    print("\nMục tiêu: %tuần-không-âm cao (lý tưởng 100%), tuần tệ nhất nhỏ, maxDD < ~10%.")


if __name__ == "__main__":
    asyncio.run(main())
