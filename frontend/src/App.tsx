import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp } from "lucide-react";
import { fetchConfig, syncKlines } from "./lib/api";
import { useWsStore } from "./lib/ws";
import CandleChart from "./components/chart/CandleChart";
import TimeframeSelector from "./components/chart/TimeframeSelector";
import Watchlist from "./components/watchlist/Watchlist";
import FeedBanner from "./components/FeedBanner";

export default function App() {
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: fetchConfig });
  const connect = useWsStore((s) => s.connect);
  const feed = useWsStore((s) => s.feed);

  const [symbol, setSymbol] = useState<string>("");
  const [tf, setTf] = useState<string>("");
  const [showEma, setShowEma] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);

  // Kết nối WS 1 lần.
  useEffect(() => {
    connect();
  }, [connect]);

  // Khởi tạo symbol/tf từ config.
  useEffect(() => {
    if (config && !symbol) {
      setSymbol(config.symbols[0]);
      setTf(config.default_tf);
    }
  }, [config, symbol]);

  // Đảm bảo có lịch sử: sync rồi reload chart.
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
    <div className="flex h-screen flex-col bg-ink-950 text-ink-100">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-ink-700 bg-ink-900 px-4 py-2">
        <div className="flex items-center gap-2">
          <img src="/logo.png" alt="GTIC" className="h-8 w-8 rounded-lg object-contain" />
          <span className="font-semibold">GTIC Trading Bot</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`h-2 w-2 rounded-full ${
              feed === "OK" ? "bg-up" : feed === "DOWN" ? "bg-down" : "bg-brand-400"
            }`}
          />
          <span className="text-ink-400">{feed}</span>
        </div>
      </header>

      <FeedBanner />

      {/* Body: watchlist + chart (responsive) */}
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <aside className="border-b border-ink-700 p-3 md:w-64 md:border-b-0 md:border-r">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
            Watchlist
          </h2>
          {config && <Watchlist symbols={config.symbols} active={symbol} onSelect={setSymbol} />}
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
              {config && <TimeframeSelector timeframes={config.timeframes} active={tf} onSelect={setTf} />}
            </div>
          </div>
          <div className="min-h-0 flex-1 rounded-xl border border-ink-700 bg-ink-900 p-2">
            {symbol && tf && (
              <CandleChart symbol={symbol} tf={tf} showEma={showEma} reloadToken={reloadToken} />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
