"""Rào chắn LIVE: ENABLE_LIVE + xác nhận; feed DOWN → auto-pause."""

import pytest

from app.config import Settings
from app.execution.live import make_live_executor


async def test_live_blocked_without_enable_flag():
    s = Settings(enable_live=False, binance_key="k", binance_secret="x")
    with pytest.raises(ValueError, match="ENABLE_LIVE"):
        await make_live_executor(1, "BTCUSDT", None, None, s)


async def test_live_blocked_without_keys():
    s = Settings(enable_live=True, binance_key="", binance_secret="")
    with pytest.raises(ValueError, match="BINANCE_KEY"):
        await make_live_executor(1, "BTCUSDT", None, None, s)


# ---- feed auto-pause ----
class FakeRunner:
    def __init__(self, bot_id, status="RUNNING"):
        self.bot_id = bot_id
        self.symbol = "BTCUSDT"
        self.mode = "PAPER"
        self.status = status


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt):
        pass

    async def commit(self):
        pass


class FakeOM:
    def __init__(self):
        self.audits = []

    async def write_audit(self, **kw):
        self.audits.append(kw)


async def test_pause_all_running_pauses_and_audits():
    from app.strategy.runner import BotManager

    om = FakeOM()
    mgr = BotManager(bus=None, session_factory=lambda: FakeSession(), order_manager=om)
    mgr._runners = {1: FakeRunner(1), 2: FakeRunner(2), 3: FakeRunner(3, status="PAUSED")}

    n = await mgr.pause_all_running("feed DOWN")
    assert n == 2  # chỉ 2 bot RUNNING bị pause
    assert mgr._runners[1].status == "PAUSED"
    assert mgr._runners[2].status == "PAUSED"
    assert mgr._runners[3].status == "PAUSED"  # vốn đã paused
    # audit SYSTEM/PAUSE cho 2 bot
    assert len(om.audits) == 2
    assert all(a["source"] == "SYSTEM" and a["action"] == "PAUSE" for a in om.audits)
