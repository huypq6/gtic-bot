"""Exchange connection check (docs/09) — is TESTNET / LIVE ready for bots to trade?"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.execution.clients import check_mode, exchange_client
from app.execution.preflight import _c, _err, overall, run_checks
from app.orders.models import Bot

router = APIRouter(prefix="/api")


@router.get("/exchange/check")
async def exchange_check(
    mode: str = "TESTNET", session: AsyncSession = Depends(get_session)
) -> dict:
    mode = mode.upper()
    if mode not in ("TESTNET", "LIVE"):
        raise HTTPException(400, "mode must be TESTNET or LIVE")
    endpoint = settings.binance_testnet_endpoint if mode == "TESTNET" else "live"
    try:
        check_mode(mode)  # keys present; LIVE: ENABLE_LIVE
    except ValueError as e:
        fix = (
            "Add the Demo Trading keys to .env (docs/09-Testnet-Setup.md) and restart the app."
            if mode == "TESTNET"
            else "LIVE needs ENABLE_LIVE=1 + BINANCE_KEY/SECRET in .env — only after the TESTNET "
            "checklist passes (docs/07 §5). Restart the app after editing .env."
        )
        checks = [_c("keys", "Keys in .env", "fail", str(e), fix)]
        return {"mode": mode, "endpoint": endpoint, "status": "fail", "checks": checks}
    try:
        client = await exchange_client(mode)
    except Exception as e:  # noqa: BLE001 — e.g. network down while creating the client
        checks = [_c("connect", "Connect to Binance", "fail", _err(e),
                     "This server cannot reach Binance (firewall/DNS/proxy?).")]
        return {"mode": mode, "endpoint": endpoint, "status": "fail", "checks": checks}
    symbols = list(
        (await session.execute(select(Bot.symbol).where(Bot.mode == mode))).scalars().all()
    ) or ["BTCUSDT"]
    checks = await run_checks(client, mode, symbols)
    return {"mode": mode, "endpoint": endpoint, "status": overall(checks), "checks": checks}
