"""Quét tham số ict_po3 trên dữ liệu thật (in-process, không ghi DB).

Chạy:  uv run python scripts/sweep_ict_po3.py

Xếp hạng theo ĐỘ BỀN (số thị trường có lời) rồi tới PnL trung bình — ưu tiên bộ tham số
chạy ổn trên NHIỀU cặp/khung hơn là đỉnh cục bộ 1 thị trường (giảm overfit).
"""

import asyncio

from app.backtest.engine import run_backtest
from app.db import async_session
from app.market.store import get_klines, sync_historical

# (symbol, tf, cửa sổ lịch sử)
MARKETS = [
    ("BTCUSDT", "15m", "45 days ago UTC"),
    ("ETHUSDT", "15m", "45 days ago UTC"),
    ("BTCUSDT", "1h", "120 days ago UTC"),
    ("ETHUSDT", "1h", "120 days ago UTC"),
]
FEE = 0.0005          # taker Futures (1 chiều)
MIN_TOTAL_TRADES = 20  # bộ nào quá ít lệnh → loại (không đủ mẫu)


def build_grid() -> list[dict]:
    grid = []
    for conf in (2, 3):                       # 2=retest FVG, 3=+OB
        for tp_mode, rrs in ((0, (1.5, 2.0, 3.0)), (1, (2.0,))):  # tp_mode=1: rr chỉ là fallback
            for rr in rrs:
                for bias_len in (100, 200):
                    for mss in (2, 3):
                        for swing in (1, 2, 3):   # nửa-độ-rộng fractal cho MSS (swing-structure)
                            grid.append({
                                "bias_mode": 1, "confluence": conf, "tp_mode": tp_mode,
                                "rr_target": rr, "bias_len": bias_len, "mss_lookback": mss,
                                "swing": swing, "news_filter": 2, "sl_buffer_pct": 0.05, "size": 0.001,
                            })
    return grid


async def load_data() -> dict:
    data = {}
    async with async_session() as s:
        for sym, tf, start in MARKETS:
            await sync_historical(s, sym, tf, start)
            await s.commit()
            candles = await get_klines(s, sym, tf, limit=20000)
            data[(sym, tf)] = candles
            print(f"  data {sym} {tf}: {len(candles)} nến")
    return data


def evaluate(params: dict, data: dict) -> dict:
    pnls, wins, trades, worst_dd = [], [], 0, 0.0
    pos = 0
    for (sym, tf), candles in data.items():
        try:
            r = run_backtest("ict_po3", "1", params, candles, 1000.0, FEE, tf, 1)
        except Exception:  # noqa: BLE001
            continue
        pnls.append(r["pnl_pct"])
        if r["winrate"] is not None:
            wins.append(r["winrate"])
        trades += r["n_trades"] or 0
        worst_dd = max(worst_dd, r["max_dd"] or 0.0)
        if (r["pnl_pct"] or 0) > 0:
            pos += 1
    if not pnls:
        return {}
    return {
        "params": params,
        "mean_pnl": sum(pnls) / len(pnls),
        "worst_pnl": min(pnls),
        "pos": pos,                       # số thị trường có lời
        "mean_win": sum(wins) / len(wins) if wins else 0.0,
        "trades": trades,
        "max_dd": worst_dd,
    }


def fmt(p: dict) -> str:
    return (f"conf={p['confluence']} tp={p['tp_mode']} rr={p['rr_target']} "
            f"bias_len={p['bias_len']} mss={p['mss_lookback']} swing={p['swing']}")


async def main() -> None:
    print("Nạp dữ liệu (sync Binance nếu thiếu)…")
    data = await load_data()
    grid = build_grid()
    print(f"\nQuét {len(grid)} bộ tham số × {len(MARKETS)} thị trường = {len(grid) * len(MARKETS)} backtest…\n")

    results = []
    for i, params in enumerate(grid, 1):
        r = evaluate(params, data)
        if r:
            results.append(r)
        if i % 12 == 0:
            print(f"  …{i}/{len(grid)}")

    elig = [r for r in results if r["trades"] >= MIN_TOTAL_TRADES]
    # bền trước (nhiều thị trường lời), rồi PnL trung bình, rồi worst-case đỡ tệ.
    elig.sort(key=lambda r: (r["pos"], r["mean_pnl"], r["worst_pnl"]), reverse=True)

    print(f"\n{'='*92}\nTOP 15 (lọc ≥{MIN_TOTAL_TRADES} lệnh; xếp theo #thị-trường-lời, rồi PnL TB):")
    print(f"{'#thị-trường-lời':>15} {'PnL_TB%':>9} {'worst%':>8} {'win%':>6} {'lệnh':>5} {'maxDD%':>7}  params")
    for r in elig[:15]:
        print(f"{r['pos']:>13}/4 {r['mean_pnl']:>9.2f} {r['worst_pnl']:>8.2f} "
              f"{r['mean_win']:>6.1f} {r['trades']:>5} {r['max_dd']:>7.2f}  {fmt(r['params'])}")

    if elig:
        best = elig[0]
        print(f"\n{'='*92}\nĐỀ XUẤT (bền nhất): {fmt(best['params'])}")
        print(f"  PnL TB {best['mean_pnl']:.2f}% · lời {best['pos']}/4 thị trường · "
              f"win {best['mean_win']:.1f}% · {best['trades']} lệnh · maxDD {best['max_dd']:.2f}%")
        print(f"  params = {best['params']}")
        best_pnl = max(elig, key=lambda r: r["mean_pnl"])
        if best_pnl is not best:
            print(f"\nPnL TB cao nhất (có thể kém bền): {fmt(best_pnl['params'])} "
                  f"→ {best_pnl['mean_pnl']:.2f}% TB, lời {best_pnl['pos']}/4")
    else:
        print("\nKhông bộ nào đủ số lệnh tối thiểu — nới MIN_TOTAL_TRADES hoặc cửa sổ dữ liệu.")
    print("\n⚠️  Đây là tối ưu IN-SAMPLE → có thể overfit. Nên kiểm chứng out-of-sample (cửa sổ khác).")


if __name__ == "__main__":
    asyncio.run(main())
