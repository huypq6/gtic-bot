"""PaperEngine — matching nội bộ thuần (không async, không DB, không network).

Tách riêng để test kỹ logic tiền/PnL. PaperExecutor (paper.py) bọc engine này +
persist DB + broadcast. 1 engine = 1 bot = 1 symbol, tối đa 1 vị thế (no pyramiding).

Quy ước:
  BUY  → muốn LONG   | SELL → muốn SHORT | CLOSE → đóng | CANCEL → hủy pending
  Tín hiệu ngược chiều: ĐÓNG vị thế hiện tại (realize PnL) rồi MỞ chiều mới (flip).
SL/TP và LIMIT kiểm qua on_price(price) mỗi tick.

Mô phỏng sát sàn (Binance USDT-M Futures) — bật qua tham số, mặc định TẮT (giữ hành vi cũ):
  fee_rate = phí taker (MARKET, SL/TP/đóng) · maker_fee = phí LIMIT (mặc định = taker)
  slippage_bps: lệnh market/stop khớp lệch bất lợi N bps
  gap_fill: tick đã vượt SL → khớp tại giá tick (tệ hơn SL), như stop-market thật
  leverage > 1: có giá thanh lý (mmr) → chạm là đóng LIQUIDATION
"""

from dataclasses import dataclass

from app.strategy.base import Position, Signal


@dataclass
class Fill:
    side: str  # BUY | SELL
    type: str  # MARKET | LIMIT
    qty: float
    price: float
    fee: float = 0.0  # phí của lần khớp này (USDT)


@dataclass
class Closed:
    side: str  # LONG | SHORT
    qty: float
    entry_price: float
    exit_price: float
    pnl: float  # ròng = gross − phí vào − phí ra
    reason: str  # SIGNAL | SL | TP | MANUAL | LIQUIDATION
    gross: float = 0.0
    entry_fee: float = 0.0
    exit_fee: float = 0.0


@dataclass
class PendingOrder:
    oid: int  # id nội bộ engine, để khớp với row DB
    side: str  # BUY | SELL
    qty: float
    price: float  # limit price
    sl: float | None = None
    tp: float | None = None


@dataclass
class EngineEvent:
    fill: Fill | None = None
    opened: Position | None = None
    closed: Closed | None = None
    cancelled: bool = False
    queued: PendingOrder | None = None  # limit vào hàng chờ (persist NEW)
    filled_pending_id: int | None = None  # pending vừa khớp (NEW→FILLED)
    cancelled_ids: list[int] | None = None  # pending bị hủy (NEW→CANCELLED)


