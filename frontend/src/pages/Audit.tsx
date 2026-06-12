import { useQuery } from "@tanstack/react-query";
import { fetchAudit } from "../lib/api";

const SOURCE_CLS: Record<string, string> = {
  BOT: "text-muted",
  MANUAL: "text-accent",
  SYSTEM: "text-muted",
};

export default function Audit() {
  const { data } = useQuery({ queryKey: ["audit"], queryFn: fetchAudit, refetchInterval: 4000 });

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
      <h2 className="mb-3 text-sm font-semibold">Audit log</h2>
      <div className="overflow-x-auto rounded-xl border border-border bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-faint">
              <th className="px-3 py-2 font-medium">Thời gian</th>
              <th className="px-3 py-2 font-medium">Nguồn</th>
              <th className="px-3 py-2 font-medium">Mode</th>
              <th className="px-3 py-2 font-medium">Bot</th>
              <th className="px-3 py-2 font-medium">Symbol</th>
              <th className="px-3 py-2 font-medium">Hành động</th>
              <th className="px-3 py-2 font-medium">Chi tiết</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((r) => (
              <tr key={r.id} className="border-t border-border">
                <td className="px-3 py-1.5 text-xs tabular-nums text-muted">
                  {r.ts ? new Date(r.ts).toLocaleString() : "—"}
                </td>
                <td className={`px-3 py-1.5 font-medium ${SOURCE_CLS[r.source] ?? ""}`}>
                  {r.source}
                </td>
                <td className="px-3 py-1.5 text-muted">{r.mode ?? "—"}</td>
                <td className="px-3 py-1.5 text-muted">{r.bot_id ?? "—"}</td>
                <td className="px-3 py-1.5">{r.symbol ?? "—"}</td>
                <td className="px-3 py-1.5 font-medium">{r.action}</td>
                <td className="px-3 py-1.5 text-xs text-faint">
                  {r.detail ? JSON.stringify(r.detail) : "—"}
                </td>
              </tr>
            ))}
            {!data?.length && (
              <tr>
                <td colSpan={7} className="px-3 py-4 text-sm text-faint">
                  Chưa có bản ghi.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
