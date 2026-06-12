import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { TrendingUp } from "lucide-react";
import { fetchConfig, syncKlines } from "../lib/api";
import CandleChart from "../components/chart/CandleChart";
import TimeframeSelector from "../components/chart/TimeframeSelector";
import Watchlist from "../components/watchlist/Watchlist";

export default function Dashboard() {
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: fetchConfig });
  const [searchParams] = useSearchParams();
  const urlSymbol = searchParams.get("symbol");
  const [symbol, setSymbol] = useState<string>("");
  const [tf, setTf] = useState<string>("");
  const [showEma, setShowEma] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (config && !symbol) {
      setSymbol(urlSymbol || config.symbols[0]);
      setTf(config.default_tf);
    }
  }, [config, symbol, urlSymbol]);
  // đổi symbol khi đến từ scanner (?symbol=).
  useEffect(() => {
    if (urlSymbol) setSymbol(urlSymbol);
  }, [urlSymbol]);

  // watchlist gồm config + symbol từ scanner (nếu khác).
  const watchSymbols =
    config && urlSymbol && !config.symbols.includes(urlSymbol)
      ? [urlSymbol, ...config.symbols]
      : config?.symbols;

  useEffect(() => {
    if (!symbol || !tf) return;
    let cancelled = false;
    syncKlines(symbol, tf)
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setReloadToken((t) => t + 1);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, tf]);

  return (
    <div className="flex min-h-0 flex-1 flex-col md:flex-row">
      <aside className="border-b border-ink-700 p-3 md:w-64 md:border-b-0 md:border-r">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
          Watchlist
        </h2>
        {watchSymbols && <Watchlist symbols={watchSymbols} active={symbol} onSelect={setSymbol} />}
      </aside>

      <main className="flex min-h-0 flex-1 flex-col p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-accent-500" />
            <span className="font-semibold">{symbol || "—"}</span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowEma((v) => !v)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                showEma ? "bg-brand-600 text-ink-100" : "text-ink-400 hover:bg-ink-800"
              }`}
            >
              EMA 9/21
            </button>
            {config && (
              <TimeframeSelector timeframes={config.timeframes} active={tf} onSelect={setTf} />
            )}
          </div>
        </div>
        <div className="min-h-0 flex-1 rounded-xl border border-ink-700 bg-ink-900 p-2">
          {symbol && tf && (
            <CandleChart symbol={symbol} tf={tf} showEma={showEma} reloadToken={reloadToken} />
          )}
        </div>
      </main>
    </div>
  );
}
