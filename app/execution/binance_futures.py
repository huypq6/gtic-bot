"""Adapter Binance USDⓈ-M Futures (P9b) — testnet (testnet.binancefuture.com) & live.

Why Futures (not Spot): strategies go SHORT, and paper + backtest both simulate USDT-M
Futures → real orders must be on the same market for results to be comparable.

Normalization for ExchangeExecutor/AccountService:
- Round quantity down to stepSize and price to tickSize; enforce minQty/minNotional floors.
- MARKET uses `newOrderRespType=RESULT` → avgPrice/executedQty are available immediately.
- SL/TP placed ON THE EXCHANGE: STOP_MARKET / TAKE_PROFIT_MARKET `closePosition=true`
  (python-binance routes these to the Algo Order endpoint, returning `algoId`)
  → positions stay protected even if the app dies.
- Closing always uses `reduceOnly` → never accidentally opens an opposite position.
- Balance/margin/unrealized PnL from `futures_account`, ledger from `futures_income_history`.

All network calls are concentrated here → tested with a fake client exposing the same interface.
"""

import logging
import math
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ExchangeReject(Exception):
    """Exchange / exchange rules rejected the order (quantity too small, invalid tick size…)."""


@dataclass
class SymbolRules:
    step: float  # quantity step (LOT_SIZE / MARKET_LOT_SIZE)
    min_qty: float
    tick: float  # price step (PRICE_FILTER)
    min_notional: float  # MIN_NOTIONAL.notional

    @staticmethod
    def _floor(v: float, step: float) -> float:
        if step <= 0:
            return v
        n = math.floor(v / step + 1e-9)
        return round(n * step, max(0, -int(math.floor(math.log10(step)))))

    def qty(self, v: float) -> float:
        return self._floor(v, self.step)

    def price(self, v: float) -> float:
        if self.tick <= 0:
            return v
        n = round(v / self.tick)
        return round(n * self.tick, max(0, -int(math.floor(math.log10(self.tick)))))

    def check(self, qty: float, price: float) -> None:
        if qty < self.min_qty or qty <= 0:
            raise ExchangeReject(f"quantity {qty} < minimum {self.min_qty}")
        if price and qty * price < self.min_notional:
            raise ExchangeReject(
                f"order notional {qty * price:.2f} < minimum {self.min_notional:g} USDT"
            )


def parse_rules(info: dict) -> dict[str, SymbolRules]:
    out: dict[str, SymbolRules] = {}
    for s in info.get("symbols", []):
        f = {x["filterType"]: x for x in s.get("filters", [])}
        lot = f.get("MARKET_LOT_SIZE") or f.get("LOT_SIZE") or {}
        out[s["symbol"]] = SymbolRules(
            step=float(lot.get("stepSize", 0) or f.get("LOT_SIZE", {}).get("stepSize", 0)),
            min_qty=float(lot.get("minQty", 0)),
            tick=float(f.get("PRICE_FILTER", {}).get("tickSize", 0)),
            min_notional=float(f.get("MIN_NOTIONAL", {}).get("notional", 5)),
        )
    return out


