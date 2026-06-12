"""Param validation + strategy versioning (registry)."""

import pytest

from app.strategy.params import ParamError, validate_params
from app.strategy.registry import all_strategies, discover, get

SCHEMA = {
    "fast": {"type": "int", "min": 2, "max": 100, "default": 9},
    "size": {"type": "float", "min": 0.0, "default": 0.001},
}


def test_fills_defaults():
    out = validate_params(SCHEMA, {})
    assert out["fast"] == 9
    assert out["size"] == 0.001


def test_coerces_type():
    out = validate_params(SCHEMA, {"fast": "12"})
    assert out["fast"] == 12
    assert isinstance(out["fast"], int)


def test_rejects_below_min():
    with pytest.raises(ParamError):
        validate_params(SCHEMA, {"fast": 1})


def test_rejects_above_max():
    with pytest.raises(ParamError):
        validate_params(SCHEMA, {"fast": 999})


def test_rejects_bad_type():
    with pytest.raises(ParamError):
        validate_params(SCHEMA, {"fast": "abc"})


def test_keeps_extra_keys():
    out = validate_params(SCHEMA, {"custom": 5})
    assert out["custom"] == 5


def test_two_versions_of_ema_cross_registered():
    discover()
    versions = {c.version for c in all_strategies() if c.name == "ema_cross"}
    assert {"1", "2"} <= versions
    assert get("ema_cross", "2").default_params.get("gap_pct") == 0.1


def test_v2_gap_filter_blocks_tiny_cross():
    from app.strategy.base import Context
    from app.strategy.strategies.ema_cross import EmaCrossV2

    strat = EmaCrossV2({"fast": 3, "slow": 6, "size": 1, "gap_pct": 50})  # gap 50% rất khó đạt
    candles, sigs = [], []
    for c in [10, 10, 10, 10, 9, 8, 7, 8, 9, 10, 11, 12, 13, 14, 15]:
        candles.append({"close": c})
        sigs += strat.on_candle(Context("X", c, list(candles), None))
    assert sigs == []  # gap quá lớn → không vào lệnh
