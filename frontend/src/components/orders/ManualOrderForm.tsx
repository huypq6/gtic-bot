import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchConfig, manualOrder } from "../../lib/api";
import { useWsStore } from "../../lib/ws";

export default function ManualOrderForm() {
  const qc = useQueryClient();
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: fetchConfig });
  const tickers = useWsStore((s) => s.tickers);

  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState("BUY");
  const [type, setType] = useState("MARKET");
  const [qty, setQty] = useState("0.01");
  const [price, setPrice] = useState("");
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");

  useEffect(() => {
    if (config && !symbol) setSymbol(config.symbols[0]);
  }, [config, symbol]);

  const num = (v: string) => (v.trim() === "" ? null : Number(v));
  const mark = tickers[symbol]?.price;

  const submit = useMutation({
    mutationFn: () =>
      manualOrder({
        symbol,
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
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });

  return (
    <div className="flex flex-wrap items-end gap-2 text-sm">
      <Sel label="Symbol" value={symbol} onChange={setSymbol} options={config?.symbols ?? []} />
      <Sel label="Side" value={side} onChange={setSide} options={["BUY", "SELL"]} />
      <Sel label="Type" value={type} onChange={setType} options={["MARKET", "LIMIT"]} />
      <Inp label="Qty" value={qty} onChange={setQty} />
      {type === "LIMIT" && <Inp label="Limit price" value={price} onChange={setPrice} />}
      <Inp label="SL" value={sl} onChange={setSl} />
      <Inp label="TP" value={tp} onChange={setTp} />
      <button
        onClick={() => submit.mutate()}
        disabled={submit.isPending || !symbol}
        className={`rounded-md px-3 py-1.5 text-sm font-semibold disabled:opacity-50 ${
          side === "BUY"
            ? "bg-up/90 text-ink-950 hover:bg-up"
            : "bg-down/90 text-ink-950 hover:bg-down"
        }`}
      >
        {side} {symbol}
      </button>
      {mark != null && <span className="text-xs text-ink-500">mark {mark.toFixed(2)}</span>}
    </div>
  );
}

function Sel({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-ink-500">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-ink-700 bg-ink-800 px-2 py-1.5"
      >
        {options.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </label>
  );
}

function Inp({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-ink-500">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-24 rounded-md border border-ink-700 bg-ink-800 px-2 py-1.5"
      />
    </label>
  );
}
