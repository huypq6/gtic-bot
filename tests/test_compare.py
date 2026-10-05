"""Cross-mode comparison (docs/08): grouping, R, pairing, slippage sign, version isolation."""

import pytest

from app.orders.compare import compare, pair_trades, slip_bps, split_strategy, trade_r

M = 60_000
TF = {"15m": 15 * M}


def tr(mode, opened_min, *, side="LONG", entry=100.0, exit=110.0, sl=95.0, qty=1.0,
       strategy="ict_po3 v4", symbol="SUIUSDT", tf="15m", fee=0.1, bot=1):
    sign = 1 if side == "LONG" else -1
    return {
        "mode": mode, "strategy": strategy, "symbol": symbol, "tf": tf, "side": side,
        "qty": qty, "entry": entry, "exit": exit, "init_sl": sl, "fee": fee,
        "pnl": sign * (exit - entry) * qty, "opened_ms": opened_min * M, "bot_ref": bot,
    }


def test_split_strategy():
    assert split_strategy("ict_po3 v4") == ("ict_po3", "4")
    assert split_strategy("donchian v2 v3") == ("donchian v2", "3")
    assert split_strategy("custom") == ("custom", "")
    assert split_strategy(None) == ("", "")


def test_trade_r():
    assert trade_r(tr("PAPER", 0)) == pytest.approx(2.0)  # +10 / risk 5
    assert trade_r(tr("PAPER", 0, side="SHORT", entry=100, exit=95, sl=105)) == pytest.approx(1.0)
    assert trade_r({**tr("PAPER", 0), "init_sl": None}) is None


def test_pairing_window_side_and_one_to_one():
    a = [tr("LIVE", 0), tr("LIVE", 100), tr("LIVE", 200, side="SHORT", exit=90, sl=105)]
    b = [tr("PAPER", 1), tr("PAPER", 2), tr("PAPER", 200)]  # 200 is LONG → side mismatch
    p = pair_trades(a, b, 15 * M)
    assert len(p.pairs) == 1
    assert p.pairs[0][1]["opened_ms"] == 1 * M  # nearest in time wins
    assert len(p.only_a) == 2 and len(p.only_b) == 2


def test_slippage_sign():
    # LONG entry: paying more is adverse; LONG exit: receiving less is adverse
    assert slip_bps("LONG", 100.1, 100.0, entry=True) == pytest.approx(10)
    assert slip_bps("LONG", 109.9, 110.0, entry=False) == pytest.approx(9.0909, rel=1e-3)
    # SHORT entry: selling lower is adverse; SHORT exit (buy back): paying more is adverse
    assert slip_bps("SHORT", 99.9, 100.0, entry=True) == pytest.approx(10)
    assert slip_bps("SHORT", 95.1, 95.0, entry=False) == pytest.approx(10.526, rel=1e-3)


def test_compare_groups_versions_and_divergence():
    trades = [
        tr("LIVE", 0, entry=100.1, exit=109.9),
        tr("LIVE", 300, exit=95),  # SL, no paper twin → only_a
        tr("PAPER", 0),
        tr("PAPER", 1000, strategy="ict_po3 v5", bot=2),  # candidate: other version
        tr("MANUAL-ish", 0, strategy=None),  # manual trade → skipped
    ]
    [g] = compare(trades, TF)
    assert (g["strategy"], g["symbol"], g["tf"]) == ("ict_po3", "SUIUSDT", "15m")
    assert [(r["mode"], r["version"], r["trades"]) for r in g["rows"]] == [
        ("LIVE", "4", 2), ("PAPER", "4", 1), ("PAPER", "5", 1),
    ]
    live = g["rows"][0]
    assert live["wins"] == 1 and live["win_rate"] == 50
    # divergence only between the same version (v4), v5 not paired with anything
    [d] = g["divergence"]
    assert (d["a"], d["b"], d["version"]) == ("LIVE", "PAPER", "4")
    assert (d["paired"], d["only_a"], d["only_b"]) == (1, 1, 0)
    assert d["entry_slip_bps"] == pytest.approx(10)
    assert d["r_diff"] < 0  # live did worse than paper on the paired trade
