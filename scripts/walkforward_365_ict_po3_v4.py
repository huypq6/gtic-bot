"""Đối chứng: ict_po3 v4 (chuẩn hiện tại) trên 365 ngày BTC 15m — có sống qua regime Aug–Dec 2025?

Chạy:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/walkforward_365_ict_po3_v4.py
v4 mới chỉ được kiểm trên 180d (Dec→Jun) — cùng cửa sổ thuận lợi với vol_breakout.
"""

import asyncio

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines

SYMBOLS = ["BTCUSDT", "SUIUSDT"]  # rổ khuyến nghị v4
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
    from app.market.store import sync_historical

    from app.strategy.registry import discover, get

    discover()
    params = dict(get("ict_po3", "4").default_params)
    data = {}
    async with async_session() as s:
        for sym in SYMBOLS:
            await sync_historical(s, sym, TF, "365 days ago UTC")
            await s.commit()
            data[sym] = await get_klines(s, sym, TF, limit=40000)
            print(f"  data {sym}: {len(data[sym])} nến")

    for sym, candles in data.items():
        r = run_backtest("ict_po3", "4", params, candles, 1000.0, FEE, TF, 1)
        wr = window_returns(r["equity_curve"])
        pos = sum(1 for v in wr if v > 0)
        nz = sum(1 for v in wr if v >= 0)
        print(f"  {sym}: pnl={r['pnl_pct']:+.2f}% maxDD={r['max_dd']:.2f}% n={r['n_trades']} | "
              f"{pos} dương / {nz} không âm / {len(wr)} cửa sổ · " +
              " ".join(f"{v:+.1f}%" for v in wr))


if __name__ == "__main__":
    asyncio.run(main())
