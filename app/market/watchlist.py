"""Watchlist — danh sách cặp theo dõi (DB), seed từ default_symbols nếu rỗng."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.market.models import WatchSymbol


async def get_watchlist(session: AsyncSession) -> list[str]:
    rows = (
        await session.execute(select(WatchSymbol).order_by(WatchSymbol.created_at))
    ).scalars().all()
    return [r.symbol for r in rows]


async def ensure_seeded(session_factory: async_sessionmaker, defaults: list[str]) -> list[str]:
    """Nếu watchlist rỗng → seed bằng defaults. Trả về danh sách hiện tại."""
    async with session_factory() as s:
        current = await get_watchlist(s)
        if not current:
            for sym in defaults:
                s.add(WatchSymbol(symbol=sym.upper()))
            await s.commit()
            current = [d.upper() for d in defaults]
        return current


async def add_symbol(session: AsyncSession, symbol: str) -> None:
    if not await session.get(WatchSymbol, symbol):
        session.add(WatchSymbol(symbol=symbol))
        await session.commit()


async def remove_symbol(session: AsyncSession, symbol: str) -> None:
    await session.execute(delete(WatchSymbol).where(WatchSymbol.symbol == symbol))
    await session.commit()
