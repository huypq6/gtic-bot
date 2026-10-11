"""Telegram notifications (settings edited in the UI, stored in app_setting "notify.telegram").

Listens to the EventBus:
  trade  → position opened / closed (published by the executors)
  risk   → order error · risk guard rejection · exchange protection problem / untracked position
  audit  → account halted / resumed · LIVE bot or account created (published by OrderManager)
  feed   → market feed DOWN (bots auto-paused) / back OK
Sending goes through its own queue + worker with retries: a Telegram problem never blocks or
breaks trading — it only shows up as `last_error` in the settings page.
"""

import asyncio
import html
import logging
import time
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.orders.models import AppSetting

logger = logging.getLogger(__name__)

KEY = "notify.telegram"
API = "https://api.telegram.org"

EVENTS = ("trade_open", "trade_close", "order_error", "risk_reject", "protection",
          "account_halt", "feed", "live_change")
DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "bot_token": "",
    "chat_id": "",
    "lang": "vi",
    "modes": {"PAPER": False, "TESTNET": True, "LIVE": True},
    "events": {"trade_open": True, "trade_close": True, "order_error": True,
               "risk_reject": False, "protection": True, "account_halt": True, "feed": True,
               "live_change": True},
}
# events tied to one trading mode → filtered by cfg["modes"]; the others are always sent
MODE_EVENTS = {"trade_open", "trade_close", "order_error", "risk_reject", "protection",
               "account_halt"}

T = {
    "vi": {
        "open": "🟢 <b>Mở {side}</b> {sym} · {mode}",
        "close": "{icon} <b>Đóng {side}</b> {sym} · {mode} — {reason}",
        "bot": "Bot #{bot}", "strategy": "Strategy",
        "entry": "Giá vào", "exit": "Giá ra", "qty": "Khối lượng", "sltp": "SL / TP",
        "pnl": "PnL", "risk": "Rủi ro (1R)",
        "order_error": "⚠️ <b>Lệnh lỗi</b> {sym} · {mode}", "signal": "Tín hiệu",
        "risk_reject": "⛔ <b>Bị rào chắn chặn</b> {sym} · {mode}",
        "protection": "🚨 <b>Cảnh báo bảo vệ vị thế</b> {sym} · {mode}",
        "halt": "🛑 <b>Tài khoản bị khoá</b> · {mode}",
        "resume": "✅ <b>Tài khoản mở khoá</b> · {mode}",
        "feed_down": "📡 <b>Mất feed giá</b> — các bot đang chạy đã tự PAUSE. "
                     "Vị thế trên sàn vẫn có SL/TP. Vào Trading để bật lại bot.",
        "feed_ok": "📡 Feed giá đã kết nối lại (bot vẫn PAUSE cho tới khi bạn bật lại).",
        "live_bot": "🔴 <b>Bot LIVE vừa được tạo</b> — #{bot} {sym}",
        "live_account": "🔴 <b>Tài khoản LIVE vừa được tạo</b> — {name}",
        "reason": {"SL": "SL", "TP": "TP", "SIGNAL": "tín hiệu", "MANUAL": "đóng tay",
                   "EXTERNAL": "đóng trên Binance", "LIQUIDATION": "THANH LÝ"},
        "test": "✅ GTIC Trading Bot đã kết nối Telegram.",
    },
    "en": {
        "open": "🟢 <b>Opened {side}</b> {sym} · {mode}",
        "close": "{icon} <b>Closed {side}</b> {sym} · {mode} — {reason}",
        "bot": "Bot #{bot}", "strategy": "Strategy",
        "entry": "Entry", "exit": "Exit", "qty": "Size", "sltp": "SL / TP",
        "pnl": "PnL", "risk": "Risk (1R)",
        "order_error": "⚠️ <b>Order failed</b> {sym} · {mode}", "signal": "Signal",
        "risk_reject": "⛔ <b>Blocked by risk guard</b> {sym} · {mode}",
        "protection": "🚨 <b>Position protection warning</b> {sym} · {mode}",
        "halt": "🛑 <b>Account halted</b> · {mode}",
        "resume": "✅ <b>Account resumed</b> · {mode}",
        "feed_down": "📡 <b>Market feed DOWN</b> — running bots were auto-PAUSED. Exchange "
                     "positions keep their SL/TP. Resume the bots on the Trading page.",
        "feed_ok": "📡 Market feed reconnected (bots stay PAUSED until you resume them).",
        "live_bot": "🔴 <b>LIVE bot created</b> — #{bot} {sym}",
        "live_account": "🔴 <b>LIVE account created</b> — {name}",
        "reason": {"SL": "SL", "TP": "TP", "SIGNAL": "signal", "MANUAL": "manual",
                   "EXTERNAL": "closed on Binance", "LIQUIDATION": "LIQUIDATED"},
        "test": "✅ GTIC Trading Bot is connected to Telegram.",
    },
}


