import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { Bot, LineChart, Zap } from "lucide-react";
import { fetchScan } from "../lib/api";
import { useWsStore, type ScanRow } from "../lib/ws";
import QuickTradePanel from "../components/scanner/QuickTradePanel";
import InfoTip from "../components/InfoTip";
import { t } from "../lib/i18n";

const SIGNAL_CLS: Record<string, string> = {
  BUY: "text-up",
  SELL: "text-down",
  NEUTRAL: "text-muted",
};

const fmt = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString("en-US", { maximumFractionDigits: 4 });

export default function Scanner() {
  const navigate = useNavigate();
  const { data: initial } = useQuery({ queryKey: ["scan"], queryFn: fetchScan });
  const live = useWsStore((s) => s.scans);
  const [trade, setTrade] = useState<ScanRow | null>(null);

  const rows: ScanRow[] = live.length
    ? live
    : (initial ?? []).map((r) => ({
        symbol: r.symbol,
        score: r.score ?? 0,
        signal: r.signal,
        reason: r.reason,
        entry: r.entry,
        atr: r.atr,
        sl: r.sl,
        tp: r.tp,
      }));

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold">{t("Scanner — pair suggestions (ATR-based SL/TP)")}</h2>
        <span className="text-xs text-faint">{t("updated periodically · sorted by score")}</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-border bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-faint">
              <th className="px-3 py-2 font-medium">Symbol</th>
              <th className="px-3 py-2 text-right font-medium">
                <InfoTip term="score">Score</InfoTip>
              </th>
              <th className="px-3 py-2 font-medium">
                <InfoTip term="signal">{t("Signal")}</InfoTip>
              </th>
              <th className="px-3 py-2 text-right font-medium">
                <InfoTip term="entry">Entry</InfoTip>
              </th>
              <th className="px-3 py-2 text-right font-medium">
                <InfoTip term="sl">SL</InfoTip>
              </th>
              <th className="px-3 py-2 text-right font-medium">
                <InfoTip term="tp">TP</InfoTip>
              </th>
              <th className="px-3 py-2 font-medium">{t("Reason")}</th>
              <th className="px-3 py-2 text-right font-medium">{t("Actions")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const tradable = r.signal === "BUY" || r.signal === "SELL";
              return (
                <tr key={r.symbol} className="border-t border-border">
                  <td className="px-3 py-2 font-medium">{r.symbol}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.score.toFixed(1)}</td>
                  <td className={`px-3 py-2 font-semibold ${SIGNAL_CLS[r.signal] ?? ""}`}>
                    {r.signal}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(r.entry)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-down">{fmt(r.sl)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-up">{fmt(r.tp)}</td>
                  <td className="px-3 py-2 text-xs text-muted">{r.reason}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        title={t("Trade the suggestion (1 order)")}
                        disabled={!tradable}
                        onClick={() => setTrade(r)}
                        className="rounded-md p-1.5 text-accent hover:bg-surface-2 disabled:opacity-30"
                      >
                        <Zap className="h-4 w-4" />
                      </button>
                      <button
                        title={t("Create a bot for this pair")}
                        onClick={() => navigate(`/trade?symbol=${r.symbol}`)}
                        className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text"
                      >
                        <Bot className="h-4 w-4" />
                      </button>
                      <button
                        title={t("Open chart")}
                        onClick={() => navigate(`/?symbol=${r.symbol}`)}
                        className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text"
                      >
                        <LineChart className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {!rows.length && (
              <tr>
                <td colSpan={8} className="px-3 py-4 text-sm text-faint">
                  {t("No scan results yet (waiting for the first scan).")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {trade && <QuickTradePanel rec={trade} onClose={() => setTrade(null)} />}
    </div>
  );
}
