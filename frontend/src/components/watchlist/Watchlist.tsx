import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { addWatch, removeWatch } from "../../lib/api";
import { useWsStore } from "../../lib/ws";

interface Props {
  symbols: string[];
  active: string;
  onSelect: (symbol: string) => void;
}

const fmt = (n: number) =>
  n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function Watchlist({ symbols, active, onSelect }: Props) {
  const qc = useQueryClient();
  const tickers = useWsStore((s) => s.tickers);
  const [input, setInput] = useState("");

  const refresh = () => qc.invalidateQueries({ queryKey: ["config"] });
  const add = useMutation({
    mutationFn: () => addWatch(input.trim().toUpperCase()),
    onSuccess: () => {
      setInput("");
      refresh();
    },
  });
  const remove = useMutation({ mutationFn: (s: string) => removeWatch(s), onSuccess: refresh });

  return (
    <div className="flex flex-col gap-2">
      {/* Thêm cặp */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (input.trim()) add.mutate();
        }}
        className="flex gap-1"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase())}
          placeholder="Thêm cặp (vd SOLUSDT)"
          className="min-w-0 flex-1 rounded-md border border-border bg-surface-2 px-2 py-1.5 text-sm"
        />
        <button
          type="submit"
          disabled={add.isPending || !input.trim()}
          title="Thêm vào watchlist"
          className="rounded-md bg-accent px-2 py-1.5 text-white hover:bg-accent-strong disabled:opacity-50"
        >
          <Plus className="h-4 w-4" />
        </button>
      </form>
      {add.isError && <p className="text-xs text-down">Cặp không hợp lệ / không có trên Binance.</p>}

      <ul className="flex flex-col gap-1">
        {symbols.map((sym) => {
          const t = tickers[sym];
          const up = (t?.pct ?? 0) >= 0;
          return (
            <li key={sym} className="group relative">
              <button
                onClick={() => onSelect(sym)}
                className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 pr-8 text-left transition ${
                  sym === active
                    ? "border-primary bg-surface-2"
                    : "border-transparent hover:bg-surface-2"
                }`}
              >
                <span className="font-medium text-text">{sym}</span>
                <span className="text-right">
                  <span className="block text-sm tabular-nums text-text">
                    {t ? fmt(t.price) : "—"}
                  </span>
                  {t && (
                    <span className={`block text-xs tabular-nums ${up ? "text-up" : "text-down"}`}>
                      {up ? "+" : ""}
                      {t.pct.toFixed(2)}%
                    </span>
                  )}
                </span>
              </button>
              <button
                title="Xóa khỏi watchlist"
                onClick={() => remove.mutate(sym)}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-faint opacity-0 transition hover:text-down group-hover:opacity-100"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
