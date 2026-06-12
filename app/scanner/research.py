"""Scanner — quét cặp định kỳ, chấm điểm + đề xuất tín hiệu (US-22).

`score_symbol` thuần (testable): RSI + momentum → (score, signal, reason).
Task nền `run_scanner` chạy mỗi `scan_interval_sec`: sync nến → chấm → lưu
`scan_result` → publish topic `scan` lên bus (WSGateway forward xuống UI).
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.market.bus import EventBus
from app.market.store import get_klines, sync_historical
from app.orders.models import ScanResult
from app.strategy.ta import atr, rsi

logger = logging.getLogger(__name__)


def score_symbol(closes: list[float], rsi_period: int = 14) -> tuple[float, str, str]:
    """Chấm điểm 1 cặp từ chuỗi close. score 0..100 (độ mạnh tín hiệu)."""
    if len(closes) < rsi_period + 2:
        return 0.0, "NEUTRAL", "thiếu dữ liệu"
    r = rsi(closes, rsi_period)
    last_rsi = r[-1] if r else 50.0
    # momentum: % thay đổi 10 nến gần nhất.
    lookback = min(10, len(closes) - 1)
    mom = (closes[-1] - closes[-1 - lookback]) / closes[-1 - lookback] * 100

    if last_rsi < 30:
        signal = "BUY"
        score = min(100.0, (30 - last_rsi) * 2 + abs(mom))
    elif last_rsi > 70:
        signal = "SELL"
        score = min(100.0, (last_rsi - 70) * 2 + abs(mom))
    else:
        signal = "NEUTRAL"
        score = abs(last_rsi - 50)
    reason = f"RSI={last_rsi:.1f}, mom10={mom:+.2f}%"
    return round(score, 2), signal, reason


def analyze_symbol(candles: list[dict], rsi_period: int = 14) -> dict:
    """Chấm điểm + đề xuất entry/SL/TP (theo ATR) cho 1 cặp."""
    closes = [c["close"] for c in candles]
    score, signal, reason = score_symbol(closes, rsi_period)
    entry = closes[-1] if closes else None
    atr_val = atr(candles)
    sl = tp = None
    if signal in ("BUY", "SELL") and entry and atr_val:
        if signal == "BUY":
            sl = round(entry - settings.scan_sl_atr * atr_val, 6)
            tp = round(entry + settings.scan_tp_atr * atr_val, 6)
        else:
            sl = round(entry + settings.scan_sl_atr * atr_val, 6)
            tp = round(entry - settings.scan_tp_atr * atr_val, 6)
    return {
        "score": score, "signal": signal, "reason": reason,
        "entry": round(entry, 6) if entry else None,
        "atr": round(atr_val, 6) if atr_val else None,
        "sl": sl, "tp": tp,
    }


async def scan_once(session_factory: async_sessionmaker) -> list[dict]:
    """Quét 1 lượt các symbol cấu hình → lưu scan_result, trả về list kết quả."""
    results: list[dict] = []
    async with session_factory() as session:
        for symbol in settings.scan_symbols:
            try:
                await sync_historical(session, symbol, settings.scan_tf, "1 day ago UTC")
                candles = await get_klines(session, symbol, settings.scan_tf, limit=100)
                a = analyze_symbol(candles)
                session.add(
                    ScanResult(
                        symbol=symbol, score=a["score"], signal=a["signal"], reason=a["reason"],
                        entry=a["entry"], atr=a["atr"], sl=a["sl"], tp=a["tp"],
                    )
                )
                results.append({"symbol": symbol, **a})
            except Exception:  # noqa: BLE001 — 1 symbol lỗi không chặn cả lượt
                logger.exception("scan %s lỗi", symbol)
        await session.commit()
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


async def run_scanner(bus: EventBus, session_factory: async_sessionmaker) -> None:
    """Task nền: quét định kỳ + publish 'scan'. Hủy qua CancelledError."""
    while True:
        try:
            results = await scan_once(session_factory)
            await bus.publish("scan", {"type": "scan", "results": results})
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("vòng quét scanner lỗi")
        await asyncio.sleep(settings.scan_interval_sec)
