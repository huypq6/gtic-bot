import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { fetchHealth } from "./lib/api";

// P0: trang Dashboard rỗng — chứng minh frontend gọi được backend qua proxy.
// P1+ thay bằng layout thật (chart, watchlist, positions...).
export default function App() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 5000,
  });

  const backendOk = data?.status === "ok";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-xl">
        <div className="flex items-center gap-3">
          <Activity className="h-6 w-6 text-emerald-400" />
          <h1 className="text-xl font-semibold">GTIC Trading Bot</h1>
        </div>
        <p className="mt-4 text-sm text-slate-400">
          Backend status:{" "}
          {isLoading ? (
            <span className="text-amber-400">checking…</span>
          ) : isError ? (
            <span className="text-red-400">unreachable</span>
          ) : backendOk ? (
            <span className="text-emerald-400">backend ok</span>
          ) : (
            <span className="text-red-400">unexpected</span>
          )}
        </p>
        <p className="mt-2 text-xs text-slate-600">P0 scaffold · proxy /api → :8000</p>
      </div>
    </div>
  );
}
