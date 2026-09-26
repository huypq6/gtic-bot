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

# ---- ensure_history: chỉ tải phần thiếu ----
class RangeSession:
    """Giả DB trả (min_ts, max_ts, count) cho truy vấn phủ dữ liệu."""

    def __init__(self, first, last, n):
        self.row = (first, last, n)

    async def execute(self, q):
        row = self.row

        class R:
            def one(self):
                return row

        return R()


async def _ensure(monkeypatch, first, last, n, start):
    calls = []

    async def fake_sync(session, symbol, tf, start_str, end_str=None):
        calls.append(start_str)
        return 0

    monkeypatch.setattr(store, "sync_historical", fake_sync)
    await store.ensure_history(RangeSession(first, last, n), "X", "15m", start)
    return calls


async def test_ensure_history_incremental_when_covered(monkeypatch):
    from datetime import UTC, datetime, timedelta

    start = datetime(2026, 1, 1, tzinfo=UTC)
    last = start + timedelta(days=10)
    calls = await _ensure(monkeypatch, start, last, 10 * 96 + 1, start)
    assert calls == [int(last.timestamp() * 1000)]  # chỉ từ nến cuối


async def test_ensure_history_full_when_gappy_or_missing(monkeypatch):
    from datetime import UTC, datetime, timedelta

    start = datetime(2026, 1, 1, tzinfo=UTC)
    full = int(start.timestamp() * 1000)
    last = start + timedelta(days=10)
    assert await _ensure(monkeypatch, start, last, 500, start) == [full]  # thủng
    assert await _ensure(monkeypatch, start + timedelta(days=2), last, 800, start) == [full]
    assert await _ensure(monkeypatch, None, None, 0, start) == [full]  # chưa có gì
