"""Strategy registry — file-based. Each strategy class registers itself via @register.

The app scans the `strategies/` package, reads metadata (name, version, default_params) and
syncs it into the `strategy` table. The UI only edits params + picks a version; code is NOT
edited in the app.
"""

import importlib
import pkgutil

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.strategy.base import Strategy

_REGISTRY: dict[tuple[str, str], type[Strategy]] = {}


def register(cls: type[Strategy]) -> type[Strategy]:
    """Decorator: register a class by (name, version)."""
    _REGISTRY[(cls.name, cls.version)] = cls
    return cls


def discover() -> None:
    """Import every module in app/strategy/strategies/ so they self-register."""
    from app.strategy import strategies as pkg

    for m in pkgutil.iter_modules(pkg.__path__):
        importlib.import_module(f"app.strategy.strategies.{m.name}")


def all_strategies() -> list[type[Strategy]]:
    return list(_REGISTRY.values())


def get(name: str, version: str) -> type[Strategy]:
    return _REGISTRY[(name, version)]


async def sync_to_db(session: AsyncSession) -> int:
    """Upsert metadata of registered strategies into the `strategy` table."""
    from app.orders.models import StrategyModel

    rows = [
        {
            "name": c.name,
            "version": c.version,
            "default_params": c.default_params,
            "source_file": c.__module__,
        }
        for c in all_strategies()
    ]
    if not rows:
        return 0
    stmt = pg_insert(StrategyModel).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["name", "version"],
        set_={
            "default_params": stmt.excluded.default_params,
            "source_file": stmt.excluded.source_file,
        },
    )
    await session.execute(stmt)
    await session.commit()
    return len(rows)
