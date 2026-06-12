import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchConfig, fetchStrategies, runBacktest, type BacktestResult } from "../lib/api";
import EquityCurve from "../components/backtest/EquityCurve";
import VersionCompare from "../components/strategy/VersionCompare";

export default function Backtest() {
  const qc = useQueryClient();
  const { data: strategies } = useQuery({ queryKey: ["strategies"], queryFn: fetchStrategies });
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: fetchConfig });

  const [stratId, setStratId] = useState<number | "">("");
  const [symbol, setSymbol] = useState("");
  const [tf, setTf] = useState("");
  const [days, setDays] = useState("7");
  const [capital, setCapital] = useState("10000");
  const [fee, setFee] = useState("0.001");

  useEffect(() => {
    if (strategies?.length && stratId === "") setStratId(strategies[0].id);
  }, [strategies, stratId]);
  useEffect(() => {
    if (config && !symbol) {
      setSymbol(config.symbols[0]);
      setTf(config.default_tf);
    }
  }, [config, symbol]);

  const run = useMutation({
    mutationFn: () =>
      runBacktest({
        strategy_id: stratId as number,
        symbol,
        tf,
        start: `${days} days ago UTC`,
        capital: Number(capital),
        fee_rate: Number(fee),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["compare"] }),
  });
  const res: BacktestResult | undefined = run.data;
  const stratName = strategies?.find((s) => s.id === stratId)?.name ?? "";

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
      <section className="rounded-xl border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold">Backtest</h2>
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <F label="Strategy">
            <select value={stratId} onChange={(e) => setStratId(Number(e.target.value))} className={sel}>
              {strategies?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} v{s.version}
                </option>
              ))}
            </select>
          </F>
          <F label="Symbol">
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className={sel}>
              {config?.symbols.map((s) => <option key={s}>{s}</option>)}
            </select>
          </F>
          <F label="TF">
            <select value={tf} onChange={(e) => setTf(e.target.value)} className={sel}>
              {config?.timeframes.map((t) => <option key={t}>{t}</option>)}
            </select>
          </F>
          <F label="Số ngày">
            <input value={days} onChange={(e) => setDays(e.target.value)} className={inp} />
          </F>
          <F label="Vốn">
            <input value={capital} onChange={(e) => setCapital(e.target.value)} className={inp} />
          </F>
          <F label="Phí">
            <input value={fee} onChange={(e) => setFee(e.target.value)} className={inp} />
          </F>
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending || stratId === ""}
            className="rounded-md bg-accent px-3 py-1.5 font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
          >
            {run.isPending ? "Đang chạy…" : "Chạy backtest"}
          </button>
        </div>
        {run.isError && <p className="mt-2 text-sm text-down">Lỗi: {String(run.error)}</p>}
      </section>

      {res && (
        <>
          <section className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Metric label="PnL %" value={res.pnl_pct} suffix="%" good={(res.pnl_pct ?? 0) >= 0} />
            <Metric label="Win rate" value={res.winrate} suffix="%" />
            <Metric label="Max DD" value={res.max_dd} suffix="%" good={false} />
            <Metric label="Sharpe" value={res.sharpe} />
            <Metric label="Số lệnh" value={res.n_trades} />
          </section>

          <section className="rounded-xl border border-border bg-surface p-4">
            <h3 className="mb-2 text-sm font-semibold">Trades ({res.trades.length})</h3>
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-surface">
                  <tr className="text-left text-xs uppercase tracking-wide text-faint">
                    <th className="px-2 py-1.5">Side</th>
                    <th className="px-2 py-1.5">Entry</th>
                    <th className="px-2 py-1.5">Exit</th>
                    <th className="px-2 py-1.5 text-right">PnL %</th>
                  </tr>
                </thead>
                <tbody>
                  {res.trades.map((t, i) => {
                    const up = (t.pnl_pct ?? 0) >= 0;
                    return (
                      <tr key={i} className="border-t border-border">
                        <td className={`px-2 py-1 font-medium ${t.side === "Long" ? "text-up" : "text-down"}`}>
                          {t.side}
                        </td>
                        <td className="px-2 py-1 tabular-nums">{t.entry?.toFixed(2) ?? "—"}</td>
                        <td className="px-2 py-1 tabular-nums">{t.exit?.toFixed(2) ?? "—"}</td>
                        <td className={`px-2 py-1 text-right tabular-nums ${up ? "text-up" : "text-down"}`}>
                          {t.pnl_pct != null ? `${up ? "+" : ""}${t.pnl_pct.toFixed(2)}` : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-xl border border-border bg-surface p-4">
            <h3 className="mb-2 text-sm font-semibold">Equity curve</h3>
            {res.equity_curve.length > 1 ? (
              <EquityCurve data={res.equity_curve} />
            ) : (
              <p className="text-sm text-faint">Không đủ dữ liệu vẽ equity.</p>
            )}
          </section>
        </>
      )}

      {stratName && (
        <section className="rounded-xl border border-border bg-surface p-4">
          <h3 className="mb-2 text-sm font-semibold">So sánh version — {stratName}</h3>
          <VersionCompare name={stratName} />
        </section>
      )}
    </div>
  );
}

const sel = "rounded-md border border-border bg-surface-2 px-2 py-1.5";
const inp = "w-24 rounded-md border border-border bg-surface-2 px-2 py-1.5";

function F({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-faint">{label}</span>
      {children}
    </label>
  );
}

function Metric({
  label,
  value,
  suffix = "",
  good,
}: {
  label: string;
  value: number | null;
  suffix?: string;
  good?: boolean;
}) {
  const cls = good === undefined ? "text-text" : good ? "text-up" : "text-down";
  return (
    <div className="rounded-xl border border-border bg-surface p-3">
      <div className="text-xs text-faint">{label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${cls}`}>
        {value == null ? "—" : `${value}${suffix}`}
      </div>
    </div>
  );
}
