"""AccountService — số dư, sổ cái, snapshot equity/ký quỹ/rủi ro, rào chắn (P9a, PAPER).

Mọi biến động số dư đi qua `_post()` (khóa dòng account FOR UPDATE → ghi account_txn +
cập nhật balance trong CÙNG transaction). Giá mark lấy từ tick executor đẩy vào
(`mark()`), thiếu thì nến 1m cuối trong DB, cuối cùng là giá vào.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.account.risk import AccountState, Limits, check_halt, position_risk
from app.market.models import Kline
from app.orders.models import Account, AccountTxn, PositionModel

logger = logging.getLogger(__name__)


def _f(v) -> float | None:
    return float(v) if v is not None else None


def limits_of(a: Account) -> Limits:
    return Limits(
        leverage=float(a.leverage), taker_fee=float(a.taker_fee),
        max_risk_pct=_f(a.max_risk_pct), max_open_risk_pct=_f(a.max_open_risk_pct),
        max_positions=a.max_positions, daily_loss_pct=_f(a.daily_loss_pct),
        max_dd_pct=_f(a.max_dd_pct),
    )


def is_exchange(a: Account) -> bool:
    return a.mode in ("TESTNET", "LIVE")


# income type của Binance Futures → loại sổ cái
_INCOME = {"REALIZED_PNL": "REALIZED_PNL", "COMMISSION": "FEE", "FUNDING_FEE": "FUNDING"}


def day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class AccountService:
    def __init__(self, session_factory: async_sessionmaker, order_manager=None) -> None:
        self._sf = session_factory
        self._om = order_manager
        self._marks: dict[str, float] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    # ---------- giá mark ----------
    def mark(self, symbol: str, price: float) -> None:
        self._marks[symbol] = price

    async def _mark_of(self, s: AsyncSession, symbol: str, fallback: float) -> float:
        if symbol in self._marks:
            return self._marks[symbol]
        k = (
            await s.execute(
                select(Kline.close).where(Kline.symbol == symbol, Kline.tf == "1m")
                .order_by(Kline.ts.desc()).limit(1)
            )
        ).scalar_one_or_none()
        return float(k) if k is not None else fallback

    def lock(self, account_id: int) -> asyncio.Lock:
        """Khóa theo tài khoản: tính khối lượng + mở lệnh là 1 bước nguyên tử (nhiều bot)."""
        return self._locks.setdefault(account_id, asyncio.Lock())

    # ---------- đọc ----------
    async def get(self, account_id: int) -> Account | None:
        async with self._sf() as s:
            return await s.get(Account, account_id)

    async def default_paper(self) -> Account | None:
        async with self._sf() as s:
            return (
                await s.execute(
                    select(Account).where(Account.mode == "PAPER").order_by(Account.id).limit(1)
                )
            ).scalar_one_or_none()

    async def snapshot(self, account_id: int, now: datetime | None = None) -> AccountState:
        now = now or datetime.now(UTC)
        async with self._sf() as s:
            a = await s.get(Account, account_id)
            if a is None:
                raise KeyError(account_id)
            lev = float(a.leverage)
            pos = (
                await s.execute(
                    select(PositionModel).where(
                        PositionModel.account_id == account_id, PositionModel.status == "OPEN"
                    )
                )
            ).scalars().all()
            upnl = margin = risk = 0.0
            for p in pos:
                entry, qty = float(p.entry_price), float(p.qty)
                m = await self._mark_of(s, p.symbol, entry)
                upnl += (m - entry) * qty if p.side == "LONG" else (entry - m) * qty
                margin += float(p.margin) if p.margin is not None else entry * qty / lev
                risk += position_risk(p.side, qty, entry, _f(p.sl))
            d0 = day_start(now)
            day_bal = (
                await s.execute(
                    select(AccountTxn.balance_after)
                    .where(AccountTxn.account_id == account_id, AccountTxn.ts < d0)
                    .order_by(AccountTxn.ts.desc(), AccountTxn.id.desc()).limit(1)
                )
            ).scalar_one_or_none()
            realized_today = (
                await s.execute(
                    select(func.coalesce(func.sum(AccountTxn.amount), 0)).where(
                        AccountTxn.account_id == account_id, AccountTxn.ts >= d0,
                        AccountTxn.type.in_(("REALIZED_PNL", "FEE", "FUNDING")),
                    )
                )
            ).scalar_one()
            balance = float(a.balance)
            equity = balance + upnl
            avail = None
            if is_exchange(a):  # số liệu của SÀN (lần đồng bộ cuối) là chuẩn
                upnl = float(a.exch_unrealized or 0)
                equity = float(a.exch_equity) if a.exch_equity is not None else balance + upnl
                margin = float(a.exch_margin or 0)
                avail = float(a.exch_available) if a.exch_available is not None else None
            peak = max(float(a.peak_equity), equity)
            if peak > float(a.peak_equity):
                a.peak_equity = peak
                await s.commit()
        return AccountState(
            balance=balance, equity=equity, used_margin=margin,
            available=avail if avail is not None else equity - margin,
            open_risk=risk, n_open=len(pos),
            daily_pnl=float(realized_today) + upnl,
            day_start_balance=float(day_bal) if day_bal is not None else balance,
            peak_equity=peak,
        )

    # ---------- ghi sổ ----------
    async def _post(
        self, s: AsyncSession, account_id: int, type_: str, amount: float, **kw
    ) -> float:
        a = (
            await s.execute(select(Account).where(Account.id == account_id).with_for_update())
        ).scalar_one()
        new_bal = float(a.balance) + amount
        a.balance = new_bal
        # nạp/rút (và số dư ban đầu của sàn) không phải lãi/lỗ → dời đỉnh theo
        if type_ in ("DEPOSIT", "WITHDRAW") or kw.get("note") == "Số dư ban đầu trên sàn":
            a.peak_equity = max(0.0, float(a.peak_equity) + amount)
        s.add(AccountTxn(account_id=account_id, type=type_, amount=amount,
                         balance_after=new_bal, **kw))
        return new_bal

    async def _paper_only(self, account_id: int) -> None:
        a = await self.get(account_id)
        if a is not None and is_exchange(a):
            raise ValueError(
                "tài khoản sàn: nạp/rút thực hiện trên Binance (chuyển Spot ↔ Futures); "
                "số dư tự đồng bộ về đây"
            )

    async def deposit(self, account_id: int, amount: float, note: str | None = None) -> float:
        if amount <= 0:
            raise ValueError("số tiền nạp phải > 0")
        await self._paper_only(account_id)
        async with self._sf() as s:
            bal = await self._post(s, account_id, "DEPOSIT", amount, note=note)
            await s.commit()
        return bal

    async def withdraw(self, account_id: int, amount: float, note: str | None = None) -> float:
        if amount <= 0:
            raise ValueError("số tiền rút phải > 0")
        await self._paper_only(account_id)
        async with self.lock(account_id):
            st = await self.snapshot(account_id)
            if amount > st.available + 1e-9:
                raise ValueError(
                    f"chỉ rút được tối đa {max(0.0, st.available):.2f} USDT "
                    "(số dư khả dụng, đã trừ ký quỹ lệnh đang mở)"
                )
            async with self._sf() as s:
                bal = await self._post(s, account_id, "WITHDRAW", -amount, note=note)
                await s.commit()
        return bal

    async def record_fee(
        self, account_id: int, fee: float, *, position_id=None, bot_id=None, symbol=None,
        note: str = "phí mở lệnh",
    ) -> None:
        if not fee:
            return
        async with self._sf() as s:
            await self._post(s, account_id, "FEE", -fee, position_id=position_id,
                             bot_id=bot_id, symbol=symbol, note=note)
            await s.commit()

    async def record_close(
        self, account_id: int, *, gross: float, exit_fee: float, position_id=None,
        bot_id=None, symbol=None, reason: str | None = None,
    ) -> None:
        async with self._sf() as s:
            await self._post(s, account_id, "REALIZED_PNL", gross, position_id=position_id,
                             bot_id=bot_id, symbol=symbol, note=reason)
            if exit_fee:
                await self._post(s, account_id, "FEE", -exit_fee, position_id=position_id,
                                 bot_id=bot_id, symbol=symbol, note="phí đóng lệnh")
            await s.commit()
        await self.enforce(account_id)

    # ---------- tài khoản sàn (P9b) ----------
    async def sync_exchange(self, account_id: int, client=None) -> None:
        """Đọc số dư/ký quỹ/lãi tạm từ sàn + nhập income history vào sổ cái.

        Lần đầu: 1 dòng "số dư ban đầu trên sàn" (không kéo lịch sử cũ). Sau đó nhập từng
        dòng income (REALIZED_PNL, COMMISSION, FUNDING_FEE, TRANSFER…) theo `income_cursor`,
        chống trùng bằng ext_id. Cuối cùng đối chiếu: số dư sổ ≠ ví sàn → dòng ADJUST.
        Lỗi mạng/key → lưu `sync_error`, không raise (vòng đồng bộ chạy tiếp).
        """
        a = await self.get(account_id)
        if a is None or not is_exchange(a):
            return
        try:
            if client is None:
                from app.execution.clients import exchange_client

                client = await exchange_client(a.mode)
            snap = await client.account()
            rows = await client.income(int(a.income_cursor) + 1) if a.income_cursor else []
        except Exception as e:  # noqa: BLE001
            async with self._sf() as s:
                row = await s.get(Account, account_id)
                row.sync_error = str(e)[:500]
                row.last_sync_at = datetime.now(UTC)
                await s.commit()
            logger.warning("đồng bộ tài khoản sàn %s lỗi: %s", account_id, e)
            return

        now = datetime.now(UTC)
        async with self._sf() as s:
            if a.income_cursor is None:  # lần đầu
                await self._post(s, account_id, "ADJUST", snap["wallet"] - float(a.balance),
                                 note="Số dư ban đầu trên sàn", ts=now)
                cursor = int(now.timestamp() * 1000)
            else:
                cursor = int(a.income_cursor)
                seen = set((await s.execute(
                    select(AccountTxn.ext_id).where(
                        AccountTxn.account_id == account_id,
                        AccountTxn.ext_id.in_([r["ext_id"] for r in rows] or [""]),
                    )
                )).scalars())
                for r in sorted(rows, key=lambda x: x["ts"]):
                    cursor = max(cursor, r["ts"])
                    if r["ext_id"] in seen or (r.get("asset") and r["asset"] != a.currency):
                        continue
                    typ = _INCOME.get(r["type"])
                    if r["type"] == "TRANSFER":
                        typ = "DEPOSIT" if r["amount"] > 0 else "WITHDRAW"
                    await self._post(
                        s, account_id, typ or "ADJUST", r["amount"], symbol=r.get("symbol"),
                        note=None if typ else r["type"], ext_id=r["ext_id"],
                        ts=datetime.fromtimestamp(r["ts"] / 1000, tz=UTC),
                    )
            row = await s.get(Account, account_id)
            diff = snap["wallet"] - float(row.balance)
            if abs(diff) > 1e-6:  # income chưa về/bị giới hạn → khớp theo ví sàn
                await self._post(s, account_id, "ADJUST", diff, note="Đối chiếu số dư sàn", ts=now)
            row.income_cursor = cursor
            row.exch_equity, row.exch_unrealized = snap["equity"], snap["unrealized"]
            row.exch_margin, row.exch_available = snap["margin"], snap["available"]
            row.last_sync_at, row.sync_error = now, None
            await s.commit()

    # ---------- rào chắn ----------
    async def enforce(self, account_id: int) -> str | None:
        """Kiểm sụt vốn / lỗ ngày → khóa tài khoản. Trả lý do nếu đang bị chặn vào lệnh."""
        now = datetime.now(UTC)
        a = await self.get(account_id)
        if a is None:
            return "tài khoản không tồn tại"
        if a.status == "HALTED":
            return f"tài khoản đang DỪNG: {a.halted_reason or ''}".strip()
        if a.halted_until and a.halted_until > now:
            return f"nghỉ tới {a.halted_until:%Y-%m-%d %H:%M} UTC: {a.halted_reason or ''}"
        st = await self.snapshot(account_id, now)
        lim = limits_of(a)
        why = check_halt(st, lim)
        if not why:
            return None
        async with self._sf() as s:
            row = await s.get(Account, account_id)
            if lim.max_dd_pct is not None and st.dd_pct >= lim.max_dd_pct:
                row.status, row.halted_reason = "HALTED", why  # chờ người xem xét
            else:
                row.halted_until = day_start(now) + timedelta(days=1)  # hết ngày UTC
                row.halted_reason = why
            await s.commit()
        if self._om:
            await self._om.write_audit(
                source="SYSTEM", action="ACCOUNT_HALT", mode=a.mode,
                detail={"account_id": account_id, "reason": why},
            )
        logger.warning("account %s bị chặn: %s", account_id, why)
        return why

    async def resume(self, account_id: int) -> None:
        async with self._sf() as s:
            a = await s.get(Account, account_id)
            a.status, a.halted_reason, a.halted_until = "ACTIVE", None, None
            # đặt lại đỉnh = equity hiện tại để không bị khóa lại ngay
            a.peak_equity = a.balance
            await s.commit()
        st = await self.snapshot(account_id)
        async with self._sf() as s:
            a = await s.get(Account, account_id)
            a.peak_equity = st.equity
            await s.commit()


async def run_exchange_sync(service: AccountService, interval: float = 15.0) -> None:
    """Vòng nền: đồng bộ mọi tài khoản TESTNET/LIVE mỗi `interval` giây + kiểm rào chắn."""
    while True:
        try:
            async with service._sf() as s:
                ids = list((await s.execute(
                    select(Account.id).where(Account.mode.in_(("TESTNET", "LIVE")))
                )).scalars())
            for aid in ids:
                await service.sync_exchange(aid)
                await service.enforce(aid)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("vòng đồng bộ tài khoản sàn lỗi")
        await asyncio.sleep(interval)
