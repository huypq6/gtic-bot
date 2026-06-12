"""Sweep ict_po3 v4 (rejection sweep + displacement + cutoff + min_rr) trên 15m/5m.

Chạy:  PYTHONPATH=. uv run python scripts/sweep_ict_po3_v4.py
Xếp theo #thị-trường-dương rồi return/DD. Mục tiêu: dương đều + DD thấp (skill strategy-research).
"""

import asyncio

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

MARKETS = [
    ("BTCUSDT", "15m", "60 days ago UTC"), ("ETHUSDT", "15m", "60 days ago UTC"),
    ("BTCUSDT", "5m", "30 days ago UTC"), ("ETHUSDT", "5m", "30 days ago UTC"),
]
FEE = 0.0005
MIN_TOTAL_TRADES = 16


def build_grid() -> list[dict]:
    grid = []
    for disp in (0.0, 0.5, 1.0):
        for cutoff in (15, 18):
            for min_rr in (0.0, 1.0):
                for tp_mode, rr in ((1, 2.0), (0, 1.5)):
                    grid.append({
                        "bias_mode": 1, "bias_len": 100, "confluence": 2,
                        "mss_lookback": 2, "swing": 1,
                        "tp_mode": tp_mode, "rr_target": rr,
                        "sl_mode": 1, "atr_len": 14, "atr_mult": 1.0, "sl_buffer_pct": 0.05,
                        "news_filter": 2, "reject_sweep": 1,
                        "disp_mult": disp, "entry_cutoff_h": cutoff, "min_rr": min_rr,
                        "size": 0.001,
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
            r = run_backtest("ict_po3", "4", params, candles, 1000.0, FEE, tf, 1)
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
    return (f"disp={p['disp_mult']} cutoff={p['entry_cutoff_h']} min_rr={p['min_rr']} "
            f"tp={p['tp_mode']} rr={p['rr_target']}")


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

    print(f"\n{'='*92}\nTOP (≥{MIN_TOTAL_TRADES} lệnh; xếp #dương rồi ret/DD):")
    print(f"  {'#dương':>7} {'PnL_TB%':>9} {'maxDD%':>7} {'ret/DD':>7} {'win%':>6} {'lệnh':>5}  params")
    for r in elig[:14]:
        print(f"  {r['pos']:>5}/4 {r['mean_pnl']:>9.2f} {r['max_dd']:>7.2f} {r['calmar']:>7.2f} "
              f"{r['mean_win']:>6.1f} {r['trades']:>5}  {fmt(r['params'])}")
    if elig:
        b = elig[0]
        print(f"\nĐỀ XUẤT: {fmt(b['params'])}")
        print(f"  params = {b['params']}")
    print("\n⚠️  IN-SAMPLE → walk-forward tuần (bước sau) mới là phán quyết.")


if __name__ == "__main__":
    asyncio.run(main())
