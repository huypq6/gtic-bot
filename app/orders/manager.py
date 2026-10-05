"""OrderManager — the single entry point for every order action (bot + manual).

Traceability NFR: write `audit_log` BEFORE acting (executor/exchange). `execute()` guarantees
the order: audit (commit) → only then run `do`. If `do` fails, the audit row remains (committed).
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.orders.models import AuditLog

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def write_audit(
        self,
        *,
        source: str,
        action: str,
        mode: str | None = None,
        bot_id: int | None = None,
        symbol: str | None = None,
        detail: dict | None = None,
    ) -> None:
        async with self._sf() as s:
            s.add(
                AuditLog(
                    source=source, action=action, mode=mode,
                    bot_id=bot_id, symbol=symbol, detail=detail,
                )
            )
            await s.commit()

    async def execute(
        self,
        *,
        source: str,
        action: str,
        do: Callable[[], Awaitable[Any]],
        mode: str | None = None,
        bot_id: int | None = None,
        symbol: str | None = None,
        detail: dict | None = None,
    ) -> Any:
        """Write the audit FIRST, then run `do`. Returns the result of `do`."""
        await self.write_audit(
            source=source, action=action, mode=mode,
            bot_id=bot_id, symbol=symbol, detail=detail,
        )
        return await do()

    async def list_audit(self, limit: int = 100, mode: str | None = None) -> list[dict]:
        q = select(AuditLog).order_by(AuditLog.id.desc())
        if mode:
            q = q.where(AuditLog.mode == mode)
        async with self._sf() as s:
            rows = (await s.execute(q.limit(limit))).scalars().all()
        return [
            {
                "id": r.id, "ts": r.ts.isoformat() if r.ts else None, "source": r.source,
                "mode": r.mode, "bot_id": r.bot_id, "symbol": r.symbol,
                "action": r.action, "detail": r.detail,
            }
            for r in rows
        ]
