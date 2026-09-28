"""Equal-weight vol_breakout portfolio (k0.6 sl0) on a 15m pair basket.

Measures DD/week at the PORTFOLIO level.

Run:  PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python scripts/portfolio_vol_breakout.py
Approximation: portfolio equity = mean of normalized equity curves
(equal capital split, no cross-rebalancing).
"""

import asyncio
from datetime import UTC, datetime

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

PARAMS = {"k": 0.6, "k_mode": 1, "noise_len": 40, "direction": 1, "trend_len": 0, "sl_mode": 0,
          "atr_len": 14, "atr_mult": 1.5, "entry_cutoff_h": 22, "size": 0.001}
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT"]
TF = "15m"
START = "180 days ago UTC"
FEE = 0.0005


def weekly_returns(eq: dict[int, float]) -> list[tuple[str, float]]:
    weeks: dict = {}
    for ts in sorted(eq):
        d = datetime.fromtimestamp(ts / 1000, tz=UTC)
        key = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
        weeks.setdefault(key, [eq[ts], eq[ts]])[1] = eq[ts]
    return [(k, (w[1] / w[0] - 1) * 100) for k, w in weeks.items() if w[0] > 0]


async def main() -> None:
    data = {}
    async with async_session() as s:
        for sym in SYMBOLS:
            await sync_historical(s, sym, TF, START)
            await s.commit()
            data[sym] = await get_klines(s, sym, TF, limit=20000)
            print(f"  data {sym}: {len(data[sym])} candles")
    print()

    curves = {}
    for sym, candles in data.items():
        try:
            r = run_backtest("vol_breakout", "1", PARAMS, candles, 1000.0, FEE, TF, 1)
        except Exception as e:  # noqa: BLE001
            print(f"  {sym}: error {e}")
            continue
        curves[sym] = {ts: v / 1000.0 for ts, v in r["equity_curve"]}  # normalize to 1.0
        print(f"  {sym}: pnl={r['pnl_pct']:+.2f}% maxDD={r['max_dd']:.2f}% n={r['n_trades']}")

    # downsampled equity curves have misaligned ts across pairs → 6h bins (last value in bin) +
    # forward-fill
    BIN = 6 * 3600 * 1000
    binned = {}
    for sym, c in curves.items():
        b = {}
        for ts in sorted(c):
            b[ts // BIN] = c[ts]
        binned[sym] = b
    def report(label: str, syms: list[str]) -> None:
        sel = {s: binned[s] for s in syms if s in binned}
        bins = sorted(set().union(*(set(b) for b in sel.values())))
        port = {}
        last = {sym: 1.0 for sym in sel}
        for bn in bins:
            for sym, b in sel.items():
                if bn in b:
                    last[sym] = b[bn]
            port[bn * BIN] = sum(last.values()) / len(last)
        vals = [port[t] for t in sorted(port)]
        peak, max_dd = vals[0], 0.0
        for v in vals:
            peak = max(peak, v)
            max_dd = max(max_dd, (peak - v) / peak)
        wk = weekly_returns(port)
        if len(wk) > 4:
            wk = wk[1:]
        npos = sum(1 for _, v in wk if v > 0)
        worst = min((v for _, v in wk), default=0.0)
        total = (vals[-1] / vals[0] - 1) * 100
        print(f"\nPORTFOLIO {label} ({len(sel)} pairs, {TF}, 180d):")
        print(f"  Total PnL {total:+.2f}% · maxDD {max_dd*100:.2f}% · "
              f"weeks: {npos}/{len(wk)} positive ({100*npos/max(len(wk),1):.0f}%), worst "
              f"{worst:+.2f}%")
        neg = [f"{k}:{v:+.1f}%" for k, v in wk if v <= -2]
        print(f"  Negative weeks ≤−2%: {', '.join(neg) if neg else 'none'}")

    report("all 6 pairs (no selection)", SYMBOLS)
    report("3 standard pairs (BTC/ETH/SOL — chosen BEFORE the scan, no bias)",
           ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    report("4 positive pairs (BTC/ETH/SOL/XRP — ⚠️ chosen after seeing results = selection bias)",
           ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"])


if __name__ == "__main__":
    asyncio.run(main())
