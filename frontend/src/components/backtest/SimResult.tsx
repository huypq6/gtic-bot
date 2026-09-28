import { useEffect, useRef } from "react";
import { ColorType, LineSeries, createChart, type Time } from "lightweight-charts";
import { AlertTriangle } from "lucide-react";
import type { BacktestResult, SimCompareRow } from "../../lib/api";
import { chartColors } from "../../lib/chartTheme";
import { useTheme } from "../../lib/theme";
import InfoTip from "../InfoTip";
import { sizingText } from "../account/SizingInput";
import { t } from "../../lib/i18n";

const COLORS = ["#1f9e8a", "#6f8fd8", "#e0a458", "#c98bdb", "#d98b8b", "#8b9cba", "#5cc3b4", "#b5a33f", "#9aa0a6"];

const n2 = (v: number | null | undefined, d = 2) => (v == null ? "—" : v.toFixed(d));
const sgn = (v: number | null | undefined, d = 2, suf = "%") =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}${suf}`;
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "text-up" : "text-down");
const usd = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function SimResult({ res }: { res: BacktestResult }) {
  const st = res.stats;
  if (!st) return null;
  const cmp = st.compare ?? [];
  const cap = res.capital ?? 0;
  const warn: string[] = [];
  if (st.liquidated) warn.push(t("Account LIQUIDATED (equity went to 0)."));
  if (st.dd_halt_ts)
    warn.push(
      t("Drawdown limit hit → account HALTED from {date} (no further trades).", { date: new Date(st.dd_halt_ts).toLocaleDateString() }),
    );
  if (st.day_halts) warn.push(t("{n} days paused after hitting the daily loss limit.", { n: st.day_halts }));
  const capped = Object.entries(st.capped ?? {});
  if (capped.length)
    warn.push(
      t("Position size CAPPED: {list} — actual risk is below target (raise leverage or lower the risk %).", {
        list: capped.map(([k, v]) => `${v}× ${k}`).join(", "),
      }),
    );
  const rej = Object.entries(st.rejects ?? {});
  if (rej.length) warn.push(t("Signals blocked: {list}.", { list: rej.map(([k, v]) => `${v}× ${k}`).join(", ") }));

  return (
    <>
      {warn.length > 0 && (
        <div className="flex gap-2 rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <ul className="space-y-0.5">
            {warn.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <M label={t("Final equity")} value={`${usd(res.final_equity)}`} sub={t("from {v} USDT", { v: usd(cap) })} cls={tone((res.final_equity ?? 0) - cap)} />
        <M label={t("Return")} value={sgn(res.pnl_pct)} sub={st.cagr_pct != null ? t("{v}/yr", { v: sgn(st.cagr_pct) }) : undefined} cls={tone(res.pnl_pct)} />
        <M
          label={t("Max drawdown")}
          tip={t("Peak-to-trough decline in equity, plus the longest time spent below the peak.")}
          value={`-${n2(res.max_dd)}%`}
          sub={t("longest below peak: {n} days", { n: st.longest_dd_days })}
          cls="text-down"
        />
        <M label="Calmar" tip={t("Annual return ÷ max drawdown. > 1 is good.")} value={n2(st.calmar)} />
        <M label="Sharpe" tip={t("Based on daily returns, annualized.")} value={n2(res.sharpe)} />
        <M label={t("Trades")} value={`${res.n_trades ?? 0}`} sub={t("win {v}%", { v: n2(res.winrate, 1) })} />
        <M
          label="Profit factor"
          tip={t("Gross profit ÷ gross loss (USDT, after fees). > 1.5 is good.")}
          value={n2(st.profit_factor)}
        />
        <M
          label={t("Avg R")}
          tip={t("Expectancy per trade in multiples of risk (after fees). Positive = has an edge.")}
          value={sgn(st.avg_r, 2, "R")}
          sub={t("best {best} · worst {worst}", { best: sgn(st.best_r, 1, "R"), worst: sgn(st.worst_r, 1, "R") })}
          cls={tone(st.avg_r)}
        />
        <M
          label={t("Trading fees")}
          value={usd(st.total_fees)}
          sub={t("= {v}% of starting capital", { v: n2(st.fees_pct_of_capital) })}
          cls={st.fees_pct_of_capital > 5 ? "text-warn" : ""}
        />
        <M label={t("Longest losing streak")} value={t("{n} trades", { n: st.max_loss_streak })} />
        <M label={t("Profitable months")} value={`${st.positive_months}/${st.monthly.length}`} />
        <M
          label={t("Avg position size")}
          tip={t("Average position value relative to equity at entry. > 100% = using leverage.")}
          value={st.avg_notional_pct != null ? `${st.avg_notional_pct}%` : "—"}
          sub={t("of equity")}
        />
      </section>

      {cmp.length > 1 && (
        <section className="rounded-xl border border-border bg-surface p-4">
          <h3 className="mb-2 text-sm font-semibold">{t("Position sizing comparison (same signals, same data)")}</h3>
          <CompareCurves rows={cmp} />
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-faint">
                  <th className="px-2 py-1.5 font-medium">{t("Setup")}</th>
                  <th className="px-2 py-1.5 text-right font-medium">{t("Final equity")}</th>
                  <th className="px-2 py-1.5 text-right font-medium">{t("Return")}</th>
                  <th className="px-2 py-1.5 text-right font-medium">{t("/yr")}</th>
                  <th className="px-2 py-1.5 text-right font-medium">{t("Drawdown")}</th>
                  <th className="px-2 py-1.5 text-right font-medium">Calmar</th>
                  <th className="px-2 py-1.5 text-right font-medium">PF</th>
                  <th className="px-2 py-1.5 text-right font-medium">{t("Fees")}</th>
                  <th className="px-2 py-1.5 text-right font-medium">{t("Avg size")}</th>
                  <th className="px-2 py-1.5 font-medium">{t("Notes")}</th>
                </tr>
              </thead>
              <tbody>
                {cmp.map((c, i) => {
                  const best = Math.max(...cmp.map((x) => x.calmar ?? -Infinity));
                  const notes = [
                    c.liquidated && t("liquidated"),
                    c.dd_halt_ts && t("HALTED by drawdown"),
                    c.day_halts > 0 && t("{n} days paused", { n: c.day_halts }),
                    Object.values(c.capped ?? {}).reduce((a, b) => a + b, 0) > 0 &&
                      t("{n} trades capped", { n: Object.values(c.capped).reduce((a, b) => a + b, 0) }),
                  ].filter(Boolean);
                  return (
                    <tr key={i} className="border-t border-border">
                      <td className="px-2 py-1.5">
                        <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                        {sizingText(c.sizing)} · {c.leverage}×{i === 0 && <span className="ml-1 text-xs text-faint">{t("(main)")}</span>}
                        {c.calmar === best && cmp.length > 1 && best > 0 && (
                          <span className="ml-1 rounded bg-up/15 px-1 text-[11px] font-semibold text-up">{t("best by Calmar")}</span>
                        )}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{usd(c.final_equity)}</td>
                      <td className={`px-2 py-1.5 text-right tabular-nums ${tone(c.pnl_pct)}`}>{sgn(c.pnl_pct)}</td>
                      <td className={`px-2 py-1.5 text-right tabular-nums ${tone(c.cagr_pct)}`}>{sgn(c.cagr_pct)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-down">-{n2(c.max_dd)}%</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{n2(c.calmar)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{n2(c.profit_factor)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{usd(c.total_fees)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{c.avg_notional_pct != null ? `${c.avg_notional_pct}%` : "—"}</td>
                      <td className="px-2 py-1.5 text-xs text-muted">{notes.join(" · ") || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-faint">
            {t(
              "Same signal sequence, so win rate/R are identical; only position size differs → return, drawdown, fees and whether guards get hit. Pick the setup by the drawdown you can tolerate, not just by return.",
            )}
          </p>
        </section>
      )}

      {st.monthly.length > 0 && (
        <section className="rounded-xl border border-border bg-surface p-4">
          <h3 className="mb-2 text-sm font-semibold">{t("Monthly returns")}</h3>
          <Monthly data={st.monthly} />
        </section>
      )}
    </>
  );
}

function M({ label, value, sub, tip, cls = "" }: { label: string; value: string; sub?: string; tip?: string; cls?: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-3">
      <div className="text-xs text-faint">{tip ? <InfoTip text={tip} align="left">{label}</InfoTip> : label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${cls}`}>{value}</div>
      {sub && <div className="text-xs text-faint">{sub}</div>}
    </div>
  );
}

