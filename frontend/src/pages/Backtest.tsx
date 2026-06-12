import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchConfig, fetchStrategies, runBacktest, type BacktestResult } from "../lib/api";
import EquityCurve from "../components/backtest/EquityCurve";
import VersionCompare from "../components/strategy/VersionCompare";
import InfoTip from "../components/InfoTip";

export default function Backtest() {
  const qc = useQueryClient();
  const { data: strategies } = useQuery({ queryKey: ["strategies"], queryFn: fetchStrategies });
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: fetchConfig });

  // Phí Binance taker (VIP0): Spot 0.10%, Futures 0.05%.
  const FEE_PRESET: Record<string, string> = { SPOT: "0.001", FUTURES: "0.0005" };
  const [stratId, setStratId] = useState<number | "">("");
  const [symbol, setSymbol] = useState("");
  const [tf, setTf] = useState("");
  const [days, setDays] = useState("7");
  const [capital, setCapital] = useState("1000");
  const [market, setMarket] = useState("SPOT");
  const [leverage, setLeverage] = useState("1");
  const [fee, setFee] = useState(FEE_PRESET.SPOT);
  const [feeEdited, setFeeEdited] = useState(false);

  useEffect(() => {
    if (strategies?.length && stratId === "") setStratId(strategies[0].id);
  }, [strategies, stratId]);
  useEffect(() => {
    if (config && !symbol) {
      setSymbol(config.symbols[0]);
      setTf(config.default_tf);
    }
  }, [config, symbol]);
  // đổi thị trường → tự áp phí Binance (nếu chưa sửa tay).
  useEffect(() => {
    if (!feeEdited) setFee(FEE_PRESET[market]);
    if (market === "SPOT") setLeverage("1");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market]);

  const run = useMutation({
    mutationFn: () =>
      runBacktest({
        strategy_id: stratId as number,
        symbol,
        tf,
        start: `${days} days ago UTC`,
        capital: Number(capital),
        market,
        leverage: Number(leverage),
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
          <F label="Thị trường">
            <select value={market} onChange={(e) => setMarket(e.target.value)} className={sel}>
              <option value="SPOT">Spot</option>
              <option value="FUTURES">Futures</option>
            </select>
          </F>
          {market === "FUTURES" && (
            <F label="Đòn bẩy ×">
              <input value={leverage} onChange={(e) => setLeverage(e.target.value)} className={inp} />
            </F>
          )}
          <F label="Vốn (USDT)">
            <input value={capital} onChange={(e) => setCapital(e.target.value)} className={inp} />
          </F>
          <F label="Phí 1 chiều">
            <input
              value={fee}
              onChange={(e) => {
                setFee(e.target.value);
                setFeeEdited(true);
              }}
              className={inp}
            />
          </F>
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending || stratId === ""}
            className="rounded-md bg-accent px-3 py-1.5 font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
          >
            {run.isPending ? "Đang chạy…" : "Chạy backtest"}
          </button>
        </div>
        <p className="mt-2 text-xs text-faint">
          Phí Binance taker (VIP0): Spot {(+FEE_PRESET.SPOT * 100).toFixed(2)}% · Futures{" "}
          {(+FEE_PRESET.FUTURES * 100).toFixed(3)}% (mỗi chiều). Futures cho đòn bẩy — hợp vốn nhỏ
          nhưng rủi ro cháy tài khoản cao.
        </p>
        {run.isError && <p className="mt-2 text-sm text-down">Lỗi: {String(run.error)}</p>}
      </section>

      {res && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="rounded border border-border px-2 py-0.5">
              <InfoTip term={(res.leverage ?? 1) > 1 ? "leverage" : "market"} align="left">
                {res.market ?? "SPOT"}
                {(res.leverage ?? 1) > 1 ? ` · ×${res.leverage}` : ""}
              </InfoTip>
            </span>
            <span className="rounded border border-border px-2 py-0.5">
              <InfoTip term="fee" align="left">
                phí {((res.fee_rate ?? 0) * 100).toFixed(3)}%/chiều
              </InfoTip>
            </span>
            <span>vốn {res.capital} USDT</span>
          </div>
          {res.liquidated && (
            <div className="rounded-lg border border-down/40 bg-down/10 px-3 py-2 text-sm text-down">
              ⚠️ Cháy tài khoản (liquidated): equity về 0 do đòn bẩy ×{res.leverage}. Giảm đòn bẩy
              hoặc dùng SL.
            </div>
          )}
          <section className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Metric label="PnL %" term="pnl_pct" value={res.pnl_pct} suffix="%" good={(res.pnl_pct ?? 0) >= 0} />
            <Metric label="Win rate" term="winrate" value={res.winrate} suffix="%" />
            <Metric label="Max DD" term="max_dd" value={res.max_dd} suffix="%" good={false} />
            <Metric label="Sharpe" term="sharpe" value={res.sharpe} />
            <Metric label="Số lệnh" term="n_trades" value={res.n_trades} />
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
  term,
  value,
  suffix = "",
  good,
}: {
  label: string;
  term?: string;
  value: number | null;
  suffix?: string;
  good?: boolean;
}) {
  const cls = good === undefined ? "text-text" : good ? "text-up" : "text-down";
  return (
    <div className="rounded-xl border border-border bg-surface p-3">
      <div className="text-xs text-faint">
        <InfoTip term={term} align="left">
          {label}
        </InfoTip>
      </div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${cls}`}>
        {value == null ? "—" : `${value}${suffix}`}
      </div>
    </div>
  );
}
