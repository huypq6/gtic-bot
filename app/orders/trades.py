"""Review lệnh đã/đang chạy: kết quả, R, MFE/MAE — thuần (không DB) để test.

1 "trade" = 1 row `position`. MFE/MAE (biến động có lợi/bất lợi cực đại) tính từ
nến 1m lưu trong DB trong khoảng [mở, đóng] → xấp xỉ theo nến (không theo tick).
"""

import math
from dataclasses import dataclass


@dataclass
class Excursion:
    mfe: float | None  # giá chạy CÓ LỢI tối đa so với entry (≥ 0, đơn vị giá); None = thiếu nến
    mae: float | None  # giá chạy BẤT LỢI tối đa so với entry (≥ 0, đơn vị giá)
    mfe_price: float | None
    mae_price: float | None
    mfe_ts: int | None  # ms
    mae_ts: int | None


def excursion(
    side: str,
    entry: float,
    bars: list[dict],
    exit_reason: str | None = None,
    exit_price: float | None = None,
) -> Excursion:
    """`bars`: [{ts, high, low}] tăng dần trong thời gian giữ lệnh.

    Nến chứa lúc thoát có cả giá SAU khi đóng → thoát TP thì MFE không vượt TP,
    thoát SL thì MAE không vượt SL (lệnh đã đóng ngay khi chạm).
    """
    best = worst = None
    best_ts = worst_ts = None
    for b in bars:
        hi, lo = b["high"], b["low"]
        fav, adv = (hi, lo) if side == "LONG" else (lo, hi)
        if best is None or (fav > best if side == "LONG" else fav < best):
            best, best_ts = fav, b["ts"]
        if worst is None or (adv < worst if side == "LONG" else adv > worst):
            worst, worst_ts = adv, b["ts"]
    if best is None:
        return Excursion(None, None, None, None, None, None)
    sign = 1 if side == "LONG" else -1
    mfe, mae = max(0.0, sign * (best - entry)), max(0.0, sign * (entry - worst))
    if exit_price is not None:
        cap = abs(exit_price - entry)
        if exit_reason == "TP" and mfe > cap:
            mfe, best = cap, exit_price
        if exit_reason == "SL" and mae > cap:
            mae, worst = cap, exit_price
    return Excursion(
        mfe=mfe, mae=mae, mfe_price=best, mae_price=worst, mfe_ts=best_ts, mae_ts=worst_ts,
    )


def infer_reason(exit_price: float | None, sl: float | None, tp: float | None) -> str | None:
    """Vị thế cũ (trước khi lưu exit_reason): engine đóng SL/TP đúng tại giá SL/TP."""
    if exit_price is None:
        return None
    if sl is not None and math.isclose(exit_price, sl, rel_tol=1e-9):
        return "SL"
    if tp is not None and math.isclose(exit_price, tp, rel_tol=1e-9):
        return "TP"
    return "SIGNAL"


def summarize(
    *,
    side: str,
    qty: float,
    entry: float,
    exit_price: float | None,
    pnl: float | None,
    risk_sl: float | None,
    exc: Excursion,
    mark: float | None = None,
) -> dict:
    """Số liệu review: PnL tiền/%, R, kết quả, MFE/MAE theo % và R."""
    sign = 1 if side == "LONG" else -1
    notional = entry * qty
    px = exit_price if exit_price is not None else mark
    if pnl is None and px is not None:  # đang mở → PnL tạm tính
        pnl = sign * (px - entry) * qty
    risk = abs(entry - risk_sl) if risk_sl is not None else None
    risk = risk if risk else None  # SL = entry → không đo được R

    def pct(v: float | None) -> float | None:
        return v / entry * 100 if v is not None and entry else None

    def r(v: float | None) -> float | None:
        return v / risk if v is not None and risk else None

    if pnl is None or exit_price is None:
        result = "OPEN"
    elif abs(pnl) <= notional * 1e-6:
        result = "BE"
    else:
        result = "WIN" if pnl > 0 else "LOSS"
    per_unit = pnl / qty if pnl is not None and qty else None
    return {
        "result": result,
        "notional": notional,
        "pnl": pnl,
        "pnl_pct": pnl / notional * 100 if pnl is not None and notional else None,
        "risk_amount": risk * qty if risk else None,
        "r": r(per_unit),
        "mfe_pct": pct(exc.mfe),
        "mae_pct": pct(exc.mae),
        "mfe_r": r(exc.mfe),
        "mae_r": r(exc.mae),
        "mfe_pnl": exc.mfe * qty if exc.mfe is not None else None,
        "mae_pnl": -exc.mae * qty if exc.mae is not None else None,
        "mfe_price": exc.mfe_price,
        "mae_price": exc.mae_price,
        "mfe_ts": exc.mfe_ts,
        "mae_ts": exc.mae_ts,
    }
