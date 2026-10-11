"""TESTNET end-to-end check of the REAL ExchangeExecutor + AccountService (docs/07 §1–4 automated).

Drives the app's own classes against Binance Futures Demo Trading and the local DB:
  S1 open with exchange SL/TP · S2 edit SL/TP · S3 restart/restore · S4 closed by hand on Binance
  S5 reversal + signal close · S6 refuse untracked exchange position · S7 SL filled on the exchange
  S8 ledger import == exchange wallet
Uses a symbol no running bot trades (default XRPUSDT), the smallest allowed size, and a temporary
TESTNET account row in the LOCAL DB (deleted at the end). Never talks to LIVE.

Run:  PYTHONPATH=. uv run python scripts/testnet_e2e.py [SYMBOL]
"""

import asyncio
import math
import os
import sys
import time

from sqlalchemy import delete, func, select

from app.account.service import AccountService
from app.config import settings
from app.db import async_session
from app.execution.binance_futures import BinanceFuturesClient
from app.execution.exchange import ExchangeExecutor, ExchangeOrderError
from app.market.bus import EventBus
from app.orders.models import Account, AccountTxn, OrderModel, PositionModel
from app.strategy.base import Signal

ACC_NAME = "__e2e_testnet__"
S7_PCT = float(os.environ.get("S7_PCT", "0.0007"))  # SL/TP distance for the on-exchange fill test
results: list[tuple[str, str, str]] = []


def rec(name: str, ok: bool | None, detail: str = "") -> None:
    st = "PASS" if ok else ("SKIP" if ok is None else "FAIL")
    results.append((st, name, detail))
    mark = {"PASS": "\033[32m✔", "FAIL": "\033[31m✘", "SKIP": "\033[33m–"}[st]
    print(f"  {mark} {name}\033[0m {detail}", flush=True)


def ceil_to(v: float, step: float) -> float:
    return round(math.ceil(v / step - 1e-9) * step, max(0, -int(math.floor(math.log10(step)))))


async def algo_ids(c, sym) -> set[str]:
    return {str(o.get("algoId")) for o in await c.open_algo_orders(sym)}


async def db_positions(sym):
    async with async_session() as s:
        return list((await s.execute(
            select(PositionModel)
            .where(PositionModel.symbol == sym, PositionModel.mode == "TESTNET")
            .order_by(PositionModel.id)
        )).scalars())


async def db_orders(sym):
    async with async_session() as s:
        return list((await s.execute(
            select(OrderModel).where(OrderModel.symbol == sym, OrderModel.mode == "TESTNET")
            .order_by(OrderModel.id)
        )).scalars())


async def cleanup_db(sym):
    async with async_session() as s:
        await s.execute(delete(OrderModel).where(OrderModel.symbol == sym,
                                                 OrderModel.mode == "TESTNET"))
        await s.execute(delete(PositionModel).where(PositionModel.symbol == sym,
                                                    PositionModel.mode == "TESTNET"))
        await s.execute(delete(Account).where(Account.name == ACC_NAME))
        await s.commit()


async def flatten(c, sym):
    for oid in await algo_ids(c, sym):
        await c.cancel_protection(sym, {"x": oid})
    p = await c.position(sym)
    if p["amt"]:
        await c.market_order(sym, "SELL" if p["amt"] > 0 else "BUY", abs(p["amt"]),
                             reduce_only=True)


