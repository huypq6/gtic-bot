"""Trade review: MFE/MAE, R, outcome, inferring the exit reason for legacy positions."""

import pytest

from app.orders.trades import excursion, infer_reason, summarize

BARS = [
    {"ts": 1, "high": 101, "low": 99},
    {"ts": 2, "high": 104, "low": 97},  # high 104 / low 97
    {"ts": 3, "high": 103, "low": 100},
]


def test_excursion_long():
    e = excursion("LONG", 100, BARS)
    assert (e.mfe, e.mae) == (4, 3)
    assert (e.mfe_ts, e.mae_ts) == (2, 2)


def test_excursion_short():
    e = excursion("SHORT", 100, BARS)
    assert (e.mfe, e.mae) == (3, 4)
    assert (e.mfe_price, e.mae_price) == (97, 104)


def test_excursion_never_negative_and_empty():
    e = excursion("LONG", 90, [{"ts": 1, "high": 95, "low": 91}])
    assert e.mae == 0  # price never went below entry
    assert excursion("LONG", 100, []).mfe is None  # missing candles → don't fabricate 0


def test_excursion_capped_at_exit_bar():
    # the exit candle runs past TP/SL after the position closed → that part is not counted
    e = excursion("LONG", 100, BARS, "TP", 102)
    assert (e.mfe, e.mfe_price) == (2, 102)
    e = excursion("SHORT", 100, BARS, "SL", 102)
    assert (e.mae, e.mae_price) == (2, 102)
    assert excursion("LONG", 100, BARS, "SIGNAL", 102).mfe == 4  # signal exit: unchanged


def test_summarize_win_in_r():
    s = summarize(
        side="LONG", qty=2, entry=100, exit_price=104, pnl=8, risk_sl=98,
        exc=excursion("LONG", 100, BARS),
    )
    assert s["result"] == "WIN"
    assert s["r"] == pytest.approx(2.0)  # +4/unit ÷ risk 2
    assert s["pnl_pct"] == pytest.approx(4.0)
    assert s["mfe_r"] == pytest.approx(2.0)
    assert s["mae_r"] == pytest.approx(1.5)
    assert s["risk_amount"] == pytest.approx(4.0)


def test_summarize_open_uses_mark():
    s = summarize(
        side="SHORT", qty=1, entry=100, exit_price=None, pnl=None, risk_sl=101,
        exc=excursion("SHORT", 100, BARS), mark=99,
    )
    assert s["result"] == "OPEN"
    assert s["pnl"] == pytest.approx(1.0)
    assert s["r"] == pytest.approx(1.0)


def test_summarize_loss_and_no_sl():
    s = summarize(
        side="LONG", qty=1, entry=100, exit_price=97, pnl=-3, risk_sl=None,
        exc=excursion("LONG", 100, BARS),
    )
    assert s["result"] == "LOSS"
    assert s["r"] is None and s["mfe_r"] is None


def test_infer_reason():
    assert infer_reason(83569.85957720544, 83569.85957720544, 82766.28) == "SL"
    assert infer_reason(0.09519, 0.0934, 0.09519) == "TP"
    assert infer_reason(100.5, 99, 102) == "SIGNAL"
    assert infer_reason(None, 99, 102) is None
