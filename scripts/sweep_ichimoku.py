"""Quét tham số ichimoku trên dữ liệu thật (in-process). Theo skill strategy-research.

Chạy:  PYTHONPATH=. uv run python scripts/sweep_ichimoku.py

Ichimoku = trend thuần (BUY/SELL khi Tenkan×Kijun + lọc mây; thoát khi đảo tín hiệu — KHÔNG SL/TP,
giữ qua ngày). Chú ý cột maxDD: mục tiêu DD thấp khó đạt với trend giữ lệnh dài.
"""

import asyncio

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

MARKETS = [
    ("BTCUSDT", "15m", "60 days ago UTC"),
    ("ETHUSDT", "15m", "60 days ago UTC"),
    ("BTCUSDT", "1h", "180 days ago UTC"),
    ("ETHUSDT", "1h", "180 days ago UTC"),
]
FEE = 0.0005
MIN_TOTAL_TRADES = 16


def build_grid() -> list[dict]:
    grid = []
    for conv in (7, 9, 20):
        for base in (22, 26, 52):
            for span_b in (52, 104):
                if span_b < base:
                    continue
                grid.append({"conv": conv, "base": base, "span_b": span_b, "size": 0.001})
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
            r = run_backtest("ichimoku", "1", params, candles, 1000.0, FEE, tf, 1)
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
    return {"params": params, "mean_pnl": sum(pnls) / len(pnls), "worst_pnl": min(pnls),
            "pos": pos, "mean_win": sum(wins) / len(wins) if wins else 0.0,
            "trades": trades, "max_dd": worst_dd}


def fmt(p: dict) -> str:
    return f"conv={p['conv']} base={p['base']} span_b={p['span_b']}"


async def main() -> None:
    print("Nạp dữ liệu…")
    data = await load_data()
    grid = build_grid()
    print(f"\nQuét {len(grid)} bộ × {len(MARKETS)} thị trường = {len(grid) * len(MARKETS)} backtest…\n")
    results = [r for p in grid if (r := evaluate(p, data))]
    elig = [r for r in results if r["trades"] >= MIN_TOTAL_TRADES]
    elig.sort(key=lambda r: (r["pos"], r["mean_pnl"], r["worst_pnl"]), reverse=True)

    print(f"{'='*88}\nTOP (lọc ≥{MIN_TOTAL_TRADES} lệnh; xếp #thị-trường-dương, rồi PnL TB):")
    print(f"  {'#dương':>7} {'PnL_TB%':>9} {'worst%':>8} {'win%':>6} {'lệnh':>5} {'maxDD%':>7}  params")
    for r in elig[:15]:
        print(f"  {r['pos']:>5}/4 {r['mean_pnl']:>9.2f} {r['worst_pnl']:>8.2f} "
              f"{r['mean_win']:>6.1f} {r['trades']:>5} {r['max_dd']:>7.2f}  {fmt(r['params'])}")
    if elig:
        b = elig[0]
        print(f"\nĐỀ XUẤT (bền nhất): {fmt(b['params'])} → PnL TB {b['mean_pnl']:.2f}%, "
              f"lời {b['pos']}/4, win {b['mean_win']:.1f}%, maxDD {b['max_dd']:.2f}%, {b['trades']} lệnh")
        print(f"  params = {b['params']}")
    else:
        print("\nKhông bộ nào đủ lệnh.")
    print("\n⚠️  IN-SAMPLE → phải walk-forward trước khi kết luận.")


if __name__ == "__main__":
    asyncio.run(main())
