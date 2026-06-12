import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { BookOpen, FlaskConical, Play, X } from "lucide-react";
import { fetchStrategies, fetchStrategyDoc, type StrategyInfo } from "../lib/api";
import Markdown from "../components/Markdown";

export default function Library() {
  const navigate = useNavigate();
  const { data: strategies } = useQuery({ queryKey: ["strategies"], queryFn: fetchStrategies });
  const [docName, setDocName] = useState<string | null>(null);

  // gộp theo name (nhiều version chung 1 phương pháp luận).
  const families = new Map<string, StrategyInfo[]>();
  for (const s of strategies ?? []) {
    const list = families.get(s.name) ?? [];
    list.push(s);
    families.set(s.name, list);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
      <h2 className="mb-3 text-sm font-semibold">Thư viện chiến thuật</h2>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {[...families.entries()].map(([name, versions]) => {
          const latest = versions[versions.length - 1];
          return (
            <div
              key={name}
              className="flex flex-col rounded-xl border border-border bg-surface p-4"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-base font-semibold text-text">{name}</h3>
                <div className="flex gap-1">
                  {versions.map((v) => (
                    <span
                      key={v.version}
                      className="rounded border border-border px-1.5 py-0.5 text-[10px] font-semibold text-muted"
                    >
                      v{v.version}
                    </span>
                  ))}
                </div>
              </div>

              <p className="mt-2 flex-1 text-sm text-muted">{latest.description || "—"}</p>

              <div className="mt-3 flex flex-wrap gap-1 text-[11px] text-faint">
                {Object.entries(latest.default_params).map(([k, val]) => (
                  <span key={k} className="rounded bg-surface-2 px-1.5 py-0.5">
                    {k}={String(val)}
                  </span>
                ))}
              </div>

              <div className="mt-4 flex items-center gap-1">
                <button
                  onClick={() => setDocName(name)}
                  className="flex items-center gap-1 rounded-md bg-primary px-2.5 py-1.5 text-xs font-medium text-white hover:opacity-90"
                >
                  <BookOpen className="h-3.5 w-3.5" /> Phương pháp luận
                </button>
                <button
                  title="Backtest strategy này"
                  onClick={() => navigate("/backtest")}
                  className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs text-muted hover:bg-surface-2"
                >
                  <FlaskConical className="h-3.5 w-3.5" /> Backtest
                </button>
                <button
                  title="Tạo bot"
                  onClick={() => navigate("/trade")}
                  className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs text-muted hover:bg-surface-2"
                >
                  <Play className="h-3.5 w-3.5" /> Tạo bot
                </button>
              </div>
            </div>
          );
        })}
        {!families.size && <p className="text-sm text-faint">Chưa có strategy nào.</p>}
      </div>

      {docName && <DocReader name={docName} onClose={() => setDocName(null)} />}
    </div>
  );
}

function DocReader({ name, onClose }: { name: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ["strategy-doc", name],
    queryFn: () => fetchStrategyDoc(name),
  });

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose}>
      <div
        className="h-full w-full max-w-2xl overflow-y-auto border-l border-border bg-surface p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <span className="text-xs uppercase tracking-wide text-faint">
            Phương pháp luận · {name}
          </span>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {isLoading ? (
          <p className="text-sm text-faint">Đang tải…</p>
        ) : (
          <Markdown>{data?.markdown ?? ""}</Markdown>
        )}
      </div>
    </div>
  );
}
