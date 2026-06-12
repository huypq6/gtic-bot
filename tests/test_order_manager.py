"""OrderManager — NFR: audit_log ghi TRƯỚC khi tác động."""

import pytest

from app.orders.manager import OrderManager


class FakeSession:
    def __init__(self, log):
        self._log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def add(self, obj):
        self._log.append("audit")

    async def commit(self):
        pass


def make_sf(log):
    def sf():
        return FakeSession(log)

    return sf


async def test_audit_written_before_act():
    log: list[str] = []
    om = OrderManager(make_sf(log))

    async def do():
        log.append("act")

    await om.execute(source="MANUAL", action="CLOSE", do=do)
    assert log == ["audit", "act"]


async def test_audit_persists_even_if_act_fails():
    log: list[str] = []
    om = OrderManager(make_sf(log))

    async def do():
        log.append("act")
        raise RuntimeError("executor lỗi")

    with pytest.raises(RuntimeError):
        await om.execute(source="BOT", action="OPEN", do=do)
    # audit đã ghi trước khi act lỗi
    assert log == ["audit", "act"]
    assert log[0] == "audit"
