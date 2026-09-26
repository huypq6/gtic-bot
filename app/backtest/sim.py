"""Backtest MÔ PHỎNG TÀI KHOẢN (P9c) — cùng luật với paper/live, khác vectorbt ở chỗ:

- Khối lượng theo quản lý vốn (`size_order`: risk_pct/risk_usdt/notional…) + rào chắn
  (trần rủi ro, lỗ ngày → nghỉ hết ngày UTC, sụt vốn → DỪNG) — cùng code với runner live.
- Khớp bằng `PaperEngine` y như paper: phí taker/maker, trượt giá, SL khớp theo gap,
  đòn bẩy + thanh lý. SL/TP/limit kiểm TRONG nến theo đường O→(L,H)→C (nến tăng: O→L→H→C;
  nến giảm: O→H→L→C) — bi quan vừa phải, như tick live đi qua.
- Strategy nhận cửa sổ trượt `window` nến cuối (= deque của StrategyRunner) và tín hiệu
  khớp ở giá đóng nến (= tick đầu tiên sau khi nến đóng ở live).
- Lãi kép: vốn tăng/giảm → lệnh sau to/nhỏ theo equity.

Thuần Python, không vectorbt, không DB → test được; chạy sync (API gọi trong threadpool).
"""

import math
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from app.account.risk import (
    AccountState,
    Limits,
    RiskReject,
    check_halt,
    position_risk,
    size_order,
)
from app.execution.paper_engine import PaperEngine
from app.strategy.base import Context
from app.strategy.registry import discover, get

TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000,
         "4h": 14_400_000, "1d": 86_400_000}
DAY_MS = 86_400_000


@dataclass
class SimConfig:
    capital: float = 1_000.0
    sizing: dict = field(default_factory=lambda: {"method": "risk_pct", "value": 1.0})
    leverage: float = 1.0
    taker_fee: float = 0.0005  # Binance USDT-M VIP0
    maker_fee: float = 0.0002
    slippage_bps: float = 2.0
    max_risk_pct: float | None = None
    max_open_risk_pct: float | None = None
    daily_loss_pct: float | None = None
    max_dd_pct: float | None = None
    window: int = 1000  # = lookback của StrategyRunner

    def limits(self) -> Limits:
        return Limits(
            leverage=self.leverage, taker_fee=self.taker_fee, max_risk_pct=self.max_risk_pct,
            max_open_risk_pct=self.max_open_risk_pct, daily_loss_pct=self.daily_loss_pct,
            max_dd_pct=self.max_dd_pct,
        )


def _path(c: dict) -> tuple[float, float, float, float]:
    o, h, lo, cl = c["open"], c["high"], c["low"], c["close"]
    return (o, lo, h, cl) if cl >= o else (o, h, lo, cl)


