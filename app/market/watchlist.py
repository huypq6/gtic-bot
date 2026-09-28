"""Watchlist — list of watched pairs (DB), seeded from default_symbols when empty."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.market.models import WatchSymbol


async def get_watchlist(session: AsyncSession) -> list[str]:
    rows = (
        await session.execute(select(WatchSymbol).order_by(WatchSymbol.created_at))
    ).scalars().all()
    return [r.symbol for r in rows]


async def ensure_seeded(session_factory: async_sessionmaker, defaults: list[str]) -> list[str]:
    """If the watchlist is empty → seed it with the defaults. Returns the current list."""
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
