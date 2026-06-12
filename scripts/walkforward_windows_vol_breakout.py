"""Walk-forward CỬA SỔ 30 NGÀY cho vol_breakout noise40 — tiêu chí skill: dương ≥ 2/3 cửa sổ.

Chạy:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/walkforward_windows_vol_breakout.py
Params CỐ ĐỊNH. Per-cặp + danh mục equal-weight (bin 6h, forward-fill).
"""

import asyncio
from datetime import datetime, timezone

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

PARAMS = {"k": 0.6, "k_mode": 1, "noise_len": 40, "direction": 1, "trend_len": 0, "sl_mode": 0,
          "atr_len": 14, "atr_mult": 1.5, "entry_cutoff_h": 22, "size": 0.001}
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TF = "15m"
START = "365 days ago UTC"
FEE = 0.0005
WIN_MS = 30 * 24 * 3600 * 1000


def window_returns(curve: list) -> list[float]:
    """equity [[ts,v]] → PnL% từng cửa sổ 30 ngày (từ đầu curve)."""
    t0 = curve[0][0]
    wins: dict[int, list[float]] = {}
    for ts, v in curve:
        wins.setdefault((ts - t0) // WIN_MS, [v, v])[1] = v
    return [(w[1] / w[0] - 1) * 100 for i, w in sorted(wins.items())]


async def main() -> None:
    data = {}
    async with async_session() as s:
        for sym in SYMBOLS:
            await sync_historical(s, sym, TF, START)
            await s.commit()
            data[sym] = await get_klines(s, sym, TF, limit=40000)
            print(f"  data {sym}: {len(data[sym])} nến")

    curves = {}
    print(f"Cửa sổ 30 ngày, params cố định: {PARAMS}\n")
    for sym, candles in data.items():
        r = run_backtest("vol_breakout", "1", PARAMS, candles, 1000.0, FEE, TF, 1)
        curves[sym] = r["equity_curve"]
        wr = window_returns(r["equity_curve"])
        pos = sum(1 for v in wr if v > 0)
        print(f"  {sym}: {pos}/{len(wr)} cửa sổ dương · " +
              " ".join(f"{v:+.1f}%" for v in wr))

    # danh mục equal-weight
    BIN = 6 * 3600 * 1000
    binned = {s: {ts // BIN: v / 1000.0 for ts, v in c} for s, c in curves.items()}
    bins = sorted(set().union(*(set(b) for b in binned.values())))
    last = {s: 1.0 for s in binned}
    port = []
    for bn in bins:
        for s, b in binned.items():
            if bn in b:
                last[s] = b[bn]
        port.append([bn * BIN, sum(last.values()) / len(last)])
    wr = window_returns(port)
    pos = sum(1 for v in wr if v > 0)
    print(f"\n  DANH MỤC {len(binned)} cặp: {pos}/{len(wr)} cửa sổ dương · " +
          " ".join(f"{v:+.1f}%" for v in wr))
    print("\nTiêu chí skill: dương ≥ ~2/3 cửa sổ, không dồn PnL vào 1 giai đoạn.")


if __name__ == "__main__":
    asyncio.run(main())
