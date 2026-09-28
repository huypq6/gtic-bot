"""15m basket walk-forward for ict_po3 v3 (FIXED params) — is the edge stable over TIME?

Run:  PYTHONPATH=. uv run python scripts/walkforward_ict_po3.py

Splits each pair's history into N sequential windows and runs the default params on EACH window.
No re-optimization (params are locked in) → this is out-of-sample over time:
if the basket is positive in MOST windows the edge is stable;
if it is positive in only 1–2 windows it is regime luck.
"""

import asyncio
from datetime import UTC, datetime

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical
from app.strategy.registry import discover, get

BASKET = ["ETHUSDT", "SOLUSDT", "DOTUSDT", "DOGEUSDT", "AVAXUSDT", "XRPUSDT", "LTCUSDT", "ADAUSDT"]
TF = "15m"
HISTORY = "180 days ago UTC"
N_WINDOWS = 6
FEE = 0.0005


def _d(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).strftime("%m-%d")


async def main() -> None:
    discover()
    params = dict(get("ict_po3", "3").default_params)
    print(f"params v3 (fixed): conf={params['confluence']} sl=ATR×{params['atr_mult']} "
          f"tp_mode={params['tp_mode']} bias_len={params['bias_len']}\n")

    data: dict = {}
    async with async_session() as s:
        for sym in BASKET:
            try:
                await sync_historical(s, sym, TF, HISTORY)
                await s.commit()
                c = await get_klines(s, sym, TF, limit=40000)
            except Exception:  # noqa: BLE001
                print(f"  {sym}: sync error")
                continue
            if len(c) >= N_WINDOWS * 300:
                data[sym] = c
            else:
                print(f"  {sym}: insufficient data ({len(c)})")
    print(f"  …loaded {len(data)} pairs\n")

    # pnl[sym][w]
    pnl: dict = {sym: [None] * N_WINDOWS for sym in data}
    win_labels = [None] * N_WINDOWS
    for sym, candles in data.items():
        sz = len(candles) // N_WINDOWS
        for w in range(N_WINDOWS):
            chunk = candles[w * sz:(w + 1) * sz] if w < N_WINDOWS - 1 else candles[w * sz:]
            if len(chunk) < 300:
                continue
            if win_labels[w] is None:
                win_labels[w] = f"{_d(chunk[0]['ts'])}→{_d(chunk[-1]['ts'])}"
            try:
                r = run_backtest("ict_po3", "3", params, chunk, 1000.0, FEE, TF, 1)
                pnl[sym][w] = r["pnl_pct"]
            except Exception:  # noqa: BLE001
                pass

    # symbol × window matrix
    print(f"{'='*88}\nPnL% by window (15m, {N_WINDOWS} periods of ~30 days):")
    head = (
        "  " + f"{'symbol':<9}"
        + "".join(f"{(win_labels[w] or '?'):>13}" for w in range(N_WINDOWS))
        + f"{'#pos':>8}"
    )
    print(head)
    for sym in data:
        vals = pnl[sym]
        cells = "".join((f"{v:>13.2f}" if v is not None else f"{'—':>13}") for v in vals)
        npos = sum(1 for v in vals if v is not None and v > 0)
        print(f"  {sym:<9}{cells}{npos:>6}/{N_WINDOWS}")

    # Summary by window
    print(f"\n{'-'*88}\nBy window (basket of {len(data)} pairs):")
    print(f"  {'window':<14}{'avgPnL%':>9}{'#pos pairs':>13}")
    good_windows = 0
    for w in range(N_WINDOWS):
        vs = [pnl[sym][w] for sym in data if pnl[sym][w] is not None]
        if not vs:
            continue
        mean = sum(vs) / len(vs)
        npos = sum(1 for v in vs if v > 0)
        if mean > 0:
            good_windows += 1
        print(f"  {(win_labels[w] or '?'):<14}{mean:>9.2f}{npos:>9}/{len(vs)}")

    # Summary by pair
    print(f"\n{'-'*88}\nBy pair (across {N_WINDOWS} windows):")
    stable = []
    for sym in data:
        vs = [v for v in pnl[sym] if v is not None]
        if not vs:
            continue
        mean = sum(vs) / len(vs)
        npos = sum(1 for v in vs if v > 0)
        if npos >= (len(vs) + 1) // 2 + 1:  # positive in more than half the windows
            stable.append(sym)
        print(f"  {sym:<9} avg {mean:>6.2f}%  positive {npos}/{len(vs)} windows")

    print(f"\n{'='*88}")
    print(f"CONCLUSION: {good_windows}/{N_WINDOWS} windows with POSITIVE basket average.")
    print("STABLE pairs (positive in > half the windows): "
          f"{', '.join(stable) if stable else 'NONE'}")
    print("⚠️  Fixed params (no re-optimization). Weak edge — needs more evidence before real "
          "money.")


if __name__ == "__main__":
    asyncio.run(main())
