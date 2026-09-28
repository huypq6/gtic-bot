"""Parameter sweep for ict_po3 on real data (in-process, no DB writes).

Run:  uv run python scripts/sweep_ict_po3.py

Ranked by ROBUSTNESS (number of profitable markets), then average PnL — favours parameter sets
that work consistently across MANY pairs/timeframes over a local peak on 1 market
(reduces overfitting).
"""

import asyncio

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

# (symbol, tf, history window)
MARKETS = [
    ("BTCUSDT", "15m", "45 days ago UTC"),
    ("ETHUSDT", "15m", "45 days ago UTC"),
    ("BTCUSDT", "1h", "120 days ago UTC"),
    ("ETHUSDT", "1h", "120 days ago UTC"),
]
FEE = 0.0005          # Futures taker (one side)
MIN_TOTAL_TRADES = 20  # sets with too few trades → dropped (sample too small)


def build_grid() -> list[dict]:
    # Keep the ATR-based SL (sl_mode=1, proven good). Sweep the FREQUENCY-REDUCING knobs to cut
    # fees:
    # confluence (3=+OB, stricter), swing (wider→fewer MSS), mss_lookback (longer debounce).
    grid = []
    for conf in (2, 3):
        for swing in (1, 2, 3):
            for mss in (2, 4):
                for tp_mode, rrs in ((0, (1.5, 2.0)), (1, (2.0,))):
                    for rr in rrs:
                        for atr_mult in (1.0, 1.5):
                            grid.append({
                                "bias_mode": 1, "confluence": conf, "tp_mode": tp_mode,
                                "rr_target": rr, "bias_len": 100, "mss_lookback": mss,
                                "swing": swing, "news_filter": 2, "sl_mode": 1,
                                "atr_len": 14, "atr_mult": atr_mult,
                                "sl_buffer_pct": 0.05, "size": 0.001,
                            })
    return grid


async def load_data() -> dict:
    data = {}
    async with async_session() as s:
        for sym, tf, start in MARKETS:
            await sync_historical(s, sym, tf, start)
            await s.commit()
            candles = await get_klines(s, sym, tf, limit=20000)
            data[(sym, tf)] = candles
            print(f"  data {sym} {tf}: {len(candles)} candles")
    return data


def evaluate(params: dict, data: dict) -> dict:
    pnls, wins, trades, worst_dd = [], [], 0, 0.0
    pos = 0
    for (_sym, tf), candles in data.items():
        try:
            r = run_backtest("ict_po3", "3", params, candles, 1000.0, FEE, tf, 1)
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
    return {
        "params": params,
        "mean_pnl": sum(pnls) / len(pnls),
        "worst_pnl": min(pnls),
        "pos": pos,                       # number of profitable markets
        "mean_win": sum(wins) / len(wins) if wins else 0.0,
        "trades": trades,
        "max_dd": worst_dd,
    }


def fmt(p: dict) -> str:
    sl = f"atr×{p['atr_mult']}" if p.get("sl_mode") == 1 else "sweep"
    return (f"conf={p['confluence']} swing={p['swing']} mss={p['mss_lookback']} "
            f"tp={p['tp_mode']} rr={p['rr_target']} sl={sl}")


async def main() -> None:
    print("Loading data (syncing from Binance if missing)…")
    data = await load_data()
    grid = build_grid()
    print(f"\nSweeping {len(grid)} parameter sets × {len(MARKETS)} markets = "
          f"{len(grid) * len(MARKETS)} backtests…\n")

    results = []
    for i, params in enumerate(grid, 1):
        r = evaluate(params, data)
        if r:
            results.append(r)
        if i % 12 == 0:
            print(f"  …{i}/{len(grid)}")

    elig = [r for r in results if r["trades"] >= MIN_TOTAL_TRADES]
    # robustness first (more profitable markets), then avg PnL, then the least-bad worst case.
    elig.sort(key=lambda r: (r["pos"], r["mean_pnl"], r["worst_pnl"]), reverse=True)

    print(f"\n{'='*92}\nTOP 15 (filtered ≥{MIN_TOTAL_TRADES} trades; ranked by "
          "#profitable-markets, then avg PnL):")
    print(f"{'#profitable-mkts':>15} {'avgPnL%':>9} {'worst%':>8} {'win%':>6} {'trades':>6} "
          f"{'maxDD%':>7}  params")
    for r in elig[:15]:
        print(f"{r['pos']:>13}/4 {r['mean_pnl']:>9.2f} {r['worst_pnl']:>8.2f} "
              f"{r['mean_win']:>6.1f} {r['trades']:>5} {r['max_dd']:>7.2f}  {fmt(r['params'])}")

    if elig:
        best = elig[0]
        print(f"\n{'='*92}\nRECOMMENDED (most robust): {fmt(best['params'])}")
        print(f"  avg PnL {best['mean_pnl']:.2f}% · profitable on {best['pos']}/4 markets · "
              f"win {best['mean_win']:.1f}% · {best['trades']} trades · "
              f"maxDD {best['max_dd']:.2f}%")
        print(f"  params = {best['params']}")
        best_pnl = max(elig, key=lambda r: r["mean_pnl"])
        if best_pnl is not best:
            print(f"\nHighest avg PnL (may be less robust): {fmt(best_pnl['params'])} "
                  f"→ {best_pnl['mean_pnl']:.2f}% avg, profitable {best_pnl['pos']}/4")
    else:
        print("\nNo parameter set meets the minimum trade count — relax MIN_TOTAL_TRADES or the "
              "data window.")
    print("\n⚠️  This is IN-SAMPLE optimization → may overfit. Validate out-of-sample (different "
          "window).")


if __name__ == "__main__":
    asyncio.run(main())
