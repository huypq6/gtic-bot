"""Screening nhanh các strategy cổ điển có sẵn (params mặc định) — baseline trước khi viết alpha mới.

Chạy:  PYTHONPATH=. uv run python scripts/screen_classics.py
Mỗi strategy × {BTC,ETH,SOL} × {15m,1h}, 180 ngày, phí 0.05%/chiều.
Mục đích: xem classic nào đáng sweep tiếp, classic nào loại ngay.
"""

import asyncio

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

MARKETS = [
    ("BTCUSDT", "15m"), ("ETHUSDT", "15m"), ("SOLUSDT", "15m"),
    ("BTCUSDT", "1h"), ("ETHUSDT", "1h"), ("SOLUSDT", "1h"),
]
START = "180 days ago UTC"
FEE = 0.0005

CANDIDATES = [  # (name, version) — bỏ ict_po3/ichimoku (đã nghiên cứu riêng)
    ("adx", "1"), ("bollinger", "1"), ("donchian", "1"), ("ema_cross", "2"),
    ("grid", "1"), ("keltner", "1"), ("macd", "1"), ("psar", "1"),
    ("rsi_rev", "1"), ("stoch", "1"), ("supertrend", "1"), ("vwap", "1"),
]


async def load_data() -> dict:
    data = {}
    async with async_session() as s:
        for sym, tf in MARKETS:
            await sync_historical(s, sym, tf, START)
            await s.commit()
            data[(sym, tf)] = await get_klines(s, sym, tf, limit=20000)
            print(f"  data {sym} {tf}: {len(data[(sym, tf)])} nến")
    return data


async def main() -> None:
    from app.strategy.registry import discover, get

    discover()
    print("Nạp dữ liệu…")
    data = await load_data()

    rows = []
    for name, ver in CANDIDATES:
        params = dict(get(name, ver).default_params)
        per = {}
        for (sym, tf), candles in data.items():
            try:
                r = run_backtest(name, ver, params, candles, 1000.0, FEE, tf, 1)
            except Exception as e:  # noqa: BLE001
                per[(sym, tf)] = None
                continue
            per[(sym, tf)] = r
        pnls = [r["pnl_pct"] for r in per.values() if r]
        if not pnls:
            continue
        rows.append({
            "name": f"{name} v{ver}",
            "mean": sum(pnls) / len(pnls),
            "pos": sum(1 for p in pnls if p > 0),
            "n": len(pnls),
            "worst_dd": max((r["max_dd"] or 0) for r in per.values() if r),
            "trades": sum(r["n_trades"] or 0 for r in per.values() if r),
            "per": per,
        })
        print(f"  xong {name} v{ver}")

    rows.sort(key=lambda r: (r["pos"], r["mean"]), reverse=True)
    print(f"\n{'='*100}")
    print(f"{'strategy':16} {'PnL_TB%':>8} {'#dương':>7} {'maxDD%':>7} {'lệnh':>6}   per-market (pnl%)")
    for r in rows:
        per_s = " ".join(
            f"{sym[:3]}/{tf}:{(p['pnl_pct'] if p else float('nan')):+.1f}"
            for (sym, tf), p in r["per"].items()
        )
        print(f"{r['name']:16} {r['mean']:>8.2f} {r['pos']:>4}/{r['n']} {r['worst_dd']:>7.1f} "
              f"{r['trades']:>6}   {per_s}")
    print("\n⚠️  Screening thô (default params, in-sample). Chỉ dùng để CHỌN ứng viên sweep.")


if __name__ == "__main__":
    asyncio.run(main())
