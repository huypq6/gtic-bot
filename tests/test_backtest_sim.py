"""Account-simulation backtest: in-candle SL, equity-based sizing, fees, compounding, guardrails."""

import pytest

from app.backtest.sim import SimConfig, simulate_with
from app.strategy.base import Signal, Strategy

T = 900_000  # 15m


def bar(i, o, h, lo, c):
    return {"ts": i * T, "open": o, "high": h, "low": lo, "close": c, "volume": 1}


class Script(Strategy):
    """Emit signals from a script {candle index: Signal}."""

    name, version = "script", "1"

    def __init__(self, plan):
        super().__init__({})
        self.plan, self.i = plan, -1

    def on_candle(self, ctx):
        self.i += 1
        s = self.plan.get(self.i)
        return [s] if s else []


FLAT = [bar(i, 100, 100.5, 99.5, 100) for i in range(10)]
CFG0 = SimConfig(capital=1000, taker_fee=0, maker_fee=0, slippage_bps=0)


def test_sl_hit_inside_candle_loses_exactly_risk():
    candles = FLAT[:3] + [bar(3, 100, 100.2, 97, 99.5)] + FLAT[4:]  # wick down touches SL 98
    r = simulate_with(Script({1: Signal("BUY", "X", sl=98)}), candles, CFG0)
    t = r["trades"][0]
    assert t["reason"] == "SL" and t["exit"] == pytest.approx(98)
    assert t["qty"] == pytest.approx(5)  # 1% × 1000 / 2
    assert t["pnl"] == pytest.approx(-10) and t["r"] == pytest.approx(-1)
    assert r["final_equity"] == pytest.approx(990)


def test_gap_through_sl_fills_worse():
    candles = FLAT[:3] + [bar(3, 96, 96.5, 95, 96)] + FLAT[4:]  # already opens below SL
    r = simulate_with(Script({1: Signal("BUY", "X", sl=98)}), candles, CFG0)
    assert r["trades"][0]["exit"] == pytest.approx(96)
    assert r["trades"][0]["r"] == pytest.approx(-2)


def test_tp_and_fees_slippage():
    cfg = SimConfig(capital=1000, taker_fee=0.0005, slippage_bps=10)
    candles = FLAT[:3] + [bar(3, 100, 104.5, 99.8, 104)] + FLAT[4:]
    r = simulate_with(Script({1: Signal("BUY", "X", sl=98, tp=104)}), candles, cfg)
    t = r["trades"][0]
    assert t["reason"] == "TP"
    assert t["entry"] == pytest.approx(100.1)  # slippage on entry
    assert t["exit"] == pytest.approx(104 * 0.999)  # slippage on exit
    assert t["fee"] == pytest.approx(0.0005 * t["qty"] * (t["entry"] + t["exit"]))
    assert r["final_equity"] == pytest.approx(1000 + t["pnl"])
    assert r["total_fees"] == pytest.approx(t["fee"], abs=1e-4)


def test_compounding_sizes_follow_equity():
    # 2 consecutive winning trades: trade 2 is bigger because equity grew
    c = [bar(i, 100, 100.5, 99.5, 100) for i in range(12)]
    c[3] = bar(3, 100, 104.5, 99.8, 104)
    for i in (4, 5, 6):
        c[i] = bar(i, 104, 104, 104, 104)
    c[7] = bar(7, 104, 108.5, 103.9, 108)
    plan = {1: Signal("BUY", "X", sl=98, tp=104), 5: Signal("BUY", "X", sl=102, tp=108)}
    r = simulate_with(Script(plan), c, CFG0)
    a, b = r["trades"]
    assert a["r"] == pytest.approx(2) and b["r"] == pytest.approx(2)
    assert b["pnl"] > a["pnl"]  # 1% of 1020 > 1% of 1000
    assert r["final_equity"] == pytest.approx(1000 * 1.02 * 1.02)


def test_daily_loss_halt_blocks_rest_of_day():
    cfg = SimConfig(capital=1000, taker_fee=0, slippage_bps=0, daily_loss_pct=1.5,
                    sizing={"method": "risk_pct", "value": 1})
    c = [bar(i, 100, 100.5, 99.5, 100) for i in range(12)]
    c[3] = bar(3, 100, 100, 97, 98)  # SL 1 (−1%)
    c[5] = bar(5, 100, 100, 97, 98)  # SL 2 (−1%) → −2% today
    plan = {1: Signal("BUY", "X", sl=98), 4: Signal("BUY", "X", sl=98),
            7: Signal("BUY", "X", sl=98)}
    r = simulate_with(Script(plan), c, cfg)
    assert len(r["trades"]) == 2  # 3rd trade is blocked
    assert r["day_halts"] == 1 and r["rejects"]


def test_no_sl_with_risk_sizing_is_rejected():
    r = simulate_with(Script({1: Signal("BUY", "X")}), FLAT, CFG0)
    assert r["n_trades"] == 0 and r["rejects"] == {"missing SL": 1}


def test_open_position_closed_at_end():
    r = simulate_with(Script({1: Signal("SELL", "X", sl=103)}), FLAT, CFG0)
    assert r["trades"][0]["reason"] == "END"
