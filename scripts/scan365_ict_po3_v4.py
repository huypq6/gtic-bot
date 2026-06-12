"""Quét cặp ict_po3 v4 trên chuẩn MỚI 365 ngày (15m, params mặc định cố định).

Chạy:  PYTHONPATH=. uv run python scripts/scan365_ict_po3_v4.py SYM1 SYM2 ...
(không args = full 14 cặp). Chia nhỏ chạy song song nhiều process được.
Tiêu chí: PnL dương, maxDD < ~10% (chừa chỗ đòn bẩy), ≥2/3 cửa sổ không âm, không tháng thảm họa.
"""

import asyncio
import sys

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

ALL = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
       "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "INJUSDT", "SUIUSDT"]
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
    symbols = sys.argv[1:] or ALL

    for sym in symbols:
        async with async_session() as s:
            try:
                await sync_historical(s, sym, TF, "365 days ago UTC")
                await s.commit()
                candles = await get_klines(s, sym, TF, limit=40000)
            except Exception as e:  # noqa: BLE001
                print(f"{sym}: lỗi data {e}")
                continue
        try:
            r = run_backtest("ict_po3", "4", params, candles, 1000.0, FEE, TF, 1)
        except Exception as e:  # noqa: BLE001
            print(f"{sym}: lỗi backtest {e}")
            continue
        wr = window_returns(r["equity_curve"])
        pos = sum(1 for v in wr if v > 0)
        nneg = sum(1 for v in wr if v >= -0.005)
        worst = min(wr, default=0.0)
        print(f"{sym}: pnl={r['pnl_pct']:+6.2f}% maxDD={r['max_dd']:5.2f}% win={r['winrate']}% "
              f"n={r['n_trades']:3d} | {pos} dương/{nneg} không-âm/{len(wr)} cửa sổ, "
              f"tệ nhất {worst:+.2f}% | " + " ".join(f"{v:+.1f}" for v in wr))


if __name__ == "__main__":
    asyncio.run(main())
