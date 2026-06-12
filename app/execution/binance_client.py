"""Adapter mỏng quanh python-binance AsyncClient — chuẩn hóa cho Executor.

Testnet & Live dùng chung lớp này, khác nhau ở `testnet` + cặp key. Cô lập để
TestnetExecutor/LiveExecutor test được bằng client giả (cùng interface).
"""

import logging

logger = logging.getLogger(__name__)


class BinanceClient:
    """Bọc AsyncClient. Trả về dict chuẩn: {orderId, price, status, qty}."""

    def __init__(self, raw) -> None:
        self._raw = raw  # binance.AsyncClient

    @classmethod
    async def create(cls, api_key: str, api_secret: str, testnet: bool) -> "BinanceClient":
        from binance import AsyncClient

        raw = await AsyncClient.create(api_key, api_secret, testnet=testnet)
        return cls(raw)

    async def close(self) -> None:
        await self._raw.close_connection()

    @staticmethod
    def _norm(resp: dict) -> dict:
        # avg fill price từ fills (market) hoặc price (limit).
        fills = resp.get("fills") or []
        if fills:
            tot_q = sum(float(f["qty"]) for f in fills)
            avg = sum(float(f["price"]) * float(f["qty"]) for f in fills) / tot_q if tot_q else 0.0
        else:
            avg = float(resp.get("price") or 0.0)
        return {
            "orderId": str(resp.get("orderId")),
            "price": avg,
            "status": resp.get("status", "NEW"),
            "qty": float(resp.get("executedQty") or resp.get("origQty") or 0.0),
        }

    async def market_order(self, symbol: str, side: str, qty: float) -> dict:
        resp = await self._raw.create_order(
            symbol=symbol, side=side, type="MARKET", quantity=qty
        )
        return self._norm(resp)

    async def limit_order(self, symbol: str, side: str, qty: float, price: float) -> dict:
        resp = await self._raw.create_order(
            symbol=symbol, side=side, type="LIMIT", timeInForce="GTC",
            quantity=qty, price=price,
        )
        return self._norm(resp)

    async def cancel(self, symbol: str, order_id: str) -> None:
        await self._raw.cancel_order(symbol=symbol, orderId=order_id)