class _Sim:
    def __init__(self, symbol: str, cfg: SimConfig, tf_ms: int) -> None:
        self.cfg, self.symbol, self.tf_ms = cfg, symbol, tf_ms
        self.lim = cfg.limits()
        self.eng = PaperEngine(
            symbol, cfg.taker_fee, cfg.maker_fee, cfg.slippage_bps, gap_fill=True,
            leverage=cfg.leverage,
        )
        self.balance = cfg.capital
        self.peak = cfg.capital
        self.day = None
        self.day_start_balance = cfg.capital
        self.realized_today = 0.0
        self.halted_until_day: int | None = None  # nghỉ vì lỗ ngày
        self.dd_halt_ts: int | None = None  # DỪNG vì sụt vốn (không tự mở lại)
        self.n_day_halts = 0
        self.liquidated = False
        self.open: dict | None = None  # meta vị thế đang mở
        self.trades: list[dict] = []
        self.rejects: dict[str, int] = {}
        self.capped: dict[str, int] = {}  # lệnh bị CO khối lượng (vẫn vào) theo lý do
        self.fees = 0.0

    # ---------- trạng thái tài khoản ----------
    def unrealized(self, price: float) -> float:
        return self.eng.unrealized_pnl(price)

    def state(self, price: float) -> AccountState:
        p = self.eng.position
        eq = self.balance + self.unrealized(price)
        margin = self.eng.margin()
        return AccountState(
            balance=self.balance, equity=eq, used_margin=margin, available=eq - margin,
            open_risk=position_risk(p.side, p.qty, p.entry_price, p.sl) if p else 0.0,
            n_open=1 if p else 0, daily_pnl=self.realized_today + self.unrealized(price),
            day_start_balance=self.day_start_balance, peak_equity=max(self.peak, eq),
        )

    def new_day(self, ts: int) -> None:
        d = ts // DAY_MS
        if d != self.day:
            self.day = d
            self.day_start_balance = self.balance
            self.realized_today = 0.0

    # ---------- sự kiện engine → sổ sách ----------
    def apply(self, events, ts: int, sig=None) -> None:
        for e in events:
            if e.closed:
                self._close(e.closed, ts)
            if e.opened:
                self._open(e, ts, sig)

    def _open(self, e, ts: int, sig) -> None:
        p = self.eng.position
        fee = self.eng.entry_fee
        self.balance -= fee
        self.realized_today -= fee
        self.fees += fee
        eq = self.balance + fee  # equity lúc quyết định vào (trước phí)
        self.open = {
            "side": p.side, "entry_ts": ts, "entry": p.entry_price, "qty": p.qty,
            "sl": p.sl, "tp": p.tp, "risk": position_risk(p.side, p.qty, p.entry_price, p.sl)
            if p.sl is not None else None,
            "equity_at_entry": eq, "mfe": 0.0, "mae": 0.0,
            "order_type": e.fill.type if e.fill else (sig.order_type if sig else "MARKET"),
        }

    def _close(self, cl, ts: int) -> None:
        self.balance += cl.gross - cl.exit_fee
        self.realized_today += cl.gross - cl.exit_fee
        self.fees += cl.exit_fee
        m = self.open or {}
        risk = m.get("risk")
        stop = abs(m["entry"] - m["sl"]) if m.get("sl") is not None else None
        self.trades.append({
            "side": "Long" if cl.side == "LONG" else "Short",
            "entry_ts": m.get("entry_ts"), "entry": cl.entry_price,
            "exit_ts": ts, "exit": cl.exit_price, "qty": cl.qty,
            "sl": m.get("sl"), "tp": m.get("tp"), "reason": cl.reason,
            "pnl": cl.pnl, "fee": cl.entry_fee + cl.exit_fee,
            "pnl_pct": cl.pnl / m["equity_at_entry"] * 100 if m.get("equity_at_entry") else None,
            "r": cl.pnl / risk if risk else None,
            "mfe_r": m["mfe"] / stop if stop else None,
            "mae_r": m["mae"] / stop if stop else None,
            "notional": cl.entry_price * cl.qty,
            "equity_at_entry": m.get("equity_at_entry"),
        })
        self.open = None
        if cl.reason == "LIQUIDATION" or self.balance <= 0:
            self.liquidated = self.liquidated or self.balance <= 0

    def track(self, price: float) -> None:
        m, p = self.open, self.eng.position
        if not (m and p):
            return
        fav = (price - p.entry_price) if p.side == "LONG" else (p.entry_price - price)
        m["mfe"] = max(m["mfe"], fav)
        m["mae"] = max(m["mae"], -fav)

    # ---------- rào chắn ----------
    def blocked(self, ts: int, price: float) -> str | None:
        if self.liquidated:
            return "tài khoản cháy"
        if self.dd_halt_ts is not None:
            return "tài khoản DỪNG do sụt vốn"
        if self.halted_until_day is not None and ts // DAY_MS < self.halted_until_day:
            return "nghỉ tới hết ngày do lỗ ngày"
        why = check_halt(self.state(price), self.lim)
        if why:
            if self.lim.max_dd_pct is not None and self.state(price).dd_pct >= self.lim.max_dd_pct:
                self.dd_halt_ts = ts
            else:
                self.halted_until_day = ts // DAY_MS + 1
                self.n_day_halts += 1
            return why
        return None

    def reject(self, reason: str) -> None:
        key = reason.split(" ")[0] if reason else "?"
        key = {"sụt": "sụt vốn", "lỗ": "lỗ ngày", "nghỉ": "lỗ ngày", "tài": "tài khoản dừng",
               "tổng": "tổng rủi ro mở", "giá": "dưới tối thiểu", "không": "không đủ số dư",
               "phương": "thiếu SL"}.get(key, reason)
        self.rejects[key] = self.rejects.get(key, 0) + 1


