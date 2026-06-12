"""Chẩn đoán vol_breakout (k0.6 sl0): lỗ tập trung ở đâu? — side / giờ vào / thứ / range hôm trước.

Chạy:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/diag_vol_breakout.py
Mục đích: tìm fix MÔ HÌNH ghìm DD (không tinh chỉnh tham số mù).
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


def bucket_stats(trades, keyf):
    b = defaultdict(list)
    for t in trades:
        if t["pnl_pct"] is None or t["entry_ts"] is None:
            continue
        b[keyf(t)].append(t["pnl_pct"])
    return {k: (len(v), sum(v), sum(1 for x in v if x > 0)) for k, v in sorted(b.items())}


async def main() -> None:
    data = {}
    async with async_session() as s:
        for sym, tf in MARKETS:
            data[(sym, tf)] = await get_klines(s, sym, tf, limit=20000)

    all_trades = []
    for (sym, tf), candles in data.items():
        r = run_backtest("vol_breakout", "1", PARAMS, candles, 1000.0, FEE, tf, 1)
        # range hôm trước theo ngày để bucket theo độ rộng range
        by_day = {}
        for c in candles:
            d = _utc(c["ts"]).date()
            hi, lo, op = by_day.get(d, (c["high"], c["low"], c["open"]))[0:3] if d in by_day else (c["high"], c["low"], c["open"])
            by_day[d] = (max(hi, c["high"]), min(lo, c["low"]), op)
        days = sorted(by_day)
        prev_rng_pct = {}
        for i in range(1, len(days)):
            hi, lo, _ = by_day[days[i - 1]]
            op = by_day[days[i]][2]
            prev_rng_pct[days[i]] = (hi - lo) / op * 100
        for t in r["trades"]:
            t["sym"] = sym
            d = _utc(t["entry_ts"]).date() if t["entry_ts"] else None
            t["prev_rng"] = prev_rng_pct.get(d)
        all_trades += r["trades"]
        print(f"{sym}: pnl={r['pnl_pct']:+.2f}% n={r['n_trades']}")

    print(f"\nTổng {len(all_trades)} lệnh (3 cặp, 180d)\n")
    fmt = lambda st: "\n".join(
        f"    {k}: n={n:3d} Σpnl={s:+7.2f}% win={100*w/max(n,1):.0f}%" for k, (n, s, w) in st.items()
    )
    print("Theo SIDE:")
    print(fmt(bucket_stats(all_trades, lambda t: t["side"])))
    print("Theo GIỜ vào (UTC, gộp 4h):")
    print(fmt(bucket_stats(all_trades, lambda t: f"{(_utc(t['entry_ts']).hour // 4) * 4:02d}-{(_utc(t['entry_ts']).hour // 4) * 4 + 3:02d}")))
    print("Theo THỨ (0=T2):")
    print(fmt(bucket_stats(all_trades, lambda t: _utc(t["entry_ts"]).weekday())))
    print("Theo RANGE hôm trước (% open):")
    print(fmt(bucket_stats(
        [t for t in all_trades if t.get("prev_rng") is not None],
        lambda t: f"{'<2%' if t['prev_rng'] < 2 else '2-4%' if t['prev_rng'] < 4 else '4-6%' if t['prev_rng'] < 6 else '>6%'}",
    )))
    print("Theo THỜI GIAN GIỮ (giờ):")
    print(fmt(bucket_stats(
        [t for t in all_trades if t["exit_ts"]],
        lambda t: f"{min((t['exit_ts'] - t['entry_ts']) // 3_600_000 // 6 * 6, 24):02d}h+",
    )))
    print("\n10 lệnh TỆ nhất:")
    for t in sorted(all_trades, key=lambda t: t["pnl_pct"] or 0)[:10]:
        print(f"    {t['sym']} {t['side']} {_utc(t['entry_ts'])} pnl={t['pnl_pct']:+.2f}% prev_rng={t.get('prev_rng') and round(t['prev_rng'],1)}%")


if __name__ == "__main__":
    asyncio.run(main())
