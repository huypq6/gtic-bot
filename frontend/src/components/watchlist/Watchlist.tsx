import { useWsStore } from "../../lib/ws";

interface Props {
  symbols: string[];
  active: string;
  onSelect: (symbol: string) => void;
}

const fmt = (n: number) =>
  n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function Watchlist({ symbols, active, onSelect }: Props) {
  const tickers = useWsStore((s) => s.tickers);

  return (
    <ul className="flex flex-col gap-1">
      {symbols.map((sym) => {
        const t = tickers[sym];
        const up = (t?.pct ?? 0) >= 0;
        return (
          <li key={sym}>
            <button
              onClick={() => onSelect(sym)}
              className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition ${
                sym === active
                  ? "border-brand-600 bg-ink-800"
                  : "border-transparent hover:bg-ink-850"
              }`}
            >
              <span className="font-medium text-ink-100">{sym}</span>
              <span className="text-right">
                <span className="block text-sm tabular-nums text-ink-100">
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
          </li>
        );
      })}
    </ul>
  );
}
