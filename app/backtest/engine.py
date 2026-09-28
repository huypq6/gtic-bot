"""Backtest engine — uses the SAME `Strategy.on_candle` (as paper/live, mitigates RK-4),
with simulated fills via **vectorbt**.

Flow: load historical candles → replay on_candle to produce long/short signals →
`vbt.Portfolio.from_signals` computes metrics + equity curve + trade list.

vectorbt is a heavy dependency (numba) → imported LAZILY inside functions so a prod app without it
can still run everything else. Functions are sync (called in a threadpool by the API).
"""

from app.strategy.base import Context
from app.strategy.registry import discover, get

_TF_FREQ = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1d"}


def _build_signals(strategy, candles: list[dict]):
    """Replay on_candle → 4 bool arrays (long/short entries/exits)."""
    from app.strategy.base import Position

    n = len(candles)
    long_e = [False] * n
    long_x = [False] * n
    short_e = [False] * n
    short_x = [False] * n
    pos: Position | None = None  # track the position to inject into ctx.position (as in live)
    sltp: dict[int, tuple] = {}  # entry ts → (sl, tp) to attach to the trade
    for i in range(n):
        price = candles[i]["close"]
        symbol = candles[i].get("symbol", "")
        ctx = Context(symbol=symbol, price=price, candles=candles[: i + 1], position=pos)
        for sig in strategy.on_candle(ctx):
            if sig.action == "BUY":
                long_e[i] = True
                short_x[i] = True
                pos = Position(symbol, "LONG", sig.size, price)
                sltp[candles[i]["ts"]] = (sig.sl, sig.tp)
            elif sig.action == "SELL":
                short_e[i] = True
                long_x[i] = True
                pos = Position(symbol, "SHORT", sig.size, price)
                sltp[candles[i]["ts"]] = (sig.sl, sig.tp)
            elif sig.action == "CLOSE":
                long_x[i] = True
                short_x[i] = True
                pos = None
    return long_e, long_x, short_e, short_x, sltp


def _safe(v) -> float | None:
    import math

    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else f


def run_backtest(
    strategy_name: str,
    strategy_version: str,
    params: dict,
    candles: list[dict],
    capital: float = 10_000.0,
    fee_rate: float = 0.001,
    tf: str = "1m",
    leverage: int = 1,
) -> dict:
    """Backtest. `fee_rate` = one-way fee (Binance spot 0.001 / futures 0.0005).

    `leverage` (Futures): amplifies profit, loss and fees by notional = capital × leverage.
    Simulated by scaling each candle's return × leverage on the REAL capital; if equity
    hits 0 → mark as `liquidated` (account blown).
    """
    import numpy as np
    import pandas as pd
    import vectorbt as vbt

    if len(candles) < 5:
        raise ValueError("not enough data to backtest")
    leverage = max(1, int(leverage))

    discover()
    strategy = get(strategy_name, strategy_version)(params)
    long_e, long_x, short_e, short_x, sltp = _build_signals(strategy, candles)

    # indicator overlay lines per strategy (US-11 extension).
    # Shape: {name: {"pane": 0|1, "data": [[ts, value], ...]}}. pane 1 = oscillator (RSI/ADX/…).
    indicators: dict[str, dict] = {}
    try:
        pane_map = strategy.plot_pane()
        for name, series in strategy.plot(candles).items():
            indicators[name] = {
                "pane": int(pane_map.get(name, 0)),
                "data": [
                    [candles[i]["ts"], round(float(v), 6)]
                    for i, v in enumerate(series)
                    if v is not None
                ],
            }
    except Exception:  # noqa: BLE001 — a plot error must not block the backtest
        indicators = {}

    idx = pd.to_datetime([c["ts"] for c in candles], unit="ms", utc=True)
    close = pd.Series([c["close"] for c in candles], index=idx)
    freq = _TF_FREQ.get(tf, "1min")

    # vbt runs at notional = capital (1×); leverage is applied afterwards on the CAPITAL.
    pf = vbt.Portfolio.from_signals(
        close,
        entries=np.array(long_e),
        exits=np.array(long_x),
        short_entries=np.array(short_e),
        short_exits=np.array(short_x),
        init_cash=capital,
        fees=fee_rate,
        freq=freq,
    )

    value = pf.value()
    vals = value.values.astype(float)
    # per-candle returns (fees included) → amplified × leverage on the real capital.
    eq = np.empty(len(vals))
    eq[0] = capital
    liquidated = False
    for i in range(1, len(vals)):
        if liquidated:
            eq[i] = 0.0
            continue
        r = (vals[i] / vals[i - 1] - 1.0) if vals[i - 1] else 0.0
        nxt = eq[i - 1] * (1 + r * leverage)
        if nxt <= 0:
            eq[i] = 0.0
            liquidated = True
        else:
            eq[i] = nxt

    # metrics on the leveraged equity.
    final = float(eq[-1])
    pnl_pct = (final / capital - 1) * 100
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / np.where(peak == 0, 1, peak)
    max_dd = float(abs(dd.min())) * 100

    step = max(1, len(eq) // 500)
    equity = [
        [int(ts.timestamp() * 1000), round(float(v), 2)]
        for ts, v in zip(value.index[::step], eq[::step], strict=False)
    ]

    trades = []
    rec = pf.trades.records_readable
    for _, t in rec.iterrows():
        entry_ts = int(pd.Timestamp(t["Entry Timestamp"]).timestamp() * 1000)
        sl, tp = sltp.get(entry_ts, (None, None))
        trades.append(
            {
                "side": str(t["Direction"]),
                "entry_ts": entry_ts,
                "entry": _safe(t["Avg Entry Price"]),
                "exit_ts": int(pd.Timestamp(t["Exit Timestamp"]).timestamp() * 1000)
                if pd.notna(t["Exit Timestamp"])
                else None,
                "exit": _safe(t["Avg Exit Price"]),
                "pnl_pct": round((_safe(t["Return"]) or 0.0) * 100 * leverage, 4),  # × leverage
                "sl": _safe(sl),
                "tp": _safe(tp),
            }
        )

    return {
        "pnl_pct": round(pnl_pct, 4),
        "winrate": round((_safe(pf.trades.win_rate()) or 0.0) * 100, 2),
        "max_dd": round(max_dd, 4),
        "sharpe": _safe(pf.sharpe_ratio()),  # ~invariant to leverage (before liquidation)
        "n_trades": int(pf.trades.count()),
        "leverage": leverage,
        "liquidated": liquidated,
        "from_ts": candles[0]["ts"],
        "to_ts": candles[-1]["ts"],
        "indicators": indicators,
        "equity_curve": equity,
        "trades": trades,
    }
