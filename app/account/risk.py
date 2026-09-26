"""Quản lý vốn thuần (không DB, không async) — tính khối lượng + rào chắn rủi ro.

Strategy KHÔNG biết vốn: chỉ trả Signal (chiều, SL, TP). Lớp này quyết định khối lượng
theo phương pháp của bot + trạng thái tài khoản, rồi co lại cho vừa các trần rủi ro/ký quỹ.
"""

from dataclasses import dataclass

MIN_NOTIONAL = 5.0  # Binance USDT-M: giá trị lệnh tối thiểu ~5 USDT

SIZING_METHODS = {
    "risk_pct": "% vốn chấp nhận mất mỗi lệnh (chạm SL)",
    "risk_usdt": "USDT chấp nhận mất mỗi lệnh (chạm SL)",
    "notional_pct": "Giá trị lệnh = % vốn",
    "notional_usdt": "Giá trị lệnh cố định (USDT)",
    "fixed_qty": "Số coin cố định (param size của strategy)",
}


class RiskReject(Exception):
    """Lệnh bị chặn — message là lý do (hiển thị + audit)."""


@dataclass
class AccountState:
    balance: float  # số dư ví
    equity: float  # ví + lãi/lỗ tạm
    used_margin: float
    available: float  # equity − ký quỹ đang dùng
    open_risk: float  # tổng USDT sẽ mất nếu mọi lệnh mở chạm SL
    n_open: int
    daily_pnl: float  # hôm nay (UTC): đã chốt + tạm tính
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
    """USDT mất nếu chạm SL (0 nếu SL đã dời qua điểm hòa vốn). Không SL → cả giá trị lệnh."""
    if sl is None:
        return qty * entry
    loss = (entry - sl) if side == "LONG" else (sl - entry)
    return max(0.0, loss * qty)


def check_halt(state: AccountState, lim: Limits) -> str | None:
    """Rào chắn cấp tài khoản — trả lý do nếu phải DỪNG vào lệnh mới."""
    if lim.max_dd_pct is not None and state.dd_pct >= lim.max_dd_pct:
        return f"sụt vốn {state.dd_pct:.1f}% từ đỉnh ≥ giới hạn {lim.max_dd_pct:g}%"
    if lim.daily_loss_pct is not None and -state.daily_pnl_pct >= lim.daily_loss_pct:
        return f"lỗ hôm nay {state.daily_pnl_pct:.1f}% chạm giới hạn {lim.daily_loss_pct:g}%"
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
    freed_margin: float = 0.0,  # ký quỹ được trả lại nếu lệnh này đảo chiều vị thế cũ
    freed_risk: float = 0.0,
) -> tuple[float, float, list[str]]:
    """→ (qty, risk_usdt, ghi chú co lệnh). Raise RiskReject nếu không vào được."""
    if price <= 0:
        raise RiskReject("chưa có giá")
    eq = state.equity
    stop = abs(price - sl) if sl is not None else None
    if method in ("risk_pct", "risk_usdt"):
        if not stop:
            raise RiskReject("phương pháp theo rủi ro cần lệnh có SL")
        risk_target = eq * value / 100 if method == "risk_pct" else value
        qty = risk_target / stop
    elif method == "notional_pct":
        qty = eq * value / 100 / price
    elif method == "notional_usdt":
        qty = value / price
    elif method == "fixed_qty":
        qty = value or fallback_qty
    else:
        raise RiskReject(f"phương pháp khối lượng '{method}' không hợp lệ")
    if qty <= 0:
        raise RiskReject("khối lượng = 0")

    notes: list[str] = []
    unit_risk = stop if stop else price  # không SL → coi cả giá trị lệnh là rủi ro

    # 1) trần rủi ro 1 lệnh
    if lim.max_risk_pct is not None:
        cap = eq * lim.max_risk_pct / 100 / unit_risk
        if qty > cap:
            qty = cap
            notes.append(f"co theo trần rủi ro/lệnh {lim.max_risk_pct:g}%")
    # 2) tổng rủi ro đang mở
    if lim.max_open_risk_pct is not None:
        room = eq * lim.max_open_risk_pct / 100 - (state.open_risk - freed_risk)
        if room <= 0:
            raise RiskReject(
                f"tổng rủi ro đang mở đã chạm {lim.max_open_risk_pct:g}% vốn"
            )
        if qty * unit_risk > room:
            qty = room / unit_risk
            notes.append(f"co theo tổng rủi ro mở {lim.max_open_risk_pct:g}%")
    # 3) ký quỹ khả dụng (margin + phí vào)
    per_unit_cost = price / lim.leverage + price * lim.taker_fee
    avail = state.available + freed_margin
    if avail <= 0:
        raise RiskReject("không còn số dư khả dụng")
    if qty * per_unit_cost > avail:
        qty = avail / per_unit_cost
        notes.append("co theo số dư khả dụng")
    if qty * price < MIN_NOTIONAL:
        raise RiskReject(
            f"giá trị lệnh {qty * price:.2f} USDT < tối thiểu {MIN_NOTIONAL:g} USDT"
        )
    return qty, qty * unit_risk, notes
