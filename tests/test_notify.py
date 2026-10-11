"""Telegram notifier: message building, event/mode filters, token masking, feed state."""

from app.notify.telegram import Notifier, build, merged


def ready(**over):
    n = Notifier(bus=None, session_factory=None)
    n.cfg = merged({"enabled": True, "bot_token": "123:ABCDEFwxyz", "chat_id": "42", **over})
    return n


OPEN = {"event": "open", "mode": "TESTNET", "bot_id": 6, "symbol": "DOGEUSDT", "side": "LONG",
        "qty": 71.0, "entry": 0.08539, "sl": 0.0828, "tp": 0.0879, "risk": 1.84,
        "strategy": "ict_po3 v4"}
CLOSE = {"event": "close", "mode": "TESTNET", "bot_id": 6, "symbol": "DOGEUSDT", "side": "LONG",
         "qty": 71.0, "entry": 0.08539, "exit": 0.0879, "pnl": 1.75, "reason": "TP", "r": 2.04}


def test_trade_messages():
    ev, mode, text = build("trade", OPEN, "vi")
    assert (ev, mode) == ("trade_open", "TESTNET")
    assert "Mở LONG" in text and "DOGEUSDT" in text and "Bot #6 · ict_po3 v4" in text
    ev, _, text = build("trade", CLOSE, "en")
    assert ev == "trade_close"
    assert "✅" in text and "+1.7500 USDT (+2.04R)" in text and "TP" in text


def test_risk_classification_and_escaping():
    err = {"mode": "LIVE", "bot_id": 9, "symbol": "BTCUSDT", "signal": "BUY",
           "reason": "order failed: notional <5 USDT (code -4164)"}
    ev, _, text = build("risk", err, "en")
    assert ev == "order_error" and "&lt;5 USDT" in text and "order failed" not in text
    assert build("risk", {**err, "reason": "daily loss limit"}, "en")[0] == "risk_reject"
    assert build("risk", {"mode": "LIVE", "symbol": "BTCUSDT",
                          "reason": "could not place SL/TP"}, "en")[0] == "protection"


def test_audit_events():
    halt = {"action": "ACCOUNT_HALT", "mode": "LIVE", "detail": {"reason": "drawdown 11%"}}
    assert build("audit", halt, "en")[0] == "account_halt"
    live = {"action": "CREATE_BOT", "mode": "LIVE", "bot_id": 12, "symbol": "BTCUSDT"}
    assert build("audit", live, "en")[0] == "live_change"
    assert build("audit", {**live, "mode": "PAPER"}, "en") is None
    assert build("audit", {"action": "EDIT_SLTP", "mode": "LIVE"}, "en") is None


def test_filters_by_event_mode_and_readiness():
    n = ready()
    assert n.handle("trade", OPEN)  # TESTNET on by default
    assert not n.handle("trade", {**OPEN, "mode": "PAPER"})  # PAPER off by default
    n.cfg["events"]["trade_open"] = False
    assert not n.handle("trade", OPEN)
    assert not ready(enabled=False).handle("trade", CLOSE)
    assert not ready(chat_id="").handle("trade", CLOSE)
    # risk_reject is off by default (can be noisy)
    assert not ready().handle("risk", {"mode": "LIVE", "symbol": "X", "signal": "BUY",
                                       "reason": "max positions"})


def test_feed_down_then_ok_once():
    n = ready()
    assert n.handle("feed", {"status": "RECONNECTING"}) is None
    assert "PAUSE" in n.handle("feed", {"status": "DOWN"})
    assert n.handle("feed", {"status": "DOWN"}) is None  # not repeated
    assert n.handle("feed", {"status": "OK"})
    assert n.handle("feed", {"status": "OK"}) is None  # OK without a prior DOWN → silent


def test_public_never_returns_the_token():
    pub = ready().public()
    assert "bot_token" not in pub
    assert pub["has_token"] and pub["token_hint"] == "••••wxyz"
    assert "123:ABC" not in str(pub)
