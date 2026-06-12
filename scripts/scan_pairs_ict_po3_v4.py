"""Quét cặp cho ict_po3 v4 (params mặc định = bộ thắng BTC 15m) — xếp theo mục tiêu user:
%tuần-không-âm cao + maxDD thấp + PnL dương.

Chạy:  PYTHONPATH=. nohup uv run python scripts/scan_pairs_ict_po3_v4.py > /tmp/scan_v4.log 2>&1 &
"""

import asyncio
from datetime import datetime, timezone

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical
from app.strategy.registry import discover, get

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT",
           "DOGEUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "NEARUSDT", "SUIUSDT", "INJUSDT"]
TFS = [("15m", "120 days ago UTC", 11520), ("5m", "45 days ago UTC", 12960)]
FEE = 0.0005


def weekly(equity):
    weeks = {}
    for ts, v in equity:
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        k = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
        weeks.setdefault(k, [v, v])[1] = v
    rs = [(b / a - 1) * 100 for a, b in weeks.values() if a > 0]
    return rs[1:] if len(rs) > 4 else rs  # bỏ tuần warmup


async def main():
    discover()
    params = dict(get("ict_po3", "4").default_params)
    print("params v4:", params, flush=True)
    rows = []
    async with async_session() as s:
        for tf, start, lim in TFS:
            for sym in SYMBOLS:
                try:
                    await sync_historical(s, sym, tf, start)
                    await s.commit()
                    candles = await get_klines(s, sym, tf, limit=lim)
                    if len(candles) < 2000:
                        print(f"  {sym} {tf}: thiếu dữ liệu", flush=True)
                        continue
                    r = run_backtest("ict_po3", "4", params, candles, 1000.0, FEE, tf, 1)
                except Exception as e:  # noqa: BLE001
                    print(f"  {sym} {tf}: lỗi {e}", flush=True)
                    continue
                wk = weekly(r["equity_curve"])
                nonneg = sum(1 for v in wk if v >= 0)
                worst = min(wk, default=0.0)
                rows.append({"sym": sym, "tf": tf, "pnl": r["pnl_pct"], "dd": r["max_dd"],
                             "win": r["winrate"], "n": r["n_trades"],
                             "wk_pct": 100 * nonneg / max(len(wk), 1), "wk_n": len(wk),
                             "worst_wk": worst})
                print(f"  ✓ {sym} {tf}: pnl={r['pnl_pct']:+.2f}% dd={r['max_dd']:.2f}% "
                      f"n={r['n_trades']} tuần-kâ={100*nonneg/max(len(wk),1):.0f}% worst={worst:+.2f}%",
                      flush=True)

    for tf, _, _ in TFS:
        sub = [r for r in rows if r["tf"] == tf]
        # điểm = ưu tiên tuần-không-âm, rồi PnL, phạt DD
        sub.sort(key=lambda r: (r["wk_pct"], r["pnl"] - r["dd"]), reverse=True)
        print(f"\n{'='*86}\n{tf} — xếp theo (%tuần-không-âm, PnL−DD):", flush=True)
        print(f"  {'symbol':<9} {'pnl%':>7} {'maxDD%':>7} {'win%':>6} {'lệnh':>5} {'%tuầnKÂ':>8} {'worstWk%':>9}")
        for r in sub:
            print(f"  {r['sym']:<9} {r['pnl']:>7.2f} {r['dd']:>7.2f} {(r['win'] or 0):>6.1f} "
                  f"{r['n']:>5} {r['wk_pct']:>7.0f}% {r['worst_wk']:>9.2f}")
    print("\nSCAN_DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