class PaperEngine:
    def __init__(
        self,
        symbol: str = "",
        fee_rate: float = 0.0,
        maker_fee: float | None = None,
        slippage_bps: float = 0.0,
        gap_fill: bool = False,
        leverage: float = 1.0,
        mmr: float = 0.005,
    ) -> None:
        self.symbol = symbol
        self.fee_rate = fee_rate
        self.maker_fee = fee_rate if maker_fee is None else maker_fee
        self.slip = slippage_bps / 10_000
        self.gap_fill = gap_fill
        self.leverage = max(1.0, float(leverage))
        self.mmr = mmr
        self.entry_fee = 0.0  # phí đã trả lúc mở vị thế hiện tại
        self.liq_price: float | None = None
        self.position: Position | None = None
        self.pending: list[PendingOrder] = []
        self._oid = 0

    def _next_oid(self) -> int:
        self._oid += 1
        return self._oid

    # ---------- public API ----------
    def submit(self, signal: Signal, price: float) -> list[EngineEvent]:
        if signal.action == "CANCEL":
            return self._cancel_all()
        if signal.action == "CLOSE":
            return [self._close(price, "SIGNAL")] if self.position else []
        if signal.action in ("BUY", "SELL"):
            if signal.order_type == "LIMIT" and signal.price is not None:
                order = PendingOrder(
                    self._next_oid(), signal.action, signal.size, signal.price,
                    signal.sl, signal.tp,
                )
                self.pending.append(order)
                return [EngineEvent(queued=order)]
            return self._apply_market(signal.action, signal.size, price, signal.sl, signal.tp)
        return []

    def on_price(self, price: float) -> list[EngineEvent]:
        events: list[EngineEvent] = []
        events += self._fill_pending(price)
        liq = self._check_liquidation(price)
        if liq:
            events.append(liq)
            return events
        sltp = self._check_sltp(price)
        if sltp:
            events.append(sltp)
        return events

    def force_close(self, price: float, reason: str = "MANUAL") -> list[EngineEvent]:
        """Đóng vị thế hiện tại tại giá `price` (vd can thiệp tay)."""
        return [self._close(self._slipped_exit(price), reason)] if self.position else []

    def restore(self, position: Position, entry_fee: float = 0.0) -> None:
        """Nạp lại vị thế đang mở (sau restart process) — không phát event."""
        self.position = position
        self.entry_fee = entry_fee
        self.liq_price = self._liq_price(position.side, position.entry_price)

    def margin(self) -> float:
        p = self.position
        return p.entry_price * p.qty / self.leverage if p else 0.0

    # ---------- giá khớp mô phỏng ----------
    def _slipped(self, side: str, price: float) -> float:
        """Lệnh market chiều `side` (BUY/SELL) khớp lệch bất lợi."""
        return price * (1 + self.slip) if side == "BUY" else price * (1 - self.slip)

    def _slipped_exit(self, price: float) -> float:
        p = self.position
        if not p:
            return price
        return self._slipped("SELL" if p.side == "LONG" else "BUY", price)

    def _liq_price(self, side: str, entry: float) -> float | None:
        if self.leverage <= 1:
            return None  # 1× (không vay) → không thanh lý
        if side == "LONG":
            return entry * (1 - 1 / self.leverage + self.mmr)
        return entry * (1 + 1 / self.leverage - self.mmr)

    def _check_liquidation(self, price: float) -> EngineEvent | None:
        p, liq = self.position, self.liq_price
        if not p or liq is None:
            return None
        if (p.side == "LONG" and price <= liq) or (p.side == "SHORT" and price >= liq):
            return self._close(price, "LIQUIDATION")
        return None

    def sltp_reason(self, price: float) -> str | None:
        """SL/TP có chạm ở `price` không (không đóng) — dùng cho testnet/live."""
        p = self.position
        if not p:
            return None
        if p.side == "LONG":
            if p.sl is not None and price <= p.sl:
                return "SL"
            if p.tp is not None and price >= p.tp:
                return "TP"
        else:
            if p.sl is not None and price >= p.sl:
                return "SL"
            if p.tp is not None and price <= p.tp:
                return "TP"
        return None

    def unrealized_pnl(self, price: float) -> float:
        p = self.position
        if not p:
            return 0.0
        if p.side == "LONG":
            return (price - p.entry_price) * p.qty
        return (p.entry_price - price) * p.qty

    # ---------- nội bộ ----------
    def _apply_market(
        self, side: str, qty: float, price: float, sl: float | None, tp: float | None,
        order_type: str = "MARKET",
    ) -> list[EngineEvent]:
        desired = "LONG" if side == "BUY" else "SHORT"
        if self.position and self.position.side == desired:
            return []  # cùng chiều → no-op (không pyramiding)
        events: list[EngineEvent] = []
        fill = price if order_type == "LIMIT" else self._slipped(side, price)
        if self.position:  # ngược chiều → đóng trước
            events.append(self._close(fill, "SIGNAL"))
        events.append(self._open(desired, qty, fill, sl, tp, order_type))
        return events

    def _open(
        self, side: str, qty: float, price: float, sl: float | None, tp: float | None,
        order_type: str = "MARKET",
    ) -> EngineEvent:
        self.position = Position(
            symbol=self.symbol, side=side, qty=qty, entry_price=price, sl=sl, tp=tp
        )
        rate = self.maker_fee if order_type == "LIMIT" else self.fee_rate
        self.entry_fee = rate * price * qty
        self.liq_price = self._liq_price(side, price)
        order_side = "BUY" if side == "LONG" else "SELL"
        return EngineEvent(
            fill=Fill(order_side, order_type, qty, price, self.entry_fee), opened=self.position
        )

    def _close(self, exit_price: float, reason: str) -> EngineEvent:
        p = self.position
        assert p is not None
        gross = (
            (exit_price - p.entry_price) * p.qty
            if p.side == "LONG"
            else (p.entry_price - exit_price) * p.qty
        )
        exit_fee = self.fee_rate * exit_price * p.qty  # thoát = taker (market/stop)
        closed = Closed(
            p.side, p.qty, p.entry_price, exit_price, gross - self.entry_fee - exit_fee, reason,
            gross=gross, entry_fee=self.entry_fee, exit_fee=exit_fee,
        )
        self.position = None
        self.entry_fee = 0.0
        self.liq_price = None
        return EngineEvent(closed=closed)

    def _cancel_all(self) -> list[EngineEvent]:
        if not self.pending:
            return []
        ids = [o.oid for o in self.pending]
        self.pending = []
        return [EngineEvent(cancelled=True, cancelled_ids=ids)]

    def _fill_pending(self, price: float) -> list[EngineEvent]:
        events: list[EngineEvent] = []
        still: list[PendingOrder] = []
        for o in self.pending:
            crosses = (o.side == "BUY" and price <= o.price) or (
                o.side == "SELL" and price >= o.price
            )
            if crosses:
                fills = self._apply_market(o.side, o.qty, o.price, o.sl, o.tp, "LIMIT")
                for ev in fills:
                    if ev.opened:  # đánh dấu pending nào vừa khớp
                        ev.filled_pending_id = o.oid
                events += fills
            else:
                still.append(o)
        self.pending = still
        return events

    def _check_sltp(self, price: float) -> EngineEvent | None:
        p = self.position
        if not p:
            return None
        # gap_fill: tick đã vượt SL → stop-market khớp ở giá tick (tệ hơn). TP khớp tại TP.
        if p.side == "LONG":
            if p.sl is not None and price <= p.sl:
                return self._close(self._slipped_exit(price if self.gap_fill else p.sl), "SL")
            if p.tp is not None and price >= p.tp:
                return self._close(self._slipped_exit(p.tp), "TP")
        else:  # SHORT
            if p.sl is not None and price >= p.sl:
                return self._close(self._slipped_exit(price if self.gap_fill else p.sl), "SL")
            if p.tp is not None and price <= p.tp:
                return self._close(self._slipped_exit(p.tp), "TP")
        return None
