import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { LineChart } from "lucide-react";
import { fetchScan } from "../lib/api";
import { useWsStore } from "../lib/ws";

const SIGNAL_CLS: Record<string, string> = {
  BUY: "text-up",
  SELL: "text-down",
  NEUTRAL: "text-muted",
};

export default function Scanner() {
  const navigate = useNavigate();
  // seed REST, phủ realtime từ WS.
  const { data: initial } = useQuery({ queryKey: ["scan"], queryFn: fetchScan });
  const live = useWsStore((s) => s.scans);

  const rows = live.length
    ? live
    : (initial ?? []).map((r) => ({
        symbol: r.symbol,
        score: r.score ?? 0,
        signal: r.signal,
        reason: r.reason,
      }));

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Scanner — đề xuất cặp</h2>
        <span className="text-xs text-faint">cập nhật định kỳ · sắp theo score</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-border bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-faint">
              <th className="px-3 py-2 font-medium">Symbol</th>
              <th className="px-3 py-2 text-right font-medium">Score</th>
              <th className="px-3 py-2 font-medium">Tín hiệu</th>
              <th className="px-3 py-2 font-medium">Lý do</th>
              <th className="px-3 py-2 text-right font-medium">Mở chart</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.symbol} className="border-t border-border">
                <td className="px-3 py-2 font-medium">{r.symbol}</td>
                <td className="px-3 py-2 text-right tabular-nums">{r.score.toFixed(1)}</td>
                <td className={`px-3 py-2 font-semibold ${SIGNAL_CLS[r.signal] ?? ""}`}>
                  {r.signal}
                </td>
                <td className="px-3 py-2 text-xs text-muted">{r.reason}</td>
                <td className="px-3 py-2 text-right">
                  <button
                    title="Mở chart cặp này"
                    onClick={() => navigate(`/?symbol=${r.symbol}`)}
                    className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text"
                  >
                    <LineChart className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-sm text-faint">
                  Chưa có kết quả quét (chờ vòng quét đầu tiên).
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
