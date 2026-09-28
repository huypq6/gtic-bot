"""Binance Futures adapter (mock AsyncClient): exchange rules, order params, exchange SL/TP."""

import pytest

from app.config import Settings
from app.execution.binance_futures import (
    BinanceFuturesClient,
    ExchangeReject,
    SymbolRules,
    parse_rules,
)
from app.execution.clients import check_mode

INFO = {"symbols": [{
    "symbol": "BTCUSDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
        {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
        {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
        {"filterType": "MIN_NOTIONAL", "notional": "100"},
    ],
}]}


class FakeRaw:
    def __init__(self):
        self.calls = []

    async def futures_exchange_info(self):
        return INFO

    async def futures_change_leverage(self, **kw):
        self.calls.append(("lev", kw))

    async def futures_create_order(self, **kw):
        self.calls.append(("order", kw))
        if kw["type"] in ("STOP_MARKET", "TAKE_PROFIT_MARKET"):
            return {"algoId": 900 + len(self.calls), "algoStatus": "NEW"}
        return {"orderId": 11, "avgPrice": "84000.5", "executedQty": kw["quantity"],
                "status": "FILLED"}

    async def futures_cancel_algo_order(self, **kw):
        self.calls.append(("cancel_algo", kw))

    async def futures_position_information(self, **kw):
        return [{"positionAmt": "-0.012", "entryPrice": "84100"}]

    async def futures_account_trades(self, **kw):
        return [
            {"orderId": 5, "qty": "0.01", "price": "100", "realizedPnl": "0", "commission": "0.1",
             "time": 1},
            {"orderId": 7, "qty": "0.006", "price": "95", "realizedPnl": "-3", "commission": "0.03",
             "time": 2},
            {"orderId": 7, "qty": "0.004", "price": "94", "realizedPnl": "-2.4",
             "commission": "0.02", "time": 3},
        ]

    async def futures_account(self):
        return {"totalWalletBalance": "1000", "totalMarginBalance": "990",
                "totalUnrealizedProfit": "-10", "totalInitialMargin": "200",
                "availableBalance": "790"}

    async def futures_income_history(self, **kw):
        self.calls.append(("income", kw))
        return [{"tranId": 1, "incomeType": "COMMISSION", "income": "-0.5", "asset": "USDT",
                 "symbol": "BTCUSDT", "time": 10}]


def test_rules_round_and_check():
    r = parse_rules(INFO)["BTCUSDT"]
    assert r == SymbolRules(step=0.001, min_qty=0.001, tick=0.1, min_notional=100)
    assert r.qty(0.0129) == 0.012  # rounds DOWN to the step
    assert r.price(84123.26) == 84123.3
    with pytest.raises(ExchangeReject, match="minimum"):
        r.check(0.001, 84000)  # 84 USDT < 100
    with pytest.raises(ExchangeReject):
        r.check(0.0, 84000)


async def test_market_order_params_and_reduce_only():
    raw = FakeRaw()
    c = BinanceFuturesClient(raw, testnet=True)
    r = await c.market_order("BTCUSDT", "BUY", 0.0129)
    kw = raw.calls[-1][1]
    assert kw["quantity"] == 0.012 and kw["newOrderRespType"] == "RESULT"
    assert "reduceOnly" not in kw
    assert r == {"orderId": "11", "price": 84000.5, "status": "FILLED", "qty": 0.012}
    await c.market_order("BTCUSDT", "SELL", 0.012, reduce_only=True)
    assert raw.calls[-1][1]["reduceOnly"] == "true"


async def test_protect_places_close_position_stop_and_tp():
    raw = FakeRaw()
    c = BinanceFuturesClient(raw, testnet=True)
    ids = await c.protect("BTCUSDT", "LONG", sl=83000.04, tp=86000.06)
    orders = [kw for t, kw in raw.calls if t == "order"]
    assert [o["type"] for o in orders] == ["STOP_MARKET", "TAKE_PROFIT_MARKET"]
    assert all(o["side"] == "SELL" and o["closePosition"] == "true" for o in orders)
    assert orders[0]["stopPrice"] == 83000.0 and orders[1]["stopPrice"] == 86000.1
    assert ids["sl"] and ids["tp"]
    await c.cancel_protection("BTCUSDT", ids)
    assert sum(1 for t, _ in raw.calls if t == "cancel_algo") == 2


async def test_leverage_set_once_per_symbol():
    raw = FakeRaw()
    c = BinanceFuturesClient(raw, testnet=True)
    await c.ensure_leverage("BTCUSDT", 5)
    await c.ensure_leverage("BTCUSDT", 5)
    await c.ensure_leverage("BTCUSDT", 3)
    assert [kw["leverage"] for t, kw in raw.calls if t == "lev"] == [5, 3]


async def test_state_reads():
    c = BinanceFuturesClient(FakeRaw(), testnet=True)
    assert await c.position("BTCUSDT") == {"amt": -0.012, "entry": 84100.0}
    f = await c.last_close_fill("BTCUSDT", 0)
    assert f["orderId"] == "7" and f["qty"] == pytest.approx(0.01)
    assert f["price"] == pytest.approx(94.6) and f["realized"] == pytest.approx(-5.4)
    assert f["fee"] == pytest.approx(0.05)
    a = await c.account()
    assert a == {"wallet": 1000, "equity": 990, "unrealized": -10, "margin": 200,
                 "available": 790}
    inc = await c.income(5)
    assert inc[0]["ext_id"] == "1:COMMISSION" and inc[0]["amount"] == -0.5


def test_check_mode_guards():
    with pytest.raises(ValueError, match="ENABLE_LIVE"):
        check_mode("LIVE", Settings(enable_live=False, binance_key="k", binance_secret="s"))
    with pytest.raises(ValueError, match="BINANCE_TESTNET_KEY"):
        check_mode("TESTNET", Settings(binance_testnet_key="", binance_testnet_secret=""))
    check_mode("TESTNET", Settings(binance_testnet_key="k", binance_testnet_secret="s"))
