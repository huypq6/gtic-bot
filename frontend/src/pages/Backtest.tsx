import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchConfig,
  fetchSizingMethods,
  fetchStrategies,
  runBacktest,
  type BacktestResult,
  type Sizing,
} from "../lib/api";
import SizingInput from "../components/account/SizingInput";
import SimResult from "../components/backtest/SimResult";
import EquityCurve from "../components/backtest/EquityCurve";
import BacktestChart from "../components/backtest/BacktestChart";
import TradeDetail, { fmtPrice } from "../components/backtest/TradeDetail";
import VersionCompare from "../components/strategy/VersionCompare";
import ParamsForm from "../components/strategy/ParamsForm";
import InfoTip from "../components/InfoTip";
import { t } from "../lib/i18n";

export default function Backtest() {
  const qc = useQueryClient();
  const { data: strategies } = useQuery({ queryKey: ["strategies"], queryFn: fetchStrategies });
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: fetchConfig });

  // Binance taker fee (VIP0): Spot 0.10%, Futures 0.05%.
  const FEE_PRESET: Record<string, string> = { SPOT: "0.001", FUTURES: "0.0005" };
  const [stratId, setStratId] = useState<number | "">("");
  const [symbol, setSymbol] = useState("");
  const [tf, setTf] = useState("");
  const [days, setDays] = useState("7");
  const [capital, setCapital] = useState("1000");
  const [market, setMarket] = useState("FUTURES");
  const [leverage, setLeverage] = useState("5");
  const [fee, setFee] = useState(FEE_PRESET.FUTURES);
  const [feeEdited, setFeeEdited] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [params, setParams] = useState<Record<string, unknown>>({});
  // P9c — account simulation engine (default): equity-based sizing, intra-candle SL, same as paper.
  const { data: methods } = useQuery({ queryKey: ["sizing-methods"], queryFn: fetchSizingMethods });
  const [engine, setEngine] = useState<"ACCOUNT" | "VBT">("ACCOUNT");
  const [sizing, setSizing] = useState<Sizing>({ method: "risk_pct", value: 1 });
  const [slip, setSlip] = useState("2");
  const [dailyLoss, setDailyLoss] = useState("");
  const [maxDd, setMaxDd] = useState("");
  const [maxRisk, setMaxRisk] = useState("");
  const [cmp, setCmp] = useState<string[]>(["risk_pct:0.5", "risk_pct:2", "notional_pct:100:1"]);
  const optNum = (v: string) => (v.trim() === "" ? null : Number(v));

  const selectedStrat = strategies?.find((s) => s.id === stratId);
  useEffect(() => {
    if (strategies?.length && stratId === "") setStratId(strategies[0].id);
  }, [strategies, stratId]);
  // strategy changed → reload that strategy's default params (to tweak before running).
  useEffect(() => {
    if (selectedStrat) setParams({ ...selectedStrat.default_params });
  }, [selectedStrat?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (config && !symbol) {
      setSymbol(config.symbols[0]);
      setTf(config.default_tf);
    }
  }, [config, symbol]);
  // market changed → apply the Binance fee automatically (unless edited by hand).
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
        // merge over default_params + coerce numbers; "" → skipped (backend default is used).
        params: cleanParams({ ...selectedStrat?.default_params, ...params }),
        ...(engine === "ACCOUNT"
          ? {
              engine,
              sizing,
              slippage_bps: Number(slip) || 0,
              daily_loss_pct: optNum(dailyLoss),
              max_dd_pct: optNum(maxDd),
              max_risk_pct: optNum(maxRisk),
              compare: cmp.map((k) => {
                const [method, value, lev] = k.split(":");
                return { method, value: Number(value), leverage: lev ? Number(lev) : null };
              }),
            }
          : { engine }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["compare"] }),
  });
  const res: BacktestResult | undefined = run.data;
  const acct = res?.engine === "ACCOUNT";
  const stratName = strategies?.find((s) => s.id === stratId)?.name ?? "";

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
      <section className="rounded-xl border border-border bg-surface p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Backtest</h2>
          <div className="flex rounded-md border border-border text-xs">
            {(
              [
                ["ACCOUNT", t("Account simulation (like paper)")],
                ["VBT", t("Fast — vectorbt (100% equity, fills at close)")],
              ] as const
            ).map(([k, l]) => (
              <button
                key={k}
                onClick={() => setEngine(k)}
                className={`px-2.5 py-1.5 ${engine === k ? "bg-accent text-white" : "text-muted hover:bg-surface-2"}`}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
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
          <F label={t("Days")}>
            <input value={days} onChange={(e) => setDays(e.target.value)} className={inp} />
          </F>
          <F label={t("Market")}>
            <select value={market} onChange={(e) => setMarket(e.target.value)} className={sel}>
              <option value="SPOT">Spot</option>
              <option value="FUTURES">Futures</option>
            </select>
          </F>
          {market === "FUTURES" && (
            <F label={t("Leverage ×")}>
              <input value={leverage} onChange={(e) => setLeverage(e.target.value)} className={inp} />
            </F>
          )}
          <F label={t("Capital (USDT)")}>
            <input value={capital} onChange={(e) => setCapital(e.target.value)} className={inp} />
          </F>
          <F label={t("Fee per side")}>
            <input
              value={fee}
              onChange={(e) => {
                setFee(e.target.value);
                setFeeEdited(true);
              }}
              className={inp}
            />
          </F>
          {engine === "ACCOUNT" && (
            <>
              <SizingInput value={sizing} onChange={setSizing} methods={methods} />
              <F label={t("Slippage (bps)")}>
                <input value={slip} onChange={(e) => setSlip(e.target.value)} className={inp} />
              </F>
              <F label={t("Max risk/trade %")}>
                <input value={maxRisk} placeholder={t("off")} onChange={(e) => setMaxRisk(e.target.value)} className={inp} />
              </F>
              <F label={t("Max daily loss %")}>
                <input value={dailyLoss} placeholder={t("off")} onChange={(e) => setDailyLoss(e.target.value)} className={inp} />
              </F>
              <F label={t("Max drawdown %")}>
                <input value={maxDd} placeholder={t("off")} onChange={(e) => setMaxDd(e.target.value)} className={inp} />
              </F>
            </>
          )}
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending || stratId === ""}
            className="rounded-md bg-accent px-3 py-1.5 font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
          >
            {run.isPending ? t("Running…") : t("Run backtest")}
          </button>
        </div>
        {engine === "ACCOUNT" && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span className="text-faint">{t("Also compare (same data):")}</span>
            {CMP_PRESETS.map(([k, l]) => (
              <button
                key={k}
                onClick={() => setCmp(cmp.includes(k) ? cmp.filter((x) => x !== k) : [...cmp, k])}
                className={`rounded-full border px-2.5 py-1 ${
                  cmp.includes(k) ? "border-accent bg-accent/10 text-text" : "border-border text-muted hover:bg-surface-2"
                }`}
              >
                {l}
              </button>
            ))}
          </div>
        )}
        {selectedStrat && Object.keys(selectedStrat.param_schema ?? {}).length > 0 && (
          <div className="mt-3 border-t border-border pt-3">
            <p className="mb-2 text-xs text-faint">
              {t("Strategy parameters (tweak before running — no code changes needed)")}
            </p>
            <ParamsForm
              schema={selectedStrat.param_schema as Record<string, never>}
              values={params}
              onChange={setParams}
            />
          </div>
        )}
        <p className="mt-2 text-xs text-faint">
          {t(
            "Binance taker fee (VIP0): Spot {spot}% · Futures {fut}% (per side). Futures allow leverage — suits small capital but carries a high risk of liquidation.",
            { spot: (+FEE_PRESET.SPOT * 100).toFixed(2), fut: (+FEE_PRESET.FUTURES * 100).toFixed(3) },
          )}
        </p>
        {engine === "ACCOUNT" && (
          <p className="mt-1 text-xs text-faint">
            {t(
              "Account simulation shares the SAME code as paper: equity-based sizing (compounding), maker/taker fees, slippage, SL/TP filled within the candle (O→H/L→C), daily-loss/drawdown guards. Handles up to ~40,000 candles (≈ 1 year of 15m).",
            )}
          </p>
        )}
        {run.isError && <p className="mt-2 text-sm text-down">{t("Error:")} {(run.error as Error).message}</p>}
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
                {t("fee {pct}%/side", { pct: ((res.fee_rate ?? 0) * 100).toFixed(3) })}
              </InfoTip>
            </span>
            <span>{t("capital {cap} USDT", { cap: res.capital ?? "" })}</span>
          </div>
          {res.liquidated && (
            <div className="rounded-lg border border-down/40 bg-down/10 px-3 py-2 text-sm text-down">
              ⚠️ {t("Account liquidated: equity went to 0 due to ×{lev} leverage. Lower the leverage or use an SL.", { lev: res.leverage ?? "" })}
            </div>
          )}
          {res.engine === "ACCOUNT" ? (
            <SimResult res={res} />
          ) : (
            <section className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <Metric label="PnL %" term="pnl_pct" value={res.pnl_pct} suffix="%" good={(res.pnl_pct ?? 0) >= 0} />
              <Metric label="Win rate" term="winrate" value={res.winrate} suffix="%" />
              <Metric label="Max DD" term="max_dd" value={res.max_dd} suffix="%" good={false} />
              <Metric label="Sharpe" term="sharpe" value={res.sharpe} />
              <Metric label={t("Trades")} term="n_trades" value={res.n_trades} />
            </section>
          )}

          {res.from_ts && res.to_ts && (
            <section className="rounded-xl border border-border bg-surface p-4">
              <h3 className="mb-2 text-sm font-semibold">
                {t("Backtest chart — candles + strategy lines + entry/exit markers")}
              </h3>
              <BacktestChart
                symbol={res.symbol}
                tf={res.tf}
                from={res.from_ts}
                to={res.to_ts}
                indicators={res.indicators}
                trades={res.trades}
              />
            </section>
          )}

          <section className="rounded-xl border border-border bg-surface p-4">
            <h3 className="mb-2 text-sm font-semibold">
              {t("Trades ({n}) — click a trade for details + time replay", { n: res.trades.length })}
            </h3>
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-surface">
                  <tr className="text-left text-xs uppercase tracking-wide text-faint">
                    <th className="px-2 py-1.5">#</th>
                    <th className="px-2 py-1.5">Side</th>
                    <th className="px-2 py-1.5">{t("Entry time")}</th>
                    <th className="px-2 py-1.5">{t("Exit time")}</th>
                    <th className="px-2 py-1.5 text-right">Entry</th>
                    <th className="px-2 py-1.5 text-right">Exit</th>
                    <th className="px-2 py-1.5 text-right">{acct ? t("% equity") : "PnL %"}</th>
                    {acct && (
                      <>
                        <th className="px-2 py-1.5 text-right">PnL (USDT)</th>
                        <th className="px-2 py-1.5 text-right">R</th>
                        <th className="px-2 py-1.5 text-right">{t("Fee")}</th>
                        <th className="px-2 py-1.5">{t("Exit reason")}</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {res.trades.map((t, i) => {
                    const up = (t.pnl_pct ?? 0) >= 0;
                    return (
                      <tr
                        key={i}
                        onClick={() => setSelected(i)}
                        className="cursor-pointer border-t border-border hover:bg-surface-2"
                      >
                        <td className="px-2 py-1 text-faint">{i + 1}</td>
                        <td className={`px-2 py-1 font-medium ${t.side === "Long" ? "text-up" : "text-down"}`}>
                          {t.side}
                        </td>
                        <td className="px-2 py-1 text-xs tabular-nums text-muted">
                          {t.entry_ts ? new Date(t.entry_ts).toLocaleString() : "—"}
                        </td>
                        <td className="px-2 py-1 text-xs tabular-nums text-muted">
                          {t.exit_ts ? new Date(t.exit_ts).toLocaleString() : "—"}
                        </td>
                        <td className="px-2 py-1 text-right tabular-nums">{fmtPrice(t.entry)}</td>
                        <td className="px-2 py-1 text-right tabular-nums">{fmtPrice(t.exit)}</td>
                        <td className={`px-2 py-1 text-right tabular-nums ${up ? "text-up" : "text-down"}`}>
                          {t.pnl_pct != null ? `${up ? "+" : ""}${t.pnl_pct.toFixed(2)}` : "—"}
                        </td>
                        {acct && (
                          <>
                            <td className={`px-2 py-1 text-right tabular-nums ${up ? "text-up" : "text-down"}`}>
                              {t.pnl != null ? `${t.pnl > 0 ? "+" : ""}${t.pnl.toFixed(2)}` : "—"}
                            </td>
                            <td className={`px-2 py-1 text-right tabular-nums ${(t.r ?? 0) >= 0 ? "text-up" : "text-down"}`}>
                              {t.r != null ? `${t.r > 0 ? "+" : ""}${t.r.toFixed(2)}R` : "—"}
                            </td>
                            <td className="px-2 py-1 text-right tabular-nums text-muted">{t.fee?.toFixed(2) ?? "—"}</td>
                            <td className="px-2 py-1 text-xs text-muted">{EXIT[t.reason ?? ""] ?? t.reason ?? "—"}</td>
                          </>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-xl border border-border bg-surface p-4">
            <h3 className="mb-2 text-sm font-semibold">{acct ? t("Equity history (USDT)") : "Equity curve"}</h3>
            {res.equity_curve.length > 1 ? (
              <EquityCurve data={res.equity_curve} />
            ) : (
              <p className="text-sm text-faint">{t("Not enough data to plot equity.")}</p>
            )}
          </section>

          {selected != null && res.trades[selected] && (
            <TradeDetail
              symbol={res.symbol}
              tf={res.tf}
              index={selected}
              trade={res.trades[selected]}
              onClose={() => setSelected(null)}
            />
          )}
        </>
      )}

      {stratName && (
        <section className="rounded-xl border border-border bg-surface p-4">
          <h3 className="mb-2 text-sm font-semibold">{t("Version comparison — {name}", { name: stratName })}</h3>
          <VersionCompare name={stratName} />
        </section>
      )}
    </div>
  );
}

const CMP_PRESETS: [string, string][] = [
  ["risk_pct:0.5", t("risk {pct}%", { pct: "0.5" })],
  ["risk_pct:1", t("risk {pct}%", { pct: "1" })],
  ["risk_pct:2", t("risk {pct}%", { pct: "2" })],
  ["risk_pct:3", t("risk {pct}%", { pct: "3" })],
  ["notional_pct:100:1", t("100% equity 1× (like vectorbt)")],
  ["notional_pct:50:1", t("50% equity 1×")],
];

const EXIT: Record<string, string> = {
  SL: t("SL hit"),
  TP: t("TP hit"),
  SIGNAL: t("Signal"),
  LIQUIDATION: t("Liquidation"),
  END: t("End of data"),
};

// Drop empty fields ("" from a cleared input) → the backend uses the default for that field.
function cleanParams(p: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(p).filter(([, v]) => v !== "" && v != null));
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
