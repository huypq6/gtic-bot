import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, X } from "lucide-react";
import { closePosition, editSltp, fetchPositions } from "../../lib/api";
import { useWsStore } from "../../lib/ws";
import ModeBadge from "../ModeBadge";
import InfoTip from "../InfoTip";

const fmt = (n: number, d = 2) =>
  n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

interface Row {
  id: number; // DB position id (-1 nếu chỉ có realtime)
  key: string;
  mode: string;
  symbol: string;
  side: string;
  qty: number;
  entry_price: number;
  price?: number;
  pnl?: number;
  sl: number | null;
  tp: number | null;
}

const keyOf = (botId: number | null, symbol: string) =>
  botId != null ? `bot:${botId}` : `manual:${symbol}`;

export default function PositionsTable() {
  const qc = useQueryClient();
  const { data: initial } = useQuery({ queryKey: ["positions"], queryFn: fetchPositions });
  const live = useWsStore((s) => s.positions);
  const tickers = useWsStore((s) => s.tickers);
  const [editing, setEditing] = useState<number | null>(null);

  const rows = new Map<string, Row>();
  for (const p of initial ?? [])
    rows.set(keyOf(p.bot_id, p.symbol), {
      id: p.id,
      key: keyOf(p.bot_id, p.symbol),
      mode: p.mode,
      symbol: p.symbol,
      side: p.side,
      qty: p.qty,
      entry_price: p.entry_price,
      sl: p.sl,
      tp: p.tp,
    });
  for (const [k, p] of Object.entries(live)) {
    const prev = rows.get(k);
    rows.set(k, {
      id: prev?.id ?? -1,
      key: k,
      mode: p.mode,
      symbol: p.symbol,
      side: p.side,
      qty: p.qty,
      entry_price: p.entry_price,
      price: p.price,
      pnl: p.pnl,
      sl: p.sl,
      tp: p.tp,
    });
  }
  const list = [...rows.values()];
  const refresh = () => qc.invalidateQueries({ queryKey: ["positions"] });

  if (list.length === 0)
    return <p className="px-1 py-4 text-sm text-faint">Chưa có vị thế mở.</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-faint">
            <th className="px-2 py-1.5 font-medium">Mode</th>
            <th className="px-2 py-1.5 font-medium">Symbol</th>
            <th className="px-2 py-1.5 font-medium">
              <InfoTip term="side">Side</InfoTip>
            </th>
            <th className="px-2 py-1.5 text-right font-medium">Qty</th>
            <th className="px-2 py-1.5 text-right font-medium">Entry</th>
            <th className="px-2 py-1.5 text-right font-medium">
              <InfoTip term="mark">Mark</InfoTip>
            </th>
            <th className="px-2 py-1.5 text-right font-medium">
              <InfoTip term="sl">SL / TP</InfoTip>
            </th>
            <th className="px-2 py-1.5 text-right font-medium">
              <InfoTip term="pnl">PnL</InfoTip>
            </th>
            <th className="px-2 py-1.5 text-right font-medium">Hành động</th>
          </tr>
        </thead>
        <tbody>
          {list.map((p) => {
            const up = (p.pnl ?? 0) >= 0;
            const mark = p.price ?? tickers[p.symbol]?.price;
            return (
              <tr key={p.key} className="border-t border-border align-middle">
                <td className="px-2 py-1.5">
                  <ModeBadge mode={p.mode} />
                </td>
                <td className="px-2 py-1.5 font-medium">{p.symbol}</td>
                <td className={`px-2 py-1.5 font-medium ${p.side === "LONG" ? "text-up" : "text-down"}`}>
                  {p.side}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">{fmt(p.qty, 4)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{fmt(p.entry_price)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {mark != null ? fmt(mark) : "—"}
                </td>
                <td className="px-2 py-1.5 text-right text-xs tabular-nums text-muted">
                  {p.sl != null ? fmt(p.sl) : "—"} / {p.tp != null ? fmt(p.tp) : "—"}
                </td>
                <td className={`px-2 py-1.5 text-right font-medium tabular-nums ${up ? "text-up" : "text-down"}`}>
                  {p.pnl != null ? `${up ? "+" : ""}${fmt(p.pnl, 2)}` : "—"}
                </td>
                <td className="px-2 py-1.5">
                  <div className="flex items-center justify-end gap-1">
                    {p.id > 0 && (
                      <>
                        <button
                          title="Sửa SL/TP"
                          onClick={() => setEditing(editing === p.id ? null : p.id)}
                          className="rounded p-1 text-muted hover:bg-surface-2 hover:text-text"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button
                          title="Đóng vị thế"
                          onClick={async () => {
                            await closePosition(p.id, mark);
                            refresh();
                          }}
                          className="rounded p-1 text-down hover:bg-down/10"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </>
                    )}
                  </div>
                  {editing === p.id && (
                    <SltpEditor
                      sl={p.sl}
                      tp={p.tp}
                      onSave={async (sl, tp) => {
                        await editSltp(p.id, sl, tp);
                        setEditing(null);
                        refresh();
                      }}
                      onCancel={() => setEditing(null)}
                    />
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function SltpEditor({
  sl,
  tp,
  onSave,
  onCancel,
}: {
  sl: number | null;
  tp: number | null;
  onSave: (sl: number | null, tp: number | null) => void;
  onCancel: () => void;
}) {
  const [slv, setSlv] = useState(sl?.toString() ?? "");
  const [tpv, setTpv] = useState(tp?.toString() ?? "");
  const num = (v: string) => (v.trim() === "" ? null : Number(v));
  return (
    <div className="mt-1 flex items-center justify-end gap-1">
      <input
        value={slv}
        onChange={(e) => setSlv(e.target.value)}
        placeholder="SL"
        className="w-20 rounded border border-border bg-surface-2 px-1.5 py-0.5 text-xs"
      />
      <input
        value={tpv}
        onChange={(e) => setTpv(e.target.value)}
        placeholder="TP"
        className="w-20 rounded border border-border bg-surface-2 px-1.5 py-0.5 text-xs"
      />
      <button
        onClick={() => onSave(num(slv), num(tpv))}
        className="rounded bg-accent px-2 py-0.5 text-xs font-medium text-white"
      >
        Lưu
      </button>
      <button onClick={onCancel} className="rounded px-1.5 py-0.5 text-xs text-muted">
        Hủy
      </button>
    </div>
  );
}
