"""Walk-forward rổ 15m cho ict_po3 v3 (params CỐ ĐỊNH) — kiểm tra edge ổn định theo THỜI GIAN.

Chạy:  PYTHONPATH=. uv run python scripts/walkforward_ict_po3.py

Chia lịch sử mỗi cặp thành N cửa sổ tuần tự, chạy bộ params mặc định trên TỪNG cửa sổ.
Không re-optimize (params đã chốt) → đây là out-of-sample theo thời gian: nếu rổ dương ở ĐA SỐ
cửa sổ thì edge ổn định; nếu chỉ dương 1–2 cửa sổ thì là may theo regime.
"""

import asyncio
from datetime import datetime, timezone

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical
from app.strategy.registry import discover, get

BASKET = ["ETHUSDT", "SOLUSDT", "DOTUSDT", "DOGEUSDT", "AVAXUSDT", "XRPUSDT", "LTCUSDT", "ADAUSDT"]
TF = "15m"
HISTORY = "180 days ago UTC"
N_WINDOWS = 6
FEE = 0.0005


def _d(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%m-%d")


async def main() -> None:
    discover()
    params = dict(get("ict_po3", "3").default_params)
    print(f"params v3 (cố định): conf={params['confluence']} sl=ATR×{params['atr_mult']} "
          f"tp_mode={params['tp_mode']} bias_len={params['bias_len']}\n")

    data: dict = {}
    async with async_session() as s:
        for sym in BASKET:
            try:
                await sync_historical(s, sym, TF, HISTORY)
                await s.commit()
                c = await get_klines(s, sym, TF, limit=40000)
            except Exception:  # noqa: BLE001
                print(f"  {sym}: sync lỗi"); continue
            if len(c) >= N_WINDOWS * 300:
                data[sym] = c
            else:
                print(f"  {sym}: thiếu dữ liệu ({len(c)})")
    print(f"  …nạp xong {len(data)} cặp\n")

    # pnl[sym][w]
    pnl: dict = {sym: [None] * N_WINDOWS for sym in data}
    win_labels = [None] * N_WINDOWS
    for sym, candles in data.items():
        sz = len(candles) // N_WINDOWS
        for w in range(N_WINDOWS):
            chunk = candles[w * sz:(w + 1) * sz] if w < N_WINDOWS - 1 else candles[w * sz:]
            if len(chunk) < 300:
                continue
            if win_labels[w] is None:
                win_labels[w] = f"{_d(chunk[0]['ts'])}→{_d(chunk[-1]['ts'])}"
            try:
                r = run_backtest("ict_po3", "3", params, chunk, 1000.0, FEE, TF, 1)
                pnl[sym][w] = r["pnl_pct"]
            except Exception:  # noqa: BLE001
                pass

    # Ma trận symbol × window
    print(f"{'='*88}\nPnL% theo cửa sổ (15m, {N_WINDOWS} kỳ ~30 ngày):")
    head = "  " + f"{'symbol':<9}" + "".join(f"{(win_labels[w] or '?'):>13}" for w in range(N_WINDOWS)) + f"{'#dương':>8}"
    print(head)
    for sym in data:
        vals = pnl[sym]
        cells = "".join((f"{v:>13.2f}" if v is not None else f"{'—':>13}") for v in vals)
        npos = sum(1 for v in vals if v is not None and v > 0)
        print(f"  {sym:<9}{cells}{npos:>6}/{N_WINDOWS}")

    # Tổng hợp theo cửa sổ
    print(f"\n{'-'*88}\nTheo cửa sổ (rổ {len(data)} cặp):")
    print(f"  {'cửa sổ':<14}{'PnL TB%':>9}{'#cặp dương':>13}")
    good_windows = 0
    for w in range(N_WINDOWS):
        vs = [pnl[sym][w] for sym in data if pnl[sym][w] is not None]
        if not vs:
            continue
        mean = sum(vs) / len(vs)
        npos = sum(1 for v in vs if v > 0)
        if mean > 0:
            good_windows += 1
        print(f"  {(win_labels[w] or '?'):<14}{mean:>9.2f}{npos:>9}/{len(vs)}")

    # Tổng hợp theo cặp
    print(f"\n{'-'*88}\nTheo cặp (qua {N_WINDOWS} cửa sổ):")
    stable = []
    for sym in data:
        vs = [v for v in pnl[sym] if v is not None]
        if not vs:
            continue
        mean = sum(vs) / len(vs)
        npos = sum(1 for v in vs if v > 0)
        if npos >= (len(vs) + 1) // 2 + 1:  # dương > nửa số cửa sổ
            stable.append(sym)
        print(f"  {sym:<9} TB {mean:>6.2f}%  dương {npos}/{len(vs)} cửa sổ")

    print(f"\n{'='*88}")
    print(f"KẾT LUẬN: {good_windows}/{N_WINDOWS} cửa sổ rổ DƯƠNG trung bình.")
    print(f"Cặp ỔN ĐỊNH (dương > nửa số cửa sổ): {', '.join(stable) if stable else 'KHÔNG cặp nào'}")
    print("⚠️  Params cố định (không re-optimize). Edge yếu — cần thêm bằng chứng trước tiền thật.")


if __name__ == "__main__":
    asyncio.run(main())
