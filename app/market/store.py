"""Lưu/đọc kline trong Postgres + sync lịch sử từ Binance REST.

- `upsert_klines`: ghi (idempotent) các nến đã đóng.
- `get_klines`: đọc cho chart load ban đầu.
- `sync_historical`: tải lịch sử qua python-binance REST → upsert.
- `persist_closed_klines`: task nền, subscribe firehose bus, ghi nến `closed=True`.
"""

import logging
from datetime import UTC, datetime

from binance import AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.market.bus import EventBus
from app.market.models import Kline

logger = logging.getLogger(__name__)


def _row_from_payload(p: dict) -> dict:
    return {
        "symbol": p["symbol"],
        "tf": p["tf"],
        "ts": datetime.fromtimestamp(p["ts"] / 1000, tz=UTC),
        "open": p["open"],
        "high": p["high"],
        "low": p["low"],
        "close": p["close"],
        "volume": p["volume"],
    }


# asyncpg giới hạn 32767 bind params/query; 8 cột/dòng → batch an toàn ~4000 dòng.
_UPSERT_BATCH = 2000


async def upsert_klines(session: AsyncSession, rows: list[dict]) -> int:
    """Upsert theo PK (symbol, tf, ts), chia batch để không vượt giới hạn params."""
    if not rows:
        return 0
    for i in range(0, len(rows), _UPSERT_BATCH):
        chunk = rows[i : i + _UPSERT_BATCH]
        stmt = pg_insert(Kline).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "tf", "ts"],
            set_={c: stmt.excluded[c] for c in ("open", "high", "low", "close", "volume")},
        )
        await session.execute(stmt)
    await session.commit()
    return len(rows)


async def get_klines(
    session: AsyncSession,
    symbol: str,
    tf: str,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 1000,
) -> list[dict]:
    q = select(Kline).where(Kline.symbol == symbol, Kline.tf == tf)
    if start:
        q = q.where(Kline.ts >= start)
    if end:
        q = q.where(Kline.ts <= end)
    q = q.order_by(Kline.ts.desc()).limit(limit)
    rows = (await session.execute(q)).scalars().all()
    rows = list(reversed(rows))  # trả về theo thời gian tăng dần
    return [
        {
            "ts": int(k.ts.timestamp() * 1000),
            "open": float(k.open),
            "high": float(k.high),
            "low": float(k.low),
            "close": float(k.close),
            "volume": float(k.volume),
        }
        for k in rows
    ]


async def sync_historical(
    session: AsyncSession, symbol: str, tf: str, start_str: str | int,
    end_str: str | None = None,
) -> int:
    """Tải lịch sử từ Binance REST (public, không cần key) → upsert. start: chuỗi
    python-binance hiểu ("7 days ago UTC") hoặc ms (int)."""
    client = await AsyncClient.create()
    try:
        raw = await client.get_historical_klines(symbol, tf, start_str, end_str)
    finally:
        await client.close_connection()
    rows = [
        {
            "symbol": symbol,
            "tf": tf,
            "ts": datetime.fromtimestamp(r[0] / 1000, tz=UTC),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": float(r[5]),
        }
        for r in raw
    ]
    return await upsert_klines(session, rows)


_TF_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
          "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "1d": 86_400_000}


async def ensure_history(
    session: AsyncSession, symbol: str, tf: str, start: datetime
) -> int:
    """Đảm bảo DB có nến liền mạch từ `start` tới hiện tại — chỉ tải PHẦN THIẾU.

    DB đã phủ từ `start` và không thủng (đếm ≥ 99% số nến kỳ vọng) → chỉ tải từ nến
    cuối; ngược lại tải lại cả khoảng (vá lỗ). Tránh mỗi lần backtest 1 năm lại gọi
    Binance ~35 request.
    """
    from sqlalchemy import func

    tf_ms = _TF_MS.get(tf)
    q = select(func.min(Kline.ts), func.max(Kline.ts), func.count()).where(
        Kline.symbol == symbol, Kline.tf == tf, Kline.ts >= start
    )
    first, last, n = (await session.execute(q)).one()
    start_ms = int(start.timestamp() * 1000)
    if tf_ms and first is not None:
        f_ms, l_ms = int(first.timestamp() * 1000), int(last.timestamp() * 1000)
        expected = (l_ms - f_ms) // tf_ms + 1
        if f_ms - start_ms <= 2 * tf_ms and n >= 0.99 * expected:
            return await sync_historical(session, symbol, tf, l_ms)
    return await sync_historical(session, symbol, tf, start_ms)


async def persist_closed_klines(bus: EventBus, session_factory: async_sessionmaker) -> None:
    """Task nền: ghi mỗi nến đã đóng vào DB. Hủy qua CancelledError."""
    sub = bus.subscribe("*")
    while True:
        msg = await sub.get()
        if msg.get("type") != "kline" or not msg.get("closed"):
            continue
        try:
            async with session_factory() as session:
                await upsert_klines(session, [_row_from_payload(msg)])
        except Exception:  # noqa: BLE001 — không để persistence làm chết feed loop
            logger.exception("persist kline thất bại")
