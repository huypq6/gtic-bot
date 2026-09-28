"""Pure money management (no DB, no async) — position sizing + risk guards.

Strategies do NOT know about capital: they only return a Signal (side, SL, TP). This layer decides
the size from the bot's sizing method + account state, then shrinks it to fit the risk/margin caps.
"""

from dataclasses import dataclass

MIN_NOTIONAL = 5.0  # Binance USDT-M: minimum order notional ~5 USDT

SIZING_METHODS = {
    "risk_pct": "% of equity risked per trade (if SL is hit)",
    "risk_usdt": "USDT risked per trade (if SL is hit)",
    "notional_pct": "Order notional = % of equity",
    "notional_usdt": "Fixed order notional (USDT)",
    "fixed_qty": "Fixed coin quantity (the strategy's size param)",
}


class RiskReject(Exception):
    """Order blocked — the message is the reason (displayed + audited)."""


@dataclass
class AccountState:
    balance: float  # wallet balance
    equity: float  # wallet + unrealized PnL
    used_margin: float
    available: float  # equity − margin in use
    open_risk: float  # total USDT lost if every open position hits its SL
    n_open: int
    daily_pnl: float  # today (UTC): realized + unrealized
    day_start_balance: float
    peak_equity: float

    @property
    def dd_pct(self) -> float:
        return (self.peak_equity - self.equity) / self.peak_equity * 100 if self.peak_equity else 0

    @property
    def daily_pnl_pct(self) -> float:
        base = self.day_start_balance or self.balance
        return self.daily_pnl / base * 100 if base else 0


@dataclass
class Limits:
    leverage: float = 1.0
    taker_fee: float = 0.0
    max_risk_pct: float | None = None
    max_open_risk_pct: float | None = None
    max_positions: int | None = None
    daily_loss_pct: float | None = None
    max_dd_pct: float | None = None


def position_risk(side: str, qty: float, entry: float, sl: float | None) -> float:
    """USDT lost if SL is hit (0 if SL has moved past breakeven). No SL → full notional."""
    if sl is None:
        return qty * entry
    loss = (entry - sl) if side == "LONG" else (sl - entry)
    return max(0.0, loss * qty)


def check_halt(state: AccountState, lim: Limits) -> str | None:
    """Account-level guard — returns the reason if new entries must be HALTED."""
    if lim.max_dd_pct is not None and state.dd_pct >= lim.max_dd_pct:
        return f"drawdown {state.dd_pct:.1f}% from peak ≥ limit {lim.max_dd_pct:g}%"
    if lim.daily_loss_pct is not None and -state.daily_pnl_pct >= lim.daily_loss_pct:
        return f"today's loss {state.daily_pnl_pct:.1f}% hit the limit {lim.daily_loss_pct:g}%"
    return None


def size_order(
    *,
    method: str,
    value: float,
    side: str,  # LONG | SHORT
    price: float,
    sl: float | None,
    state: AccountState,
    lim: Limits,
    fallback_qty: float = 0.0,
    freed_margin: float = 0.0,  # margin released if this order reverses the existing position
    freed_risk: float = 0.0,
) -> tuple[float, float, list[str]]:
    """→ (qty, risk_usdt, size-reduction notes). Raises RiskReject if the entry is not allowed."""
    if price <= 0:
        raise RiskReject("no price yet")
    eq = state.equity
    stop = abs(price - sl) if sl is not None else None
    if method in ("risk_pct", "risk_usdt"):
        if not stop:
            raise RiskReject("risk-based sizing requires an order with an SL")
        risk_target = eq * value / 100 if method == "risk_pct" else value
        qty = risk_target / stop
    elif method == "notional_pct":
        qty = eq * value / 100 / price
    elif method == "notional_usdt":
        qty = value / price
    elif method == "fixed_qty":
        qty = value or fallback_qty
    else:
        raise RiskReject(f"invalid sizing method '{method}'")
    if qty <= 0:
        raise RiskReject("quantity = 0")

    notes: list[str] = []
    unit_risk = stop if stop else price  # no SL → treat full notional as risk

    # 1) per-trade risk cap
    if lim.max_risk_pct is not None:
        cap = eq * lim.max_risk_pct / 100 / unit_risk
        if qty > cap:
            qty = cap
            notes.append(f"reduced to per-trade risk cap {lim.max_risk_pct:g}%")
    # 2) total open risk
    if lim.max_open_risk_pct is not None:
        room = eq * lim.max_open_risk_pct / 100 - (state.open_risk - freed_risk)
        if room <= 0:
            raise RiskReject(
                f"total open risk already at {lim.max_open_risk_pct:g}% of equity"
            )
        if qty * unit_risk > room:
            qty = room / unit_risk
            notes.append(f"reduced to total open risk cap {lim.max_open_risk_pct:g}%")
    # 3) available margin (margin + entry fee)
    per_unit_cost = price / lim.leverage + price * lim.taker_fee
    avail = state.available + freed_margin
    if avail <= 0:
        raise RiskReject("no available balance left")
    if qty * per_unit_cost > avail:
        cap = avail / per_unit_cost
        if cap < qty * 0.99:  # shrinking ≤ 1% (e.g. 100% equity + entry fee) isn't worth noting
            notes.append("reduced to available balance")
        qty = cap
    if qty * price < MIN_NOTIONAL:
        raise RiskReject(
            f"order notional {qty * price:.2f} USDT < minimum {MIN_NOTIONAL:g} USDT"
        )
    return qty, qty * unit_risk, notes