def merged(cfg: dict | None) -> dict:
    c = {**DEFAULTS, **(cfg or {})}
    c["modes"] = {**DEFAULTS["modes"], **(cfg or {}).get("modes", {})}
    c["events"] = {**DEFAULTS["events"], **(cfg or {}).get("events", {})}
    return c


def _e(v: Any) -> str:
    return html.escape(str(v))


def _num(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.8g}" if abs(v) < 1000 else f"{v:,.2f}"


def build(topic: str, msg: dict, lang: str = "vi") -> tuple[str, str | None, str] | None:
    """(event, mode, html text) for a bus message, or None if it isn't notifiable. Pure."""
    t = T.get(lang, T["vi"])
    mode = msg.get("mode")
    sym = _e(msg.get("symbol") or "")
    if topic == "trade":
        side = msg.get("side", "")
        lines = []
        if msg.get("bot_id") is not None:
            lines.append(t["bot"].format(bot=msg["bot_id"]) +
                         (f" · {_e(msg['strategy'])}" if msg.get("strategy") else ""))
        if msg.get("event") == "open":
            head = t["open"].format(side=side, sym=sym, mode=mode)
            lines += [f"{t['entry']}: {_num(msg.get('entry'))}",
                      f"{t['qty']}: {_num(msg.get('qty'))}",
                      f"{t['sltp']}: {_num(msg.get('sl'))} / {_num(msg.get('tp'))}"]
            if msg.get("risk"):
                lines.append(f"{t['risk']}: {msg['risk']:.2f} USDT")
            return "trade_open", mode, "\n".join([head, *lines])
        if msg.get("event") == "close":
            pnl = msg.get("pnl")
            icon = "✅" if (pnl or 0) > 0 else "❌" if (pnl or 0) < 0 else "➖"
            reason = t["reason"].get(msg.get("reason") or "", msg.get("reason") or "")
            head = t["close"].format(icon=icon, side=side, sym=sym, mode=mode, reason=_e(reason))
            pl = f"{t['pnl']}: {pnl:+.4f} USDT" if pnl is not None else f"{t['pnl']}: —"
            if msg.get("r") is not None:
                pl += f" ({msg['r']:+.2f}R)"
            lines += [f"{t['entry']} → {t['exit']}: {_num(msg.get('entry'))} → "
                      f"{_num(msg.get('exit'))}", pl]
            return "trade_close", mode, "\n".join([head, *lines])
        return None
    if topic == "risk":
        reason = str(msg.get("reason") or "")
        bot = t["bot"].format(bot=msg["bot_id"]) if msg.get("bot_id") is not None else ""
        if reason.startswith("order failed"):
            ev, head = "order_error", t["order_error"]
            reason = reason.removeprefix("order failed: ")
        elif msg.get("signal"):
            ev, head = "risk_reject", t["risk_reject"]
        else:
            ev, head = "protection", t["protection"]
        lines = [head.format(sym=sym, mode=mode)]
        if bot or msg.get("signal"):
            lines.append(" · ".join(x for x in (
                bot, f"{t['signal']}: {msg['signal']}" if msg.get("signal") else "") if x))
        lines.append(_e(reason))
        return ev, mode, "\n".join(lines)
    if topic == "audit":
        a, d = msg.get("action"), msg.get("detail") or {}
        if a == "ACCOUNT_HALT":
            return "account_halt", mode, f"{t['halt'].format(mode=mode)}\n{_e(d.get('reason', ''))}"
        if a == "ACCOUNT_RESUME":
            return "account_halt", mode, t["resume"].format(mode=mode)
        if mode == "LIVE" and a == "CREATE_BOT":
            return "live_change", mode, t["live_bot"].format(bot=msg.get("bot_id"), sym=sym)
        if mode == "LIVE" and a == "ACCOUNT_CREATE":
            return "live_change", mode, t["live_account"].format(name=_e(d.get("name", "")))
        return None
    return None


