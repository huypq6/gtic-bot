"""Sweep ichimoku v2 (ATR trailing) — optimized for POSITIVE PnL + LOW maxDD (user goal).

Run:  PYTHONPATH=. uv run python scripts/sweep_ichimoku_v2.py
Ranked by robustness, then RETURN/DD (rough Calmar) → favours good profit/DD, not just raw PnL.
"""

import asyncio

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

# Ichimoku is trend-following → higher timeframes only (15m already tested: heavily negative,
# whipsaw).
MARKETS = [
    ("BTCUSDT", "1h", "180 days ago UTC"), ("ETHUSDT", "1h", "180 days ago UTC"),
    ("BTCUSDT", "4h", "600 days ago UTC"), ("ETHUSDT", "4h", "600 days ago UTC"),
]
FEE = 0.0005
MIN_TOTAL_TRADES = 24


def build_grid() -> list[dict]:
    grid = []
    for conv in (9, 20):
        for base in (26, 52):
            for span_b in (52, 104):
                if span_b < base:
                    continue
                for atr_mult in (1.0, 1.5, 2.0):
                    grid.append({"conv": conv, "base": base, "span_b": span_b,
                                 "atr_len": 14, "atr_mult": atr_mult, "size": 0.001})
    return grid


async def load_data() -> dict:
    data = {}
    async with async_session() as s:
        for sym, tf, start in MARKETS:
            await sync_historical(s, sym, tf, start)
            await s.commit()
            data[(sym, tf)] = await get_klines(s, sym, tf, limit=20000)
    return data


def evaluate(params: dict, data: dict) -> dict:
    pnls, wins, trades, worst_dd, pos = [], [], 0, 0.0, 0
    for (_sym, tf), candles in data.items():
        try:
            r = run_backtest("ichimoku", "2", params, candles, 1000.0, FEE, tf, 1)
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
    return f"conv={p['conv']} base={p['base']} span_b={p['span_b']} atr×{p['atr_mult']}"


async def main() -> None:
    print("Loading data…")
    data = await load_data()
    grid = build_grid()
    print(f"Sweeping {len(grid)} sets × {len(MARKETS)} = {len(grid) * len(MARKETS)} backtests…\n")
    results = [r for p in grid if (r := evaluate(p, data))]
    elig = [r for r in results if r["trades"] >= MIN_TOTAL_TRADES]
    elig.sort(key=lambda r: (r["pos"], r["calmar"], r["mean_pnl"]), reverse=True)

    print(f"{'='*92}\nTOP (≥{MIN_TOTAL_TRADES} trades; ranked by #positive, then RETURN/DD):")
    print(f"  {'#pos':>7} {'avgPnL%':>9} {'maxDD%':>7} {'ret/DD':>7} {'win%':>6} {'trades':>6}  "
          "params")
    for r in elig[:15]:
        print(f"  {r['pos']:>5}/4 {r['mean_pnl']:>9.2f} {r['max_dd']:>7.2f} {r['calmar']:>7.2f} "
              f"{r['mean_win']:>6.1f} {r['trades']:>5}  {fmt(r['params'])}")
    if elig:
        b = elig[0]
        print(f"\nRECOMMENDED: {fmt(b['params'])} → avg PnL {b['mean_pnl']:.2f}%, maxDD "
              f"{b['max_dd']:.2f}%, "
              f"ret/DD {b['calmar']:.2f}, profitable {b['pos']}/4, win {b['mean_win']:.1f}%")
        print(f"  params = {b['params']}")
    print("\n⚠️  IN-SAMPLE → walk-forward before drawing conclusions.")


if __name__ == "__main__":
    asyncio.run(main())
