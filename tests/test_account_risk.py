"""Quản lý vốn thuần: tính khối lượng theo phương pháp + co theo trần + rào chắn."""

import pytest

from app.account.risk import (
    AccountState,
    Limits,
    RiskReject,
    check_halt,
    position_risk,
    size_order,
)


def st(equity=1000.0, **kw) -> AccountState:
    base = dict(
        balance=equity, equity=equity, used_margin=0.0, available=equity, open_risk=0.0,
        n_open=0, daily_pnl=0.0, day_start_balance=equity, peak_equity=equity,
    )
    return AccountState(**{**base, **kw})


def size(method, value, price=100.0, sl=98.0, state=None, lim=None, **kw):
    return size_order(
        method=method, value=value, side="LONG", price=price, sl=sl,
        state=state or st(), lim=lim or Limits(), **kw,
    )


def test_risk_pct_loses_exactly_pct_at_sl():
    qty, risk, notes = size("risk_pct", 1)  # 1% của 1000 = 10 USDT, SL cách 2
    assert qty == pytest.approx(5) and risk == pytest.approx(10) and not notes


def test_risk_usdt_and_notional_methods():
    assert size("risk_usdt", 20)[0] == pytest.approx(10)
    assert size("notional_usdt", 500)[0] == pytest.approx(5)
    assert size("notional_pct", 50)[0] == pytest.approx(5)  # 50% × 1000 / 100
    assert size("fixed_qty", 0, fallback_qty=0.3)[0] == pytest.approx(0.3)


def test_risk_method_needs_sl():
    with pytest.raises(RiskReject, match="SL"):
        size("risk_pct", 1, sl=None)


def test_cap_per_trade_risk():
    qty, risk, notes = size("risk_pct", 5, lim=Limits(max_risk_pct=2))
    assert risk == pytest.approx(20) and notes


def test_cap_total_open_risk_and_reject_when_full():
    lim = Limits(max_open_risk_pct=3)
    qty, risk, _ = size("risk_pct", 2, state=st(open_risk=20), lim=lim)
    assert risk == pytest.approx(10)  # còn chỗ 30 − 20
    with pytest.raises(RiskReject, match="tổng rủi ro"):
        size("risk_pct", 1, state=st(open_risk=30), lim=lim)
    # đảo chiều: rủi ro của vị thế cũ được trả lại
    assert size("risk_pct", 1, state=st(open_risk=30), lim=lim, freed_risk=10)[1] == 10


def test_cap_by_available_margin_with_leverage_and_fee():
    # SL rất sát → risk_pct đòi khối lượng lớn hơn số dư
    qty, _, notes = size("risk_pct", 1, sl=99.9, state=st(available=200),
                         lim=Limits(leverage=2, taker_fee=0.0005))
    assert qty * (100 / 2 + 100 * 0.0005) == pytest.approx(200)
    assert "khả dụng" in notes[-1]


def test_reject_no_balance_and_min_notional():
    with pytest.raises(RiskReject, match="khả dụng"):
        size("risk_pct", 1, state=st(available=0))
    with pytest.raises(RiskReject, match="tối thiểu"):
        size("notional_usdt", 3)


def test_position_risk():
    assert position_risk("LONG", 2, 100, 95) == 10
    assert position_risk("SHORT", 2, 100, 103) == 6
    assert position_risk("LONG", 2, 100, 101) == 0  # SL đã dời qua hòa vốn
    assert position_risk("LONG", 2, 100, None) == 200


def test_halt_rules():
    lim = Limits(daily_loss_pct=3, max_dd_pct=15)
    assert check_halt(st(), lim) is None
    assert "lỗ hôm nay" in check_halt(st(daily_pnl=-30), lim)
    assert "sụt vốn" in check_halt(st(equity=840, peak_equity=1000), lim)
