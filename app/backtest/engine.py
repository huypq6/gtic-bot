"""Backtest engine — dùng CHUNG `Strategy.on_candle` (như paper/live, chống RK-4),
fill giả lập bằng **vectorbt**.

Quy trình: nạp nến lịch sử → replay on_candle để sinh tín hiệu long/short →
`vbt.Portfolio.from_signals` tính metrics + equity curve + danh sách trade.

vectorbt là dep nặng (numba) → import LAZY trong hàm để app prod không cài cũng chạy
được phần còn lại. Hàm chạy sync (gọi trong threadpool ở API).
"""

from app.strategy.base import Context
from app.strategy.registry import discover, get

_TF_FREQ = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1d"}


def _build_signals(strategy, candles: list[dict]):
    """Replay on_candle → 4 mảng bool (long/short entries/exits)."""
    from app.strategy.base import Position

    n = len(candles)
    long_e = [False] * n
    long_x = [False] * n
    short_e = [False] * n
    short_x = [False] * n
    pos: Position | None = None  # theo dõi vị thế để bơm vào ctx.position (như live)
    for i in range(n):
        price = candles[i]["close"]
        symbol = candles[i].get("symbol", "")
        ctx = Context(symbol=symbol, price=price, candles=candles[: i + 1], position=pos)
        for sig in strategy.on_candle(ctx):
            if sig.action == "BUY":
                long_e[i] = True
                short_x[i] = True
                pos = Position(symbol, "LONG", sig.size, price)
            elif sig.action == "SELL":
                short_e[i] = True
                long_x[i] = True
                pos = Position(symbol, "SHORT", sig.size, price)
            elif sig.action == "CLOSE":
                long_x[i] = True
                short_x[i] = True
                pos = None
    return long_e, long_x, short_e, short_x


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
) -> dict:
    """Trả về dict metrics + equity_curve + trades. `candles` theo thời gian tăng dần."""
    import numpy as np
    import pandas as pd
    import vectorbt as vbt

    if len(candles) < 5:
        raise ValueError("không đủ dữ liệu để backtest")

    discover()
    strategy = get(strategy_name, strategy_version)(params)
    long_e, long_x, short_e, short_x = _build_signals(strategy, candles)

    idx = pd.to_datetime([c["ts"] for c in candles], unit="ms", utc=True)
    close = pd.Series([c["close"] for c in candles], index=idx)
    freq = _TF_FREQ.get(tf, "1min")

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
    # downsample equity curve ~500 điểm cho JSONB.
    step = max(1, len(value) // 500)
    equity = [
        [int(ts.timestamp() * 1000), round(float(v), 2)]
        for ts, v in zip(value.index[::step], value.values[::step], strict=False)
    ]

    trades = []
    rec = pf.trades.records_readable
    for _, t in rec.iterrows():
        trades.append(
            {
                "side": str(t["Direction"]),
                "entry_ts": int(pd.Timestamp(t["Entry Timestamp"]).timestamp() * 1000),
                "entry": _safe(t["Avg Entry Price"]),
                "exit_ts": int(pd.Timestamp(t["Exit Timestamp"]).timestamp() * 1000)
                if pd.notna(t["Exit Timestamp"])
                else None,
                "exit": _safe(t["Avg Exit Price"]),
                "pnl_pct": round((_safe(t["Return"]) or 0.0) * 100, 4),
            }
        )

    return {
        "pnl_pct": round((_safe(pf.total_return()) or 0.0) * 100, 4),
        "winrate": round((_safe(pf.trades.win_rate()) or 0.0) * 100, 2),
        "max_dd": round(abs(_safe(pf.max_drawdown()) or 0.0) * 100, 4),
        "sharpe": _safe(pf.sharpe_ratio()),
        "n_trades": int(pf.trades.count()),
        "equity_curve": equity,
        "trades": trades,
    }
