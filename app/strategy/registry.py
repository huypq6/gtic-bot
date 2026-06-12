"""Strategy registry — file-based. Mỗi class strategy đăng ký qua @register.

App quét package `strategies/`, đọc metadata (name, version, default_params) và
sync vào bảng `strategy`. UI chỉ chỉnh params + chọn version, KHÔNG sửa code trong app.
"""

import importlib
import pkgutil

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.strategy.base import Strategy

_REGISTRY: dict[tuple[str, str], type[Strategy]] = {}


def register(cls: type[Strategy]) -> type[Strategy]:
    """Decorator: đăng ký class theo (name, version)."""
    _REGISTRY[(cls.name, cls.version)] = cls
    return cls


def discover() -> None:
    """Import mọi module trong app/strategy/strategies/ để chúng tự đăng ký."""
    from app.strategy import strategies as pkg

    for m in pkgutil.iter_modules(pkg.__path__):
        importlib.import_module(f"app.strategy.strategies.{m.name}")


def all_strategies() -> list[type[Strategy]]:
    return list(_REGISTRY.values())


def get(name: str, version: str) -> type[Strategy]:
    return _REGISTRY[(name, version)]


async def sync_to_db(session: AsyncSession) -> int:
    """Upsert metadata các strategy đã đăng ký vào bảng `strategy`."""
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
