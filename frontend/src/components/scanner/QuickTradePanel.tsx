import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { manualOrder } from "../../lib/api";
import { useWsStore } from "../../lib/ws";
import type { ScanRow } from "../../lib/ws";

// "Đánh theo recommend": panel đặt 1 lệnh tay, prefilled symbol/side/SL/TP từ scan.
export default function QuickTradePanel({
  rec,
  onClose,
}: {
  rec: ScanRow;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const tickers = useWsStore((s) => s.tickers);
  const mark = tickers[rec.symbol]?.price ?? rec.entry ?? undefined;
  const side = rec.signal === "SELL" ? "SELL" : "BUY";

  const [qty, setQty] = useState("0.01");
  const [type, setType] = useState("MARKET");
  const [price, setPrice] = useState(rec.entry?.toString() ?? "");
  const [sl, setSl] = useState(rec.sl?.toString() ?? "");
  const [tp, setTp] = useState(rec.tp?.toString() ?? "");
  const [mode, setMode] = useState("PAPER");

  const num = (v: string) => (v.trim() === "" ? null : Number(v));

  const submit = useMutation({
    mutationFn: () =>
      manualOrder({
        symbol: rec.symbol,
        side,
        type,
        qty: Number(qty),
        price: type === "LIMIT" ? num(price) : null,
        sl: num(sl),
        tp: num(tp),
        ref_price: mark ?? null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["positions"] });
      qc.invalidateQueries({ queryKey: ["orders"] });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-6 shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            Đánh {rec.symbol}{" "}
            <span className={side === "BUY" ? "text-up" : "text-down"}>{side}</span>
          </h2>
          <span className="text-xs text-faint">{rec.reason}</span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <L label="Mode">
            <select value={mode} onChange={(e) => setMode(e.target.value)} className={inp}>
              <option>PAPER</option>
              <option>TESTNET</option>
            </select>
          </L>
          <L label="Type">
            <select value={type} onChange={(e) => setType(e.target.value)} className={inp}>
              <option>MARKET</option>
              <option>LIMIT</option>
            </select>
          </L>
          <L label="Qty">
            <input value={qty} onChange={(e) => setQty(e.target.value)} className={inp} />
          </L>
          {type === "LIMIT" ? (
            <L label="Limit price">
              <input value={price} onChange={(e) => setPrice(e.target.value)} className={inp} />
            </L>
          ) : (
            <L label="Giá hiện tại">
              <input value={mark?.toFixed(2) ?? "—"} disabled className={`${inp} opacity-60`} />
            </L>
          )}
          <L label="SL (đề xuất ATR)">
            <input value={sl} onChange={(e) => setSl(e.target.value)} className={inp} />
          </L>
          <L label="TP (đề xuất ATR)">
            <input value={tp} onChange={(e) => setTp(e.target.value)} className={inp} />
          </L>
        </div>

        {submit.isError && (
          <p className="mt-2 text-sm text-down">Lỗi: {String(submit.error)}</p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-md px-3 py-1.5 text-sm text-muted hover:bg-surface-2">
            Hủy
          </button>
          <button
            onClick={() => submit.mutate()}
            disabled={submit.isPending}
            className={`rounded-md px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-50 ${
              side === "BUY" ? "bg-up hover:bg-up/90" : "bg-down hover:bg-down/90"
            }`}
          >
            {submit.isPending ? "Đang đặt…" : `Đặt lệnh ${side}`}
          </button>
        </div>
      </div>
    </div>
  );
}

const inp = "rounded-md border border-border bg-surface-2 px-2 py-1.5";

function L({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-faint">{label}</span>
      {children}
    </label>
  );
}