async def tg_call(token: str, method: str, payload: dict | None = None) -> dict:
    """Telegram Bot API call → result, or raises RuntimeError with Telegram's description."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{API}/bot{token}/{method}", json=payload or {})
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(f"HTTP {r.status_code}") from None
    if not data.get("ok"):
        raise RuntimeError(data.get("description") or f"HTTP {r.status_code}")
    return data["result"]


class Notifier:
    def __init__(self, bus, session_factory: async_sessionmaker) -> None:
        self._bus = bus
        self._sf = session_factory
        self.cfg: dict = merged(None)
        self._q: asyncio.Queue[str] = asyncio.Queue(maxsize=200)
        self._feed_down = False
        self.last_ok_at: float | None = None
        self.last_error: str | None = None
        self.sent = 0

    # ---------- config ----------
    async def load(self) -> dict:
        async with self._sf() as s:
            row = await s.get(AppSetting, KEY)
        self.cfg = merged(row.value if row else None)
        return self.cfg

    async def save(self, patch: dict) -> dict:
        """Merge `patch` into the stored config. bot_token "" / missing keeps the saved one."""
        cfg = merged(self.cfg)
        for k, v in patch.items():
            if k == "bot_token" and not v:
                continue
            if k in ("modes", "events") and isinstance(v, dict):
                cfg[k] = {**cfg[k], **{x: bool(y) for x, y in v.items() if x in cfg[k]}}
            elif k in DEFAULTS:
                cfg[k] = v
        async with self._sf() as s:
            row = await s.get(AppSetting, KEY)
            if row is None:
                s.add(AppSetting(key=KEY, value=cfg))
            else:
                row.value = cfg
            await s.commit()
        self.cfg = cfg
        return cfg

    def public(self) -> dict:
        """Config for the UI — the token is never sent back, only a hint."""
        c = merged(self.cfg)
        tok = c.pop("bot_token")
        c["has_token"] = bool(tok)
        c["token_hint"] = f"••••{tok[-4:]}" if tok else ""
        c["status"] = {"last_ok_at": self.last_ok_at, "last_error": self.last_error,
                       "sent": self.sent, "queued": self._q.qsize()}
        return c

    def ready(self) -> bool:
        return bool(self.cfg["enabled"] and self.cfg["bot_token"] and self.cfg["chat_id"])

    # ---------- events ----------
    def handle(self, topic: str, msg: dict) -> str | None:
        """Bus message → queued text (or None when filtered out)."""
        if not isinstance(msg, dict):
            return None
        if topic == "feed":
            st = msg.get("status")
            if st == "DOWN" and not self._feed_down:
                self._feed_down = True
                return self._enqueue("feed", None, T[self._lang()]["feed_down"])
            if st == "OK" and self._feed_down:
                self._feed_down = False
                return self._enqueue("feed", None, T[self._lang()]["feed_ok"])
            return None
        out = build(topic, msg, self._lang())
        return self._enqueue(*out) if out else None

    def _lang(self) -> str:
        return self.cfg.get("lang") if self.cfg.get("lang") in T else "vi"

    def _enqueue(self, event: str, mode: str | None, text: str) -> str | None:
        if not self.ready() or not self.cfg["events"].get(event, False):
            return None
        if event in MODE_EVENTS and mode and not self.cfg["modes"].get(mode, False):
            return None
        try:
            self._q.put_nowait(text)
        except asyncio.QueueFull:
            logger.warning("telegram queue full — dropping a notification")
            return None
        return text

    async def run(self) -> None:
        """Bus listener + sender worker (runs for the app's lifetime)."""
        await self.load()
        subs = {t: self._bus.subscribe(t) for t in ("trade", "risk", "audit", "feed")}

        async def listen(topic: str, q: asyncio.Queue) -> None:
            while True:
                msg = await q.get()
                try:
                    self.handle(topic, msg)
                except Exception:  # noqa: BLE001
                    logger.exception("notifier: bad %s message", topic)

        tasks = [asyncio.create_task(listen(t, q)) for t, q in subs.items()]
        try:
            while True:
                text = await self._q.get()
                await self._send_with_retry(text)
                await asyncio.sleep(1.1)  # Telegram: ~1 message/second per chat
        finally:
            for t in tasks:
                t.cancel()
            for t, q in subs.items():
                self._bus.unsubscribe(t, q)

    async def _send_with_retry(self, text: str) -> None:
        for attempt in range(3):
            try:
                await self.send(text)
                return
            except Exception as e:  # noqa: BLE001
                self.last_error = str(e)[:300]
                logger.warning("telegram send failed (%s/3): %s", attempt + 1, e)
                await asyncio.sleep(2 * (attempt + 1))

    async def send(self, text: str, token: str | None = None, chat_id: str | None = None) -> None:
        await tg_call(token or self.cfg["bot_token"], "sendMessage", {
            "chat_id": chat_id or self.cfg["chat_id"], "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        self.last_ok_at, self.last_error = time.time(), None
        self.sent += 1
