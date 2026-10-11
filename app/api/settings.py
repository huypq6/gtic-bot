"""Settings edited in the UI (stored in app_setting, not .env) — Telegram notifications."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.notify.telegram import T, tg_call

router = APIRouter(prefix="/api")


class TelegramPatch(BaseModel):
    enabled: bool | None = None
    bot_token: str | None = None  # "" / omitted → keep the saved token
    chat_id: str | None = None
    lang: str | None = None
    modes: dict[str, bool] | None = None
    events: dict[str, bool] | None = None


class TokenBody(BaseModel):
    bot_token: str | None = None  # not saved yet → use this one; omitted → the saved token
    chat_id: str | None = None


def _n(request: Request):
    return request.app.state.notifier


@router.get("/settings/telegram")
async def get_telegram(request: Request) -> dict:
    return _n(request).public()


@router.put("/settings/telegram")
async def put_telegram(body: TelegramPatch, request: Request) -> dict:
    patch = body.model_dump(exclude_none=True)
    if "lang" in patch and patch["lang"] not in T:
        raise HTTPException(422, "lang must be vi or en")
    if "bot_token" in patch:
        patch["bot_token"] = patch["bot_token"].strip()
    if "chat_id" in patch:
        patch["chat_id"] = patch["chat_id"].strip()
    await _n(request).save(patch)
    await request.app.state.order_manager.write_audit(
        source="MANUAL", action="SETTINGS_TELEGRAM",
        detail={k: v for k, v in patch.items() if k != "bot_token"}
        | ({"bot_token": "changed"} if patch.get("bot_token") else {}),
    )
    return _n(request).public()


@router.post("/settings/telegram/test")
async def test_telegram(body: TokenBody, request: Request) -> dict:
    n = _n(request)
    token = (body.bot_token or "").strip() or n.cfg["bot_token"]
    chat = (body.chat_id or "").strip() or n.cfg["chat_id"]
    if not token or not chat:
        raise HTTPException(400, "bot token and chat id are required")
    try:
        await n.send(T[n.cfg.get("lang", "vi")]["test"], token=token, chat_id=chat)
    except Exception as e:  # noqa: BLE001
        n.last_error = str(e)[:300]
        raise HTTPException(400, f"Telegram: {e}") from e
    return {"ok": True}


@router.post("/settings/telegram/chats")
async def find_chats(body: TokenBody, request: Request) -> dict:
    """Chats that recently messaged the bot (getUpdates) → pick one as chat id. The user sends any
    message to the bot (or adds it to a group) first."""
    token = (body.bot_token or "").strip() or _n(request).cfg["bot_token"]
    if not token:
        raise HTTPException(400, "bot token is required")
    try:
        me = await tg_call(token, "getMe")
        updates = await tg_call(token, "getUpdates", {"limit": 100, "timeout": 0})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Telegram: {e}") from e
    chats: dict[str, dict] = {}
    for u in updates:
        m = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
        c = m.get("chat")
        if not c:
            continue
        name = c.get("title") or " ".join(
            x for x in (c.get("first_name"), c.get("last_name")) if x
        ) or c.get("username") or ""
        chats[str(c["id"])] = {"id": str(c["id"]), "type": c.get("type"), "name": name,
                               "username": c.get("username")}
    return {"bot": {"username": me.get("username"), "name": me.get("first_name")},
            "chats": list(chats.values())}
