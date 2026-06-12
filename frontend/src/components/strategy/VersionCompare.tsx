import { useQuery } from "@tanstack/react-query";
import { fetchCompare } from "../../lib/api";

// So sánh hiệu năng các version theo backtest (US-08).
export default function VersionCompare({ name }: { name: string }) {
  const { data } = useQuery({
    queryKey: ["compare", name],
    queryFn: () => fetchCompare(name),
    enabled: !!name,
  });

  if (!data?.length) return null;

  const num = (v: number | null, s = "") => (v == null ? "—" : `${v}${s}`);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-faint">
            <th className="px-2 py-1.5 font-medium">Version</th>
            <th className="px-2 py-1.5 text-right font-medium">Runs</th>
            <th className="px-2 py-1.5 text-right font-medium">Best PnL%</th>
            <th className="px-2 py-1.5 text-right font-medium">Last PnL%</th>
            <th className="px-2 py-1.5 text-right font-medium">Win%</th>
            <th className="px-2 py-1.5 text-right font-medium">Max DD%</th>
            <th className="px-2 py-1.5 text-right font-medium">Trades</th>
          </tr>
        </thead>
        <tbody>
          {data.map((r) => (
            <tr key={r.version} className="border-t border-border">
              <td className="px-2 py-1.5 font-medium">v{r.version}</td>
              <td className="px-2 py-1.5 text-right tabular-nums">{r.runs}</td>
              <td
                className={`px-2 py-1.5 text-right tabular-nums ${(r.best_pnl_pct ?? 0) >= 0 ? "text-up" : "text-down"}`}
              >
                {num(r.best_pnl_pct, "%")}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums">{num(r.last_pnl_pct, "%")}</td>
              <td className="px-2 py-1.5 text-right tabular-nums">{num(r.last_winrate, "%")}</td>
              <td className="px-2 py-1.5 text-right tabular-nums text-down">
                {num(r.last_max_dd, "%")}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums">{num(r.last_n_trades)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