def simulate(
    strategy_name: str,
    strategy_version: str,
    params: dict,
    candles: list[dict],
    cfg: SimConfig,
    tf: str = "15m",
    symbol: str = "",
) -> dict:
    discover()
    strategy = get(strategy_name, strategy_version)(params)
    return simulate_with(strategy, candles, cfg, tf, symbol)


def simulate_with(
    strategy, candles: list[dict], cfg: SimConfig, tf: str = "15m", symbol: str = ""
) -> dict:
    """Như `simulate` nhưng nhận sẵn instance strategy (test / nhiều cấu hình)."""
    if len(candles) < 5:
        raise ValueError("không đủ dữ liệu để backtest")
    tf_ms = TF_MS.get(tf, 60_000)
    sim = _Sim(symbol, cfg, tf_ms)
    method = cfg.sizing.get("method", "risk_pct")
    value = float(cfg.sizing.get("value") or 0)
    equity: list[tuple[int, float]] = []
    W = max(1, cfg.window)

    for i, c in enumerate(candles):
        ts = c["ts"]
        sim.new_day(ts)
        # 1) trong nến: SL/TP/limit/thanh lý theo đường giá
        if sim.eng.position or sim.eng.pending:
            for k, px in enumerate(_path(c)):
                # chỉ tick MỞ CỬA mới có thể nhảy qua SL (gap); trong nến giá chạy liên tục
                # qua các mức → SL khớp đúng tại SL (+ trượt giá).
                sim.eng.gap_fill = k == 0
                sim.apply(sim.eng.on_price(px), ts)
                sim.track(px)
        close = c["close"]
        close_ts = ts + tf_ms  # tín hiệu khớp khi nến đóng
        # 2) nến đóng → strategy
        ctx = Context(
            symbol=symbol, price=close, candles=candles[max(0, i - W + 1): i + 1],
            position=sim.eng.position,
        )
        for sig in strategy.on_candle(ctx):
            if sig.action not in ("BUY", "SELL"):
                sim.apply(sim.eng.submit(sig, close), close_ts, sig)
                continue
            pos = sim.eng.position
            desired = "LONG" if sig.action == "BUY" else "SHORT"
            if pos and pos.side == desired:
                continue
            why = sim.blocked(close_ts, close)
            if why:
                sim.reject(why)
                continue
            entry = sig.price if sig.order_type == "LIMIT" and sig.price else close
            try:
                qty, _, notes = size_order(
                    method=method, value=value, side=desired, price=entry, sl=sig.sl,
                    state=sim.state(close), lim=sim.lim, fallback_qty=sig.size,
                    freed_margin=sim.eng.margin() if pos else 0.0,
                    freed_risk=position_risk(pos.side, pos.qty, pos.entry_price, pos.sl)
                    if pos else 0.0,
                )
            except RiskReject as e:
                sim.reject(str(e))
                continue
            for n in notes:
                sim.capped[n] = sim.capped.get(n, 0) + 1
            sim.apply(sim.eng.submit(replace(sig, size=qty), close), close_ts, sig)
        eq = sim.balance + sim.unrealized(close)
        sim.peak = max(sim.peak, eq)
        equity.append((close_ts, eq))
        if sim.liquidated:
            break

    # đóng vị thế còn mở ở giá cuối để số liệu đủ (đánh dấu END)
    last = candles[min(len(candles) - 1, len(equity) - 1)]
    if sim.eng.position:
        sim.apply(sim.eng.force_close(last["close"], "END"), last["ts"] + tf_ms)
        equity[-1] = (equity[-1][0], sim.balance)

    return {**_stats(sim, equity, cfg, candles), "trades": sim.trades}


