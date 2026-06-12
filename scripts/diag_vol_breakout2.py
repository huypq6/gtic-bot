"""Chẩn đoán 2: các pattern (short>long, 16-19h âm, T2 âm) có ỔN ĐỊNH qua 2 nửa 180d không?

Chạy:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/diag_vol_breakout2.py
Pattern chỉ xuất hiện 1 nửa = nhiễu/regime → KHÔNG đưa vào v2.
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines

PARAMS = {"k": 0.6, "direction": 1, "trend_len": 0, "sl_mode": 0,
          "atr_len": 14, "atr_mult": 1.5, "entry_cutoff_h": 22, "size": 0.001}
MARKETS = [("BTCUSDT", "15m"), ("ETHUSDT", "15m"), ("SOLUSDT", "15m")]
FEE = 0.0005


def _utc(ts):
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)


async def main() -> None:
    data = {}
    async with async_session() as s:
        for sym, tf in MARKETS:
            data[(sym, tf)] = await get_klines(s, sym, tf, limit=20000)

    all_trades = []
    for (sym, tf), candles in data.items():
        r = run_backtest("vol_breakout", "1", PARAMS, candles, 1000.0, FEE, tf, 1)
        for t in r["trades"]:
            t["sym"] = sym
        all_trades += r["trades"]

    tss = sorted(t["entry_ts"] for t in all_trades if t["entry_ts"])
    mid = tss[len(tss) // 2]
    print(f"Mốc chia nửa: {_utc(mid)}\n")

    def show(label, keyf):
        b = defaultdict(lambda: [0, 0.0, 0, 0.0])  # n1, pnl1, n2, pnl2
        for t in all_trades:
            if t["pnl_pct"] is None or not t["entry_ts"]:
                continue
            k = keyf(t)
            if k is None:
                continue
            half = 0 if t["entry_ts"] < mid else 1
            b[k][half * 2] += 1
            b[k][half * 2 + 1] += t["pnl_pct"]
        print(label)
        for k, (n1, p1, n2, p2) in sorted(b.items()):
            print(f"    {k}: nửa1 n={n1:3d} Σ{p1:+7.2f}% | nửa2 n={n2:3d} Σ{p2:+7.2f}%")
        print()

    show("SIDE:", lambda t: t["side"])
    show("GIỜ 16-19 vs còn lại:", lambda t: "16-19h" if 16 <= _utc(t["entry_ts"]).hour <= 19 else "khác")
    show("THỨ HAI vs còn lại:", lambda t: "T2" if _utc(t["entry_ts"]).weekday() == 0 else "khác")
    show("THỨ BẢY vs còn lại:", lambda t: "T7" if _utc(t["entry_ts"]).weekday() == 5 else "khác")

    # đuôi lỗ: nếu cap lỗ tại −2.5%/lệnh (SL rộng) thì cải thiện bao nhiêu mỗi nửa?
    capped = [0.0, 0.0]
    raw = [0.0, 0.0]
    for t in all_trades:
        if t["pnl_pct"] is None or not t["entry_ts"]:
            continue
        half = 0 if t["entry_ts"] < mid else 1
        raw[half] += t["pnl_pct"]
        capped[half] += max(t["pnl_pct"], -2.5)
    print(f"CAP LỖ −2.5%/lệnh: nửa1 Σ{raw[0]:+.2f}%→{capped[0]:+.2f}% | nửa2 Σ{raw[1]:+.2f}%→{capped[1]:+.2f}%")


if __name__ == "__main__":
    asyncio.run(main())
