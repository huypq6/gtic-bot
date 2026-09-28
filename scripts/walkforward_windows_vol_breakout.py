"""30-DAY WINDOW walk-forward for vol_breakout noise40.

Skill criterion: positive in ≥ 2/3 of windows.

Run:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/walkforward_windows_vol_breakout.py
FIXED params. Per pair + equal-weight portfolio (6h bins, forward-fill).
"""

import asyncio

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
    """equity [[ts,v]] → PnL% per 30-day window (from the start of the curve)."""
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
            print(f"  data {sym}: {len(data[sym])} candles")

    curves = {}
    print(f"30-day windows, fixed params: {PARAMS}\n")
    for sym, candles in data.items():
        r = run_backtest("vol_breakout", "1", PARAMS, candles, 1000.0, FEE, TF, 1)
        curves[sym] = r["equity_curve"]
        wr = window_returns(r["equity_curve"])
        pos = sum(1 for v in wr if v > 0)
        print(f"  {sym}: {pos}/{len(wr)} windows positive · " +
              " ".join(f"{v:+.1f}%" for v in wr))

    # equal-weight portfolio
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
    print(f"\n  PORTFOLIO {len(binned)} pairs: {pos}/{len(wr)} windows positive · " +
          " ".join(f"{v:+.1f}%" for v in wr))
    print("\nSkill criterion: positive in ≥ ~2/3 of windows, PnL not concentrated in a single "
          "period.")


if __name__ == "__main__":
    asyncio.run(main())
