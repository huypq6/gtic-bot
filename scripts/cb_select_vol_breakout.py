"""Chọn config circuit-breaker cho vol_breakout trên dữ liệu ĐÃ NHÌN (365d, Jun25–Jun26).

Chạy:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/cb_select_vol_breakout.py
Sau khi chọn 1 config → phán quyết MỘT LẦN trên vùng chưa nhìn (cb_validate_vol_breakout.py).
"""

import asyncio
from datetime import datetime, timezone

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines

BASE = {"k": 0.6, "k_mode": 1, "noise_len": 40, "direction": 1, "trend_len": 0, "sl_mode": 0,
        "atr_len": 14, "atr_mult": 1.5, "entry_cutoff_h": 22, "size": 0.001}
CONFIGS = {
    "baseline (cb tắt)": {**BASE},
    "cb 10%/30d nghỉ14d": {**BASE, "cb_thresh_pct": 10.0, "cb_window_d": 30, "cb_pause_d": 14},
    "cb 8%/30d nghỉ7d":   {**BASE, "cb_thresh_pct": 8.0, "cb_window_d": 30, "cb_pause_d": 7},
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
    data = {}
    async with async_session() as s:
        for sym in SYMBOLS:
            data[sym] = await get_klines(s, sym, TF, limit=40000)
            print(f"  data {sym}: {len(data[sym])} nến "
                  f"({datetime.fromtimestamp(data[sym][0]['ts']/1000, tz=timezone.utc).date()} →)")

    for cname, params in CONFIGS.items():
        print(f"\n{'='*96}\nCONFIG {cname}")
        for sym, candles in data.items():
            r = run_backtest("vol_breakout", "1", params, candles, 1000.0, FEE, TF, 1)
            wr = window_returns(r["equity_curve"])
            pos = sum(1 for v in wr if v > 0)
            print(f"  {sym}: pnl={r['pnl_pct']:+.2f}% maxDD={r['max_dd']:.2f}% n={r['n_trades']} | "
                  f"{pos}/{len(wr)} cửa sổ dương · " + " ".join(f"{v:+.1f}%" for v in wr))
    print("\nChọn config cắt được Nov–Dec 2025 mà không giết cả năm → validate trên vùng CHƯA NHÌN.")


if __name__ == "__main__":
    asyncio.run(main())
