import { useQuery } from "@tanstack/react-query";
import { fetchPositions, type PositionRow } from "../../lib/api";
import { useWsStore } from "../../lib/ws";
import ModeBadge from "../ModeBadge";

const fmt = (n: number, d = 2) =>
  n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

export default function PositionsTable() {
  // Seed từ REST, phủ realtime (pnl) từ WS store theo bot_id.
  const { data: initial } = useQuery({ queryKey: ["positions"], queryFn: fetchPositions });
  const live = useWsStore((s) => s.positions);

  const merged = new Map<number, PositionRow & { price?: number; pnl?: number }>();
  for (const p of initial ?? []) if (p.bot_id != null) merged.set(p.bot_id, { ...p });
  for (const [botId, p] of Object.entries(live)) {
    merged.set(Number(botId), {
      id: -1,
      bot_id: Number(botId),
      mode: p.mode,
      symbol: p.symbol,
      side: p.side,
      qty: p.qty,
      entry_price: p.entry_price,
      sl: p.sl,
      tp: p.tp,
      price: p.price,
      pnl: p.pnl,
    });
  }
  const rows = [...merged.values()];

  if (rows.length === 0)
    return <p className="px-1 py-4 text-sm text-ink-500">Chưa có vị thế mở.</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-ink-500">
            <th className="px-2 py-1.5 font-medium">Mode</th>
            <th className="px-2 py-1.5 font-medium">Symbol</th>
            <th className="px-2 py-1.5 font-medium">Side</th>
            <th className="px-2 py-1.5 text-right font-medium">Qty</th>
            <th className="px-2 py-1.5 text-right font-medium">Entry</th>
            <th className="px-2 py-1.5 text-right font-medium">Mark</th>
            <th className="px-2 py-1.5 text-right font-medium">PnL</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => {
            const up = (p.pnl ?? 0) >= 0;
            return (
              <tr key={p.bot_id} className="border-t border-ink-800">
                <td className="px-2 py-1.5">
                  <ModeBadge mode={p.mode} />
                </td>
                <td className="px-2 py-1.5 font-medium">{p.symbol}</td>
                <td
                  className={`px-2 py-1.5 font-medium ${p.side === "LONG" ? "text-up" : "text-down"}`}
                >
                  {p.side}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">{fmt(p.qty, 4)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{fmt(p.entry_price)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {p.price != null ? fmt(p.price) : "—"}
                </td>
                <td
                  className={`px-2 py-1.5 text-right font-medium tabular-nums ${up ? "text-up" : "text-down"}`}
                >
                  {p.pnl != null ? `${up ? "+" : ""}${fmt(p.pnl, 2)}` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