async def main() -> int:
    sym = (sys.argv[1] if len(sys.argv) > 1 else "XRPUSDT").upper()
    if not settings.binance_testnet_key:
        print("BINANCE_TESTNET_KEY missing in .env")
        return 2
    c = await BinanceFuturesClient.create(settings.binance_testnet_key,
                                          settings.binance_testnet_secret, testnet=True,
                                          endpoint=settings.binance_testnet_endpoint)
    assert c.testnet
    print(f"Endpoint {c.base_url} · symbol {sym}")
    if (await c.position(sym))["amt"] or await algo_ids(c, sym):
        print(f"{sym} has an open position/orders on testnet — pick another symbol")
        return 1
    await cleanup_db(sym)

    bus = EventBus()
    risk = bus.subscribe("risk")
    svc = AccountService(async_session)
    async with async_session() as s:
        acc = Account(name=ACC_NAME, mode="TESTNET", balance=0, peak_equity=0, leverage=3,
                      taker_fee=0.0005, maker_fee=0.0002, slippage_bps=0)
        s.add(acc)
        await s.commit()
        acc_id = acc.id
    await svc.sync_exchange(acc_id, client=c)  # first sync: opening balance + income cursor

    def new_exec():
        ex = ExchangeExecutor(None, sym, "TESTNET", bus, async_session, c)
        ex.reconcile_every = 0
        return ex

    rules = await c.rules(sym)
    mark = float((await c._raw.futures_mark_price(symbol=sym))["markPrice"])
    qty = max(rules.min_qty, ceil_to(rules.min_notional * 1.3 / mark, rules.step))
    print(f"mark {mark} · qty {qty} (≈{qty * mark:.2f} USDT)\n")
    t_start = int(time.time() * 1000)
    ex = new_exec()
    acc_row = await svc.get(acc_id)
    ex.attach_account(acc_row, svc)
    try:
        # S1 ------------------------------------------------------------------------------
        print("S1 open LONG with SL/TP on the exchange")
        await ex.on_price(mark)
        await ex.submit(Signal("BUY", sym, size=qty, sl=mark * 0.98, tp=mark * 1.02))
        expos = await c.position(sym)
        ids = await algo_ids(c, sym)
        [pos] = await db_positions(sym)
        orders = await db_orders(sym)
        rec("exchange position opened", expos["amt"] > 0, f"amt {expos['amt']}")
        rec("SL + TP on the exchange", set(ex._protect.values()) <= ids and len(ids) == 2,
            str(ex._protect))
        rec("DB position OPEN with ext_protect", pos.status == "OPEN" and bool(pos.ext_protect))
        rec("entry = exchange fill", abs(float(pos.entry_price) - expos["entry"]) < 1e-9,
            f"app {float(pos.entry_price)} · exchange {expos['entry']}")
        o = orders[-1]
        rec("fill row: ext_id + OPEN + position_id",
            bool(o.ext_id) and o.intent == "OPEN" and o.position_id == pos.id, f"ext {o.ext_id}")

        # S2 ------------------------------------------------------------------------------
        print("S2 edit SL/TP")
        old = set(ex._protect.values())
        await ex.modify_sltp(mark * 0.97, mark * 1.03)
        await asyncio.sleep(0.5)
        ids = await algo_ids(c, sym)
        rec("old SL/TP cancelled, new ones placed",
            not (old & ids) and set(ex._protect.values()) == ids and len(ids) == 2)

        # S3 ------------------------------------------------------------------------------
        print("S3 restart → restore")
        ex2 = new_exec()
        ex2.attach_account(acc_row, svc)
        restored = await ex2.restore_open()
        ids_after = await algo_ids(c, sym)
        rec("position restored", restored and ex2.engine.position is not None)
        rec("SL/TP ids reloaded, no duplicates", ex2._protect == ex._protect and ids_after == ids)

        # S4 ------------------------------------------------------------------------------
        print("S4 closed by hand on Binance → app records it")
        amt = (await c.position(sym))["amt"]
        await c.market_order(sym, "SELL", amt, reduce_only=True)  # what a human would do
        await asyncio.sleep(1.5)
        await ex2.on_price(mark)  # reconcile
        [pos] = await db_positions(sym)
        rec("CLOSED as EXTERNAL", pos.status == "CLOSED" and pos.exit_reason == "EXTERNAL",
            f"exit {pos.exit_price} pnl {pos.pnl}")
        await asyncio.sleep(0.5)
        rec("leftover SL/TP cancelled", not await algo_ids(c, sym))

        # S5 ------------------------------------------------------------------------------
        print("S5 reversal + signal close")
        await ex2.submit(Signal("SELL", sym, size=qty, sl=mark * 1.02, tp=mark * 0.98))
        rec("SHORT opened", (await c.position(sym))["amt"] < 0)
        await ex2.submit(Signal("BUY", sym, size=qty, sl=mark * 0.98, tp=mark * 1.02))
        p = await c.position(sym)
        ids = await algo_ids(c, sym)
        rec("reversed to LONG (close then open)", p["amt"] > 0 and abs(p["amt"]) == qty,
            f"amt {p['amt']}")
        rec("only the new SL/TP remain", ids == set(ex2._protect.values()) and len(ids) == 2)
        await ex2.submit(Signal("CLOSE", sym))
        await asyncio.sleep(0.5)
        rec("signal close → flat, no orders", (await c.position(sym))["amt"] == 0
            and not await algo_ids(c, sym))
        poss = await db_positions(sym)
        rec("DB: 3 trades, all CLOSED", len(poss) == 3 and all(x.status == "CLOSED" for x in poss))

        # S6 ------------------------------------------------------------------------------
        print("S6 untracked position on the exchange")
        await c.market_order(sym, "BUY", qty)  # opened outside the app
        try:
            await ex2.submit(Signal("SELL", sym, size=qty, sl=mark * 1.02))
            rec("refused to trade into it", False, "order was sent!")
        except ExchangeOrderError as e:
            rec("refused to trade into it", True, str(e)[:70])
        await flatten(c, sym)
        ex3 = new_exec()
        await c.market_order(sym, "BUY", qty)
        while not risk.empty():
            risk.get_nowait()
        await ex3.restore_open()
        rec("startup alert for untracked position", not risk.empty())
        await flatten(c, sym)

        # S7 ------------------------------------------------------------------------------
        print(f"S7 SL/TP filled ON the exchange (±{S7_PCT:.2%}, up to 120 s)")
        m = float((await c._raw.futures_mark_price(symbol=sym))["markPrice"])
        await ex2.on_price(m)
        await ex2.submit(Signal("BUY", sym, size=qty, sl=m * (1 - S7_PCT), tp=m * (1 + S7_PCT)))
        done = False
        for _ in range(40):
            await asyncio.sleep(3)
            await ex2.on_price(float((await c._raw.futures_mark_price(symbol=sym))["markPrice"]))
            if ex2.engine.position is None:
                done = True
                break
        if done:
            last = (await db_positions(sym))[-1]
            rec("SL/TP fill detected", last.exit_reason in ("SL", "TP"),
                f"{last.exit_reason} @ {last.exit_price} pnl {float(last.pnl):+.5f}")
            await asyncio.sleep(0.5)
            rec("other leg cancelled", not await algo_ids(c, sym))
        else:
            rec("SL/TP fill detected", None, f"price didn't reach ±{S7_PCT:.2%} in 120 s")
            await ex2.submit(Signal("CLOSE", sym))

        # S8 ------------------------------------------------------------------------------
        print("S8 ledger vs exchange wallet")
        await asyncio.sleep(3)  # income history lags a little
        await svc.sync_exchange(acc_id, client=c)
        async with async_session() as s:
            a = await s.get(Account, acc_id)
            total = float((await s.execute(select(func.sum(AccountTxn.amount)).where(
                AccountTxn.account_id == acc_id))).scalar_one())
            types = dict((await s.execute(select(AccountTxn.type, func.count()).where(
                AccountTxn.account_id == acc_id).group_by(AccountTxn.type))).all())
        wallet = (await c.account())["wallet"]
        rec("ledger sum == exchange wallet", abs(total - wallet) < 1e-6,
            f"ledger {total:.6f} · wallet {wallet:.6f}")
        rec("fees + realized PnL imported", types.get("FEE", 0) > 0 and types.get(
            "REALIZED_PNL", 0) > 0, str(types))
        rec("no sync error", a.sync_error is None)
    except Exception as e:  # noqa: BLE001
        rec("unexpected error", False, f"{type(e).__name__}: {getattr(e, 'message', e)}")
    finally:
        await flatten(c, sym)
        await cleanup_db(sym)
        await c.close()

    n_fail = sum(1 for r in results if r[0] == "FAIL")
    print(f"\n{len(results) - n_fail}/{len(results)} passed · {n_fail} failed · "
          f"{(int(time.time() * 1000) - t_start) / 1000:.0f}s")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
