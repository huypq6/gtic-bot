"""TA (vwap/ichimoku) + strategies ichimoku/vwap/grid."""

from app.strategy.base import Context, Position
from app.strategy.registry import all_strategies, discover
from app.strategy.strategies.grid import Grid
from app.strategy.strategies.ichimoku import Ichimoku
from app.strategy.strategies.vwap_cross import VwapCross
from app.strategy.ta import ichimoku, vwap


def candle(c, vol=1.0):
    return {"ts": 0, "open": c, "high": c + 0.5, "low": c - 0.5, "close": c, "volume": vol}


def replay(strat, closes, vols=None):
    out, bars = [], []
    for i, c in enumerate(closes):
        bars.append(candle(c, vols[i] if vols else 1.0))
        out.extend(strat.on_candle(Context("X", c, list(bars), None)))
    return [s.action for s in out]


# ---- TA ----
def test_vwap_basic():
    cs = [candle(10, 2), candle(20, 2)]  # typical = close±0 (h+l+c)/3 ≈ close
    v = vwap(cs, 2)
    assert v is not None and 9 < v < 21


def test_vwap_insufficient():
    assert vwap([candle(10)], 5) is None


def test_ichimoku_none_when_short():
    assert ichimoku([candle(10) for _ in range(10)]) is None


def test_ichimoku_struct_on_enough_data():
    cs = [candle(float(i)) for i in range(1, 120)]  # uptrend dài
    ich = ichimoku(cs, 9, 26, 52, 26)
    assert ich is not None
    assert ich["tenkan_now"] > ich["kijun_now"]  # uptrend: tenkan trên kijun
    assert "cloud_top" in ich and ich["cloud_top"] >= ich["cloud_bottom"]


# ---- ichimoku strategy ----
def test_ichimoku_buys_on_uptrend():
    s = Ichimoku({"conv": 5, "base": 10, "span_b": 20, "size": 1})
    closes = [20] * 30 + [19, 18, 17, 16, 15] + list(range(15, 60))  # dip rồi tăng mạnh
    assert "BUY" in replay(s, [float(c) for c in closes])


def test_ichimoku_quiet_when_short():
    s = Ichimoku()
    assert s.on_candle(Context("X", 10, [candle(10) for _ in range(20)], None)) == []


# ---- vwap strategy ----
def test_vwap_cross_up_buys():
    s = VwapCross({"period": 5, "size": 1})
    # giá đi ngang dưới rồi vọt lên trên VWAP
    closes = [10, 10, 10, 10, 10, 9.5, 9.5, 9.5, 12]
    assert "BUY" in replay(s, closes)


# ---- grid strategy (đọc ctx.position) ----
def test_grid_buys_below_lower_when_flat():
    s = Grid({"period": 5, "step_pct": 2, "size": 1})
    bars = [candle(c) for c in [100, 100, 100, 100, 100]]  # ref=100, lower=98
    sigs = s.on_candle(Context("X", 97.0, bars, None))
    assert [x.action for x in sigs] == ["BUY"]


def test_grid_closes_long_back_at_ref():
    s = Grid({"period": 5, "step_pct": 2, "size": 1})
    bars = [candle(c) for c in [100, 100, 100, 100, 100]]
    pos = Position(symbol="X", side="LONG", qty=1, entry_price=97)
    sigs = s.on_candle(Context("X", 100.0, bars, pos))  # giá về mốc → CLOSE
    assert [x.action for x in sigs] == ["CLOSE"]


def test_grid_flat_inside_band_no_signal():
    s = Grid({"period": 5, "step_pct": 2, "size": 1})
    bars = [candle(c) for c in [100, 100, 100, 100, 100]]
    assert s.on_candle(Context("X", 100.5, bars, None)) == []


# ---- registry ----
def test_all_three_registered():
    discover()
    names = {c.name for c in all_strategies()}
    assert {"ichimoku", "vwap", "grid"} <= names
