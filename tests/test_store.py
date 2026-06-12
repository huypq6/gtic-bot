"""store.upsert_klines — phải chia batch để không vượt 32767 bind params của asyncpg."""

from app.market import store
from app.market.store import upsert_klines


class FakeSession:
    def __init__(self):
        self.execute_calls = 0
        self.commits = 0

    async def execute(self, stmt):
        self.execute_calls += 1

    async def commit(self):
        self.commits += 1


def _rows(n: int) -> list[dict]:
    base = {"symbol": "BTCUSDT", "tf": "1m", "open": 1, "high": 1, "low": 1, "close": 1, "vol": 1}
    return [{**base, "ts": i} for i in range(n)]


async def test_empty_is_noop():
    s = FakeSession()
    assert await upsert_klines(s, []) == 0
    assert s.execute_calls == 0


async def test_single_batch():
    s = FakeSession()
    n = store._UPSERT_BATCH
    assert await upsert_klines(s, _rows(n)) == n
    assert s.execute_calls == 1
    assert s.commits == 1


async def test_multiple_batches_under_param_limit():
    s = FakeSession()
    n = store._UPSERT_BATCH * 2 + 1  # mô phỏng 3 ngày 1m klines
    assert await upsert_klines(s, _rows(n)) == n
    assert s.execute_calls == 3  # 3 batch
    # mỗi batch ≤ _UPSERT_BATCH dòng × 8 cột < 32767 params
    assert store._UPSERT_BATCH * 8 < 32767