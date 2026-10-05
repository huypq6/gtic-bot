"""Cross-mode comparison (docs/08): the same strategy across PAPER / TESTNET / LIVE and versions.

Pure (no DB) for testing. Input = closed trades as dicts:
  {mode, strategy ("ict_po3 v4"), symbol, tf, side, qty, entry, exit, pnl, fee, init_sl,
   opened_ms, bot_ref}
"""

from collections import defaultdict
from dataclasses import dataclass

MODES = ("LIVE", "TESTNET", "PAPER")  # display order: real money first
# divergence pairs (A vs B): A is the "more real" side, B the reference
_DIV_PAIRS = (("LIVE", "PAPER"), ("LIVE", "TESTNET"), ("TESTNET", "PAPER"))


def split_strategy(label: str | None) -> tuple[str, str]:
    """'ict_po3 v4' → ('ict_po3', '4'); a label without a version → (label, '')."""
    if not label:
        return "", ""
    name, sep, ver = label.rpartition(" v")
    return (name, ver) if sep and name else (label, "")


def trade_r(t: dict) -> float | None:
    """Net PnL in R (1R = |entry − initial SL| × qty), same definition as Trade results."""
    if t.get("pnl") is None or t.get("init_sl") is None or not t.get("qty"):
        return None
    risk = abs(t["entry"] - t["init_sl"]) * t["qty"]
    return t["pnl"] / risk if risk else None


def _stats(trades: list[dict]) -> dict:
    rs = [r for r in (trade_r(t) for t in trades) if r is not None]
    wins = sum(1 for t in trades if (t.get("pnl") or 0) > 0)
    n = len(trades)
    return {
        "trades": n,
        "wins": wins,
        "win_rate": wins / n * 100 if n else None,
        "sum_r": sum(rs) if rs else None,
        "avg_r": sum(rs) / len(rs) if rs else None,
        "pnl": sum(t.get("pnl") or 0 for t in trades),
        "fees": sum(t.get("fee") or 0 for t in trades),
        "bots": sorted({t["bot_ref"] for t in trades if t.get("bot_ref") is not None}),
    }


@dataclass
class Pairing:
    pairs: list[tuple[dict, dict]]
    only_a: list[dict]
    only_b: list[dict]


def pair_trades(a: list[dict], b: list[dict], window_ms: int) -> Pairing:
    """Match each A trade to the nearest-in-time unused B trade with the same side and
    |Δopen| ≤ window. Greedy over all candidate pairs by time distance → one-to-one."""
    cand = [
        (abs(ta["opened_ms"] - tb["opened_ms"]), i, j)
        for i, ta in enumerate(a)
        for j, tb in enumerate(b)
        if ta["side"] == tb["side"] and abs(ta["opened_ms"] - tb["opened_ms"]) <= window_ms
    ]
    cand.sort()
    used_a: set[int] = set()
    used_b: set[int] = set()
    pairs = []
    for _, i, j in cand:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append((a[i], b[j]))
    pairs.sort(key=lambda p: p[0]["opened_ms"])
    return Pairing(
        pairs=pairs,
        only_a=[t for i, t in enumerate(a) if i not in used_a],
        only_b=[t for j, t in enumerate(b) if j not in used_b],
    )


def slip_bps(side: str, price_a: float, price_b: float, *, entry: bool) -> float:
    """Adverse slippage of A vs B in bps (positive = A got the worse price).
    LONG entry / SHORT exit: paying more is worse.
    SHORT entry / LONG exit: receiving less is worse."""
    if not price_b:
        return 0.0
    buy = (side == "LONG") == entry
    diff = (price_a - price_b) if buy else (price_b - price_a)
    return diff / price_b * 10_000


def _divergence(a: list[dict], b: list[dict], window_ms: int) -> dict:
    p = pair_trades(a, b, window_ms)
    ent = [slip_bps(x["side"], x["entry"], y["entry"], entry=True) for x, y in p.pairs]
    ext = [
        slip_bps(x["side"], x["exit"], y["exit"], entry=False)
        for x, y in p.pairs
        if x.get("exit") is not None and y.get("exit") is not None
    ]
    rd = [
        ra - rb
        for ra, rb in ((trade_r(x), trade_r(y)) for x, y in p.pairs)
        if ra is not None and rb is not None
    ]

    def avg(v: list[float]) -> float | None:
        return sum(v) / len(v) if v else None

    return {
        "paired": len(p.pairs),
        "only_a": len(p.only_a),
        "only_b": len(p.only_b),
        "entry_slip_bps": avg(ent),
        "exit_slip_bps": avg(ext),
        "r_diff": avg(rd),
    }


def compare(trades: list[dict], tf_ms: dict[str, int]) -> list[dict]:
    """Group closed trades by (strategy name, symbol, tf) → per (mode, version) stats +
    divergence between modes running the same version. Manual trades (no strategy) skipped."""
    groups: dict[tuple, dict[tuple, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for t in trades:
        name, ver = split_strategy(t.get("strategy"))
        if not name:
            continue
        groups[(name, t["symbol"], t.get("tf") or "")][(t["mode"], ver)].append(t)

    out = []
    for (name, symbol, tf), by in groups.items():
        order = {m: i for i, m in enumerate(MODES)}
        keys = sorted(by, key=lambda k: (order.get(k[0], 9), k[1]))
        rows = [{"mode": m, "version": v, **_stats(by[(m, v)])} for m, v in keys]
        window = tf_ms.get(tf, 60_000)
        div = []
        for ma, mb in _DIV_PAIRS:
            for v in sorted({v for m, v in by if m == ma} & {v for m, v in by if m == mb}):
                div.append({"a": ma, "b": mb, "version": v,
                            **_divergence(by[(ma, v)], by[(mb, v)], window)})
        out.append({"strategy": name, "symbol": symbol, "tf": tf, "rows": rows,
                    "divergence": div,
                    "trades": sum(r["trades"] for r in rows)})
    out.sort(key=lambda g: (-g["trades"], g["strategy"], g["symbol"]))
    return out