function Monthly({ data }: { data: [string, number][] }) {
  const max = Math.max(1, ...data.map(([, v]) => Math.abs(v)));
  return (
    <div className="overflow-x-auto">
      <div className="flex min-w-max items-center gap-1">
        {data.map(([m, v]) => (
          <div key={m} className="flex w-14 flex-col items-center gap-1" title={`${m}: ${sgn(v)}`}>
            <div className="flex h-20 w-6 flex-col justify-end">
              <div className="flex h-10 items-end">
                {v > 0 && <div className="w-6 rounded-t bg-up" style={{ height: `${(v / max) * 100}%` }} />}
              </div>
              <div className="flex h-10 items-start border-t border-border">
                {v < 0 && <div className="w-6 rounded-b bg-down" style={{ height: `${(-v / max) * 100}%` }} />}
              </div>
            </div>
            <span className={`text-[11px] tabular-nums ${tone(v)}`}>{sgn(v, 1)}</span>
            <span className="text-[10px] text-faint">{m.slice(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function CompareCurves({ rows }: { rows: SimCompareRow[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const theme = useTheme((s) => s.theme);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const c = chartColors();
    const chart = createChart(el, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: c.text, attributionLogo: false },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.grid },
      timeScale: { borderColor: c.grid, timeVisible: true },
      autoSize: true,
    });
    rows.forEach((r, i) => {
      const s = chart.addSeries(LineSeries, {
        color: COLORS[i % COLORS.length],
        lineWidth: i === 0 ? 3 : 2,
        priceLineVisible: false,
        title: `${sizingText(r.sizing)} ${r.leverage}×`,
      });
      s.setData(r.equity_curve.map(([ts, v]) => ({ time: (ts / 1000) as Time, value: v })));
    });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [rows, theme]);
  return <div ref={ref} className="h-72 w-full" />;
}
