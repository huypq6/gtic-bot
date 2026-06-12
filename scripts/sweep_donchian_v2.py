"""Sweep donchian v2 (breakout + ATR trail + lọc ADX/cuối tuần) trên 1h — trend intraday→swing.

Chạy:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/sweep_donchian_v2.py
Mục tiêu: giữ PnL trend của 1h (screening: donchian v1 ETH 1h +66%) nhưng ghìm DD < 10%.
"""

import asyncio

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

MARKETS = [
    ("BTCUSDT", "1h", "180 days ago UTC"), ("ETHUSDT", "1h", "180 days ago UTC"),
    ("SOLUSDT", "1h", "180 days ago UTC"), ("BTCUSDT", "15m", "90 days ago UTC"),
]
FEE = 0.0005
MIN_TOTAL_TRADES = 24


def build_grid() -> list[dict]:
    grid = []
    for period in (20, 40, 55):
        for exit_period, atr_mult in ((10, 2.0), (10, 3.0), (20, 3.0)):
            for adx_min in (0, 20):
                for dow_filter in (0, 1):
                    grid.append({
                        "period": period, "exit_period": exit_period, "exit_mode": 2,
                        "atr_len": 14, "atr_mult": atr_mult,
                        "adx_min": adx_min, "adx_len": 14,
                        "dow_filter": dow_filter, "size": 0.001,
                    })
    return grid


async def load_data() -> dict:
    data = {}
    async with async_session() as s:
        for sym, tf, start in MARKETS:
            await sync_historical(s, sym, tf, start)
            await s.commit()
            data[(sym, tf)] = await get_klines(s, sym, tf, limit=20000)
            print(f"  data {sym} {tf}: {len(data[(sym, tf)])} nến")
    return data


def evaluate(params: dict, data: dict) -> dict:
    pnls, wins, trades, worst_dd, pos = [], [], 0, 0.0, 0
    for (sym, tf), candles in data.items():
        try:
            r = run_backtest("donchian", "2", params, candles, 1000.0, FEE, tf, 1)
        except Exception:  # noqa: BLE001
            continue
        pnls.append(r["pnl_pct"])
        if r["winrate"] is not None:
            wins.append(r["winrate"])
        trades += r["n_trades"] or 0
        worst_dd = max(worst_dd, r["max_dd"] or 0.0)
        if (r["pnl_pct"] or 0) > 0:
            pos += 1
    if not pnls:
        return {}
    mean = sum(pnls) / len(pnls)
    return {"params": params, "mean_pnl": mean, "worst_pnl": min(pnls), "pos": pos,
            "mean_win": sum(wins) / len(wins) if wins else 0.0, "trades": trades,
            "max_dd": worst_dd, "calmar": mean / max(worst_dd, 1.0)}


def fmt(p: dict) -> str:
    return (f"per={p['period']} xper={p['exit_period']} atr×{p['atr_mult']} "
            f"adx≥{p['adx_min']} dow={p['dow_filter']}")


async def main() -> None:
    print("Nạp dữ liệu…")
    data = await load_data()
    grid = build_grid()
    print(f"Quét {len(grid)} bộ × {len(MARKETS)} = {len(grid) * len(MARKETS)} backtest…\n")
    results = []
    for i, p in enumerate(grid, 1):
        r = evaluate(p, data)
        if r:
            results.append(r)
        if i % 6 == 0:
            print(f"  …{i}/{len(grid)}")
    elig = [r for r in results if r["trades"] >= MIN_TOTAL_TRADES]
    elig.sort(key=lambda r: (r["pos"], r["calmar"], r["mean_pnl"]), reverse=True)

    print(f"\n{'='*96}\nTOP (≥{MIN_TOTAL_TRADES} lệnh; xếp #dương rồi ret/DD):")
    print(f"  {'#dương':>7} {'PnL_TB%':>9} {'tệ_nhất%':>9} {'maxDD%':>7} {'ret/DD':>7} {'win%':>6} {'lệnh':>5}  params")
    for r in elig[:16]:
        print(f"  {r['pos']:>5}/4 {r['mean_pnl']:>9.2f} {r['worst_pnl']:>9.2f} {r['max_dd']:>7.2f} "
              f"{r['calmar']:>7.2f} {r['mean_win']:>6.1f} {r['trades']:>5}  {fmt(r['params'])}")
    if elig:
        b = elig[0]
        print(f"\nĐỀ XUẤT: {fmt(b['params'])}")
        print(f"  params = {b['params']}")
    print("\n⚠️  IN-SAMPLE → walk-forward mới là phán quyết.")


if __name__ == "__main__":
    asyncio.run(main())
