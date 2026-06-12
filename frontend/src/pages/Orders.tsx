import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { fetchOrders, type OrderRow } from "../lib/api";
import ModeBadge from "../components/ModeBadge";
import PositionsTable from "../components/orders/PositionsTable";

const STATUS_CLS: Record<string, string> = {
  FILLED: "text-up",
  NEW: "text-warn",
  CANCELLED: "text-faint",
  REJECTED: "text-down",
  PARTIAL: "text-warn",
};

const num = (n: number | null) => (n == null ? "—" : n.toLocaleString("en-US", { maximumFractionDigits: 6 }));

function toCsv(rows: OrderRow[]): string {
  const cols: (keyof OrderRow)[] = [
    "id", "created_at", "mode", "source", "symbol", "side", "type", "qty", "price",
    "sl", "tp", "filled_qty", "avg_price", "fee", "status", "ext_id", "bot_id",
  ];
  const head = cols.join(",");
  const body = rows
    .map((r) => cols.map((c) => (r[c] ?? "").toString().replace(/,/g, "")).join(","))
    .join("\n");
  return `${head}\n${body}`;
}

export default function Orders() {
  const [mode, setMode] = useState("");
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [symbol, setSymbol] = useState("");

  const { data: orders } = useQuery({
    queryKey: ["orders", mode, source, status, symbol],
    queryFn: () => fetchOrders({ mode, source, status, symbol }),
    refetchInterval: 4000,
  });

  const exportCsv = () => {
    const blob = new Blob([toCsv(orders ?? [])], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "orders.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
      {/* Monitor — vị thế đang mở (bot tự cắt SL/TP) */}
      <section className="rounded-xl border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold">Đang theo dõi (vị thế mở · realtime)</h2>
        <PositionsTable />
      </section>

      {/* Lịch sử lệnh — phân tích */}
      <section className="rounded-xl border border-border bg-surface p-4">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <h2 className="text-sm font-semibold">Lịch sử lệnh</h2>
          <div className="flex flex-wrap items-end gap-2 text-sm">
            <Sel label="Mode" value={mode} onChange={setMode} opts={["PAPER", "TESTNET", "LIVE"]} />
            <Sel label="Source" value={source} onChange={setSource} opts={["BOT", "MANUAL", "SYSTEM"]} />
            <Sel
              label="Status"
              value={status}
              onChange={setStatus}
              opts={["NEW", "FILLED", "PARTIAL", "CANCELLED", "REJECTED"]}
            />
            <label className="flex flex-col gap-1">
              <span className="text-xs text-faint">Symbol</span>
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                placeholder="vd BTCUSDT"
                className="w-28 rounded-md border border-border bg-surface-2 px-2 py-1.5"
              />
            </label>
            <button
              onClick={exportCsv}
              className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs hover:bg-surface-2"
            >
              <Download className="h-3.5 w-3.5" /> CSV
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-faint">
                <th className="px-2 py-1.5 font-medium">Thời gian</th>
                <th className="px-2 py-1.5 font-medium">Mode</th>
                <th className="px-2 py-1.5 font-medium">Nguồn</th>
                <th className="px-2 py-1.5 font-medium">Symbol</th>
                <th className="px-2 py-1.5 font-medium">Side</th>
                <th className="px-2 py-1.5 font-medium">Type</th>
                <th className="px-2 py-1.5 text-right font-medium">Qty</th>
                <th className="px-2 py-1.5 text-right font-medium">Giá</th>
                <th className="px-2 py-1.5 text-right font-medium">SL / TP</th>
                <th className="px-2 py-1.5 font-medium">Status</th>
                <th className="px-2 py-1.5 font-medium">ext_id</th>
              </tr>
            </thead>
            <tbody>
              {(orders ?? []).map((o) => (
                <tr key={o.id} className="border-t border-border">
                  <td className="px-2 py-1.5 text-xs tabular-nums text-muted">
                    {o.created_at ? new Date(o.created_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-2 py-1.5">
                    <ModeBadge mode={o.mode} />
                  </td>
                  <td className="px-2 py-1.5 text-muted">{o.source}</td>
                  <td className="px-2 py-1.5 font-medium">{o.symbol}</td>
                  <td className={`px-2 py-1.5 font-medium ${o.side === "BUY" ? "text-up" : "text-down"}`}>
                    {o.side}
                  </td>
                  <td className="px-2 py-1.5 text-muted">{o.type}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{num(o.qty)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{num(o.price)}</td>
                  <td className="px-2 py-1.5 text-right text-xs tabular-nums text-muted">
                    {num(o.sl)} / {num(o.tp)}
                  </td>
                  <td className={`px-2 py-1.5 font-medium ${STATUS_CLS[o.status] ?? ""}`}>
                    {o.status}
                  </td>
                  <td className="px-2 py-1.5 text-xs text-faint">{o.ext_id ?? "—"}</td>
                </tr>
              ))}
              {!orders?.length && (
                <tr>
                  <td colSpan={11} className="px-2 py-4 text-sm text-faint">
                    Chưa có lệnh nào (theo bộ lọc).
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Sel({
  label,
  value,
  onChange,
  opts,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  opts: string[];
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-faint">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-surface-2 px-2 py-1.5"
      >
        <option value="">Tất cả</option>
        {opts.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </label>
  );
}