class BinanceFuturesClient:
    market = "FUTURES"

    def __init__(self, raw, testnet: bool) -> None:
        self._raw = raw  # binance.AsyncClient
        self.testnet = testnet
        self._rules: dict[str, SymbolRules] = {}
        self._leverage: dict[str, int] = {}

    @classmethod
    async def create(cls, api_key: str, api_secret: str, testnet: bool) -> "BinanceFuturesClient":
        from binance import AsyncClient

        raw = await AsyncClient.create(api_key, api_secret, testnet=testnet)
        return cls(raw, testnet)

    async def close(self) -> None:
        await self._raw.close_connection()

    # ---------- exchange rules ----------
    async def rules(self, symbol: str) -> SymbolRules:
        if symbol not in self._rules:
            self._rules.update(parse_rules(await self._raw.futures_exchange_info()))
        if symbol not in self._rules:
            raise ExchangeReject(f"{symbol} is not listed on Binance Futures")
        return self._rules[symbol]

    async def ensure_leverage(self, symbol: str, leverage: float) -> None:
        lev = max(1, int(leverage))
        if self._leverage.get(symbol) != lev:
            await self._raw.futures_change_leverage(symbol=symbol, leverage=lev)
            self._leverage[symbol] = lev

    # ---------- orders ----------
    @staticmethod
    def _norm(resp: dict) -> dict:
        avg = float(resp.get("avgPrice") or 0) or float(resp.get("price") or 0)
        return {
            "orderId": str(resp.get("orderId") or resp.get("algoId")),
            "price": avg,
            "status": resp.get("status") or resp.get("algoStatus") or "NEW",
            "qty": float(resp.get("executedQty") or resp.get("origQty") or 0.0),
        }

    async def market_order(
        self, symbol: str, side: str, qty: float, reduce_only: bool = False
    ) -> dict:
        r = await self.rules(symbol)
        q = r.qty(qty)
        r.check(q, 0)
        params = dict(symbol=symbol, side=side, type="MARKET", quantity=q,
                      newOrderRespType="RESULT")
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._norm(await self._raw.futures_create_order(**params))

    async def limit_order(self, symbol: str, side: str, qty: float, price: float) -> dict:
        r = await self.rules(symbol)
        q, p = r.qty(qty), r.price(price)
        r.check(q, p)
        return self._norm(await self._raw.futures_create_order(
            symbol=symbol, side=side, type="LIMIT", timeInForce="GTC", quantity=q, price=p,
        ))

    async def protect(
        self, symbol: str, side: str, sl: float | None, tp: float | None
    ) -> dict[str, str | None]:
        """Place SL/TP on the exchange for position `side` (LONG/SHORT).

        Returns {"sl": algoId, "tp": algoId}."""
        r = await self.rules(symbol)
        close_side = "SELL" if side == "LONG" else "BUY"
        out: dict[str, str | None] = {"sl": None, "tp": None}
        for key, px, typ in (("sl", sl, "STOP_MARKET"), ("tp", tp, "TAKE_PROFIT_MARKET")):
            if px is None:
                continue
            resp = await self._raw.futures_create_order(
                symbol=symbol, side=close_side, type=typ, stopPrice=r.price(px),
                closePosition="true", workingType="MARK_PRICE",
            )
            out[key] = str(resp.get("algoId") or resp.get("orderId"))
        return out

    async def cancel(self, symbol: str, order_id: str) -> None:
        await self._raw.futures_cancel_order(symbol=symbol, orderId=order_id)

    async def cancel_protection(self, symbol: str, ids: dict) -> None:
        for oid in (ids or {}).values():
            if not oid:
                continue
            try:
                await self._raw.futures_cancel_algo_order(symbol=symbol, algoId=oid)
            except Exception as e:  # noqa: BLE001 — already filled/cancelled → ignore
                logger.info("cancel SL/TP %s %s: %s", symbol, oid, e)

    # ---------- state ----------
    async def position(self, symbol: str) -> dict:
        """{"amt": signed quantity (+LONG/−SHORT), "entry": entry price}."""
        rows = await self._raw.futures_position_information(symbol=symbol)
        amt = sum(float(r.get("positionAmt") or 0) for r in rows)
        open_rows = [r for r in rows if float(r.get("positionAmt") or 0)]
        entry = float(open_rows[0]["entryPrice"]) if open_rows else 0.0
        return {"amt": amt, "entry": entry}

    async def last_close_fill(self, symbol: str, since_ms: int) -> dict | None:
        """Most recent closing fill (e.g. exchange SL/TP hit) → avg price + fee + realized PnL."""
        trades = await self._raw.futures_account_trades(symbol=symbol, startTime=since_ms)
        closes = [t for t in trades if float(t.get("realizedPnl") or 0) != 0]
        if not closes:
            return None
        last_id = closes[-1]["orderId"]
        fills = [t for t in closes if t["orderId"] == last_id]
        q = sum(float(t["qty"]) for t in fills)
        return {
            "orderId": str(last_id),
            "price": sum(float(t["price"]) * float(t["qty"]) for t in fills) / q if q else 0.0,
            "qty": q,
            "fee": sum(float(t.get("commission") or 0) for t in fills),
            "realized": sum(float(t.get("realizedPnl") or 0) for t in fills),
            "ts": int(fills[-1]["time"]),
        }

    async def account(self) -> dict:
        a = await self._raw.futures_account()
        return {
            "wallet": float(a.get("totalWalletBalance") or 0),
            "equity": float(a.get("totalMarginBalance") or 0),
            "unrealized": float(a.get("totalUnrealizedProfit") or 0),
            "margin": float(a.get("totalInitialMargin") or 0),
            "available": float(a.get("availableBalance") or 0),
        }

    async def income(self, since_ms: int | None) -> list[dict]:
        """Exchange ledger: REALIZED_PNL, COMMISSION, FUNDING_FEE, TRANSFER… (oldest → newest)."""
        params = {"limit": 1000}
        if since_ms:
            params["startTime"] = since_ms
        rows = await self._raw.futures_income_history(**params)
        return [
            {
                "ext_id": f"{r.get('tranId')}:{r.get('incomeType')}",
                "type": r.get("incomeType"), "amount": float(r.get("income") or 0),
                "asset": r.get("asset"), "symbol": r.get("symbol") or None,
                "ts": int(r.get("time") or 0), "info": r.get("info"),
            }
            for r in rows
        ]
