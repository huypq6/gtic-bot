"""PaperEngine — matching nội bộ (pure). Logic này dùng chung cho paper mode.

Quy ước: 1 bot = 1 vị thế (không pyramiding). BUY = muốn LONG, SELL = muốn SHORT,
CLOSE = đóng vị thế. Tín hiệu ngược chiều sẽ ĐÓNG rồi MỞ chiều mới (flip).
"""

from app.execution.paper_engine import PaperEngine
from app.strategy.base import Signal


def buy(size=1.0, **kw):
    return Signal(action="BUY", symbol="BTCUSDT", size=size, **kw)


def sell(size=1.0, **kw):
    return Signal(action="SELL", symbol="BTCUSDT", size=size, **kw)


def close():
    return Signal(action="CLOSE", symbol="BTCUSDT")


# ---- mở vị thế MARKET ----
def test_market_buy_opens_long():
    eng = PaperEngine()
    events = eng.submit(buy(2), price=100)
    assert eng.position is not None
    assert eng.position.side == "LONG"
    assert eng.position.qty == 2
    assert eng.position.entry_price == 100
    assert any(e.opened for e in events)
    assert any(e.fill and e.fill.price == 100 for e in events)


def test_market_sell_opens_short_when_flat():
    eng = PaperEngine()
    eng.submit(sell(1), price=100)
    assert eng.position.side == "SHORT"


# ---- đóng vị thế + PnL ----
def test_close_long_realizes_profit():
    eng = PaperEngine()
    eng.submit(buy(2), price=100)
    events = eng.submit(close(), price=110)
    assert eng.position is None
    closed = [e.closed for e in events if e.closed][0]
    assert closed.side == "LONG"
    assert closed.exit_price == 110
    assert closed.pnl == (110 - 100) * 2  # +20


def test_close_short_realizes_profit():
    eng = PaperEngine()
    eng.submit(sell(2), price=100)
    events = eng.submit(close(), price=90)
    closed = [e.closed for e in events if e.closed][0]
    assert closed.pnl == (100 - 90) * 2  # +20 (short lãi khi giá giảm)


def test_sell_flips_long_to_short():
    eng = PaperEngine()
    eng.submit(buy(1), price=100)
    events = eng.submit(sell(1), price=120)
    # đóng long (+20) rồi mở short
    assert eng.position.side == "SHORT"
    assert eng.position.entry_price == 120
    assert any(e.closed and e.closed.pnl == 20 for e in events)


def test_buy_when_already_long_is_noop():
    eng = PaperEngine()
    eng.submit(buy(1), price=100)
    events = eng.submit(buy(1), price=105)
    assert eng.position.qty == 1
    assert eng.position.entry_price == 100  # không đổi
    assert events == []


# ---- SL / TP qua on_price ----
def test_long_stop_loss_triggers():
    eng = PaperEngine()
    eng.submit(buy(1, sl=95, tp=120), price=100)
    events = eng.on_price(94)
    assert eng.position is None
    closed = [e.closed for e in events if e.closed][0]
    assert closed.reason == "SL"
    assert closed.exit_price == 95
    assert closed.pnl == (95 - 100) * 1  # -5


def test_long_take_profit_triggers():
    eng = PaperEngine()
    eng.submit(buy(1, sl=95, tp=120), price=100)
    events = eng.on_price(125)
    closed = [e.closed for e in events if e.closed][0]
    assert closed.reason == "TP"
    assert closed.exit_price == 120
    assert closed.pnl == 20


def test_short_stop_loss_triggers():
    eng = PaperEngine()
    eng.submit(sell(1, sl=105, tp=80), price=100)
    events = eng.on_price(106)
    closed = [e.closed for e in events if e.closed][0]
    assert closed.reason == "SL"
    assert closed.exit_price == 105
    assert closed.pnl == (100 - 105) * 1  # -5


def test_no_trigger_when_price_inside_band():
    eng = PaperEngine()
    eng.submit(buy(1, sl=95, tp=120), price=100)
    assert eng.on_price(110) == []
    assert eng.position is not None


# ---- LIMIT ----
def test_buy_limit_queues_then_fills_when_price_crosses():
    eng = PaperEngine()
    events = eng.submit(buy(1, order_type="LIMIT", price=95), price=100)
    assert eng.position is None  # chưa khớp
    assert any(e.fill and e.fill.type == "LIMIT" for e in events) is False
    assert len(eng.pending) == 1
    eng.on_price(96)  # chưa chạm
    assert eng.position is None
    eng.on_price(95)  # chạm → khớp
    assert eng.position is not None
    assert eng.position.entry_price == 95
    assert eng.pending == []


def test_sell_limit_fills_when_price_rises():
    eng = PaperEngine()
    eng.submit(sell(1, order_type="LIMIT", price=105), price=100)
    eng.on_price(105)
    assert eng.position is not None
    assert eng.position.side == "SHORT"


def test_cancel_clears_pending():
    eng = PaperEngine()
    eng.submit(buy(1, order_type="LIMIT", price=95), price=100)
    events = eng.submit(Signal(action="CANCEL", symbol="BTCUSDT"), price=100)
    assert eng.pending == []
    assert any(e.cancelled for e in events)


# ---- phí ----
def test_fee_reduces_pnl():
    eng = PaperEngine(fee_rate=0.001)
    eng.submit(buy(1), price=100)
    events = eng.submit(close(), price=110)
    closed = [e.closed for e in events if e.closed][0]
    # gross +10, fee = 0.001*(100+110)= 0.21
    assert abs(closed.pnl - (10 - 0.21)) < 1e-9


# ---- unrealized PnL ----
def test_unrealized_pnl():
    eng = PaperEngine()
    eng.submit(buy(2), price=100)
    assert eng.unrealized_pnl(105) == (105 - 100) * 2
    eng.submit(close(), price=100)
    assert eng.unrealized_pnl(105) == 0.0
