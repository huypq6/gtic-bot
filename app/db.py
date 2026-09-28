"""SQLAlchemy async engine + session factory.

Models (P2+) inherit from `Base`. The Timescale extension + hypertable are handled by
`db/init/01-extensions.sql` and Alembic migrations, not declared here.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base for all ORM models."""


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: 1 session/request."""
    async with async_session() as session:
        yield session