def _stats(sim: _Sim, equity: list[tuple[int, float]], cfg: SimConfig, candles) -> dict:
    cap = cfg.capital
    vals = [v for _, v in equity]
    final = vals[-1] if vals else cap
    peak, max_dd, dd_start, longest, cur_start = cap, 0.0, None, 0, equity[0][0]
    for ts, v in equity:
        if v >= peak:
            peak = v
            if dd_start is not None:
                longest = max(longest, ts - dd_start)
                dd_start = None
        else:
            dd_start = dd_start or ts
            max_dd = max(max_dd, (peak - v) / peak * 100 if peak else 0)
    if dd_start is not None:
        longest = max(longest, equity[-1][0] - dd_start)
    span_days = max(1e-9, (equity[-1][0] - cur_start) / DAY_MS)
    cagr = ((final / cap) ** (365 / span_days) - 1) * 100 if final > 0 and span_days >= 7 else None

    # lợi nhuận theo ngày (Sharpe) + theo tháng
    daily: dict[int, float] = {}
    monthly: dict[str, list[float]] = {}
    for ts, v in equity:
        daily[ts // DAY_MS] = v
        k = datetime.fromtimestamp(ts / 1000, tz=UTC).strftime("%Y-%m")
        monthly.setdefault(k, [v, v])[1] = v
    dv = list(daily.values())
    rets = [(b / a - 1) for a, b in zip(dv, dv[1:], strict=False) if a > 0]
    sharpe = None
    if len(rets) > 2:
        mu = sum(rets) / len(rets)
        sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1))
        sharpe = mu / sd * math.sqrt(365) if sd > 0 else None
    months = []
    prev = cap
    for k, (_, end) in monthly.items():
        months.append([k, (end / prev - 1) * 100 if prev else 0.0])
        prev = end

    t = sim.trades
    wins = [x for x in t if x["pnl"] > 0]
    losses = [x for x in t if x["pnl"] <= 0]
    gross_win = sum(x["pnl"] for x in wins)
    gross_loss = -sum(x["pnl"] for x in losses)
    rs = [x["r"] for x in t if x["r"] is not None]
    streak = worst_streak = 0
    for x in t:
        streak = streak + 1 if x["pnl"] <= 0 else 0
        worst_streak = max(worst_streak, streak)
    step = max(1, len(equity) // 1500)
    curve = [[ts, round(v, 4)] for ts, v in equity[::step]]
    if curve and curve[-1][0] != equity[-1][0]:
        curve.append([equity[-1][0], round(equity[-1][1], 4)])

    return {
        "engine": "ACCOUNT",
        "capital": cap,
        "final_equity": round(final, 4),
        "pnl_pct": round((final / cap - 1) * 100, 4),
        "cagr_pct": round(cagr, 2) if cagr is not None else None,
        "max_dd": round(max_dd, 4),
        "longest_dd_days": round(longest / DAY_MS, 1),
        "calmar": round(cagr / max_dd, 2) if cagr is not None and max_dd > 0 else None,
        "sharpe": round(sharpe, 3) if sharpe is not None else None,
        "n_trades": len(t),
        "winrate": round(len(wins) / len(t) * 100, 2) if t else 0.0,
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
        "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
        "best_r": round(max(rs), 2) if rs else None,
        "worst_r": round(min(rs), 2) if rs else None,
        "max_loss_streak": worst_streak,
        "total_fees": round(sim.fees, 4),
        "fees_pct_of_capital": round(sim.fees / cap * 100, 3),
        "day_halts": sim.n_day_halts,
        "dd_halt_ts": sim.dd_halt_ts,
        "liquidated": sim.liquidated,
        "rejects": sim.rejects,
        "capped": sim.capped,
        "avg_notional_pct": round(
            sum(x["notional"] / x["equity_at_entry"] for x in t) / len(t) * 100, 1
        ) if t else None,
        "monthly": [[k, round(v, 3)] for k, v in months],
        "positive_months": sum(1 for _, v in months if v > 0),
        "from_ts": candles[0]["ts"],
        "to_ts": candles[-1]["ts"],
        "equity_curve": curve,
    }
