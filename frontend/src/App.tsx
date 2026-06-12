import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "./lib/api";

// P0/scaffold: trang Dashboard rỗng — chứng minh frontend gọi được backend qua proxy.
// Theme phái sinh từ logo (brand slate-violet, accent teal). P1+ thay bằng layout thật.
export default function App() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 5000,
  });

  const backendOk = data?.status === "ok";
  const statusLabel = isLoading
    ? { text: "checking…", cls: "text-brand-400" }
    : isError
      ? { text: "unreachable", cls: "text-down" }
      : backendOk
        ? { text: "backend ok", cls: "text-up" }
        : { text: "unexpected", cls: "text-down" };

  return (
    <div className="min-h-screen flex items-center justify-center bg-ink-950 px-4">
      <div className="w-full max-w-sm rounded-2xl border border-ink-700 bg-ink-900 p-8 shadow-2xl">
        <div className="flex items-center gap-3">
          <img
            src="/logo.png"
            alt="GTIC"
            className="h-12 w-12 rounded-xl ring-1 ring-ink-700 object-contain bg-ink-800"
          />
          <div>
            <h1 className="text-lg font-semibold text-ink-100">GTIC Trading Bot</h1>
            <p className="text-xs text-ink-400">Binance · single-user</p>
          </div>
        </div>

        <div className="mt-6 flex items-center gap-2 rounded-lg border border-ink-700 bg-ink-850 px-3 py-2">
          <span
            className={`h-2 w-2 rounded-full ${backendOk ? "bg-up" : isLoading ? "bg-brand-400" : "bg-down"}`}
          />
          <span className="text-sm text-ink-400">Backend:</span>
          <span className={`text-sm font-medium ${statusLabel.cls}`}>{statusLabel.text}</span>
        </div>

        <p className="mt-4 text-xs text-ink-500">P0 scaffold · proxy /api → :8000</p>
      </div>
    </div>
  );
}
