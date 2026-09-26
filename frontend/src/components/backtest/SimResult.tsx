import { useEffect, useRef } from "react";
import { ColorType, LineSeries, createChart, type Time } from "lightweight-charts";
import { AlertTriangle } from "lucide-react";
import type { BacktestResult, SimCompareRow } from "../../lib/api";
import { chartColors } from "../../lib/chartTheme";
import { useTheme } from "../../lib/theme";
import InfoTip from "../InfoTip";
import { sizingText } from "../account/SizingInput";

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
  if (st.liquidated) warn.push("Tài khoản CHÁY (equity về 0).");
  if (st.dd_halt_ts)
    warn.push(`Chạm giới hạn sụt vốn → tài khoản DỪNG từ ${new Date(st.dd_halt_ts).toLocaleDateString()} (không vào lệnh nữa).`);
  if (st.day_halts) warn.push(`${st.day_halts} ngày bị nghỉ do chạm giới hạn lỗ ngày.`);
  const capped = Object.entries(st.capped ?? {});
  if (capped.length)
    warn.push(
      `Lệnh bị CO khối lượng: ${capped.map(([k, v]) => `${v}× ${k}`).join(", ")} — rủi ro thực tế thấp hơn mục tiêu (tăng đòn bẩy hoặc giảm % rủi ro).`,
    );
  const rej = Object.entries(st.rejects ?? {});
  if (rej.length) warn.push(`Tín hiệu bị chặn: ${rej.map(([k, v]) => `${v}× ${k}`).join(", ")}.`);

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
        <M label="Vốn cuối" value={`${usd(res.final_equity)}`} sub={`từ ${usd(cap)} USDT`} cls={tone((res.final_equity ?? 0) - cap)} />
        <M label="Lợi nhuận" value={sgn(res.pnl_pct)} sub={st.cagr_pct != null ? `${sgn(st.cagr_pct)}/năm` : undefined} cls={tone(res.pnl_pct)} />
        <M
          label="Sụt vốn tối đa"
          tip="Từ đỉnh equity xuống đáy. Kèm thời gian dài nhất nằm dưới đỉnh."
          value={`-${n2(res.max_dd)}%`}
          sub={`dưới đỉnh lâu nhất ${st.longest_dd_days} ngày`}
          cls="text-down"
        />
        <M label="Calmar" tip="Lợi nhuận/năm ÷ sụt vốn tối đa. > 1 là tốt." value={n2(st.calmar)} />
        <M label="Sharpe" tip="Theo lợi nhuận ngày, năm hóa." value={n2(res.sharpe)} />
        <M label="Số lệnh" value={`${res.n_trades ?? 0}`} sub={`thắng ${n2(res.winrate, 1)}%`} />
        <M
          label="Profit factor"
          tip="Tổng lãi ÷ tổng lỗ (USDT, đã trừ phí). > 1.5 là tốt."
          value={n2(st.profit_factor)}
        />
        <M
          label="R trung bình"
          tip="Kỳ vọng mỗi lệnh theo bội số rủi ro (đã trừ phí). Dương = có lợi thế."
          value={sgn(st.avg_r, 2, "R")}
          sub={`tốt nhất ${sgn(st.best_r, 1, "R")} · tệ nhất ${sgn(st.worst_r, 1, "R")}`}
          cls={tone(st.avg_r)}
        />
        <M
          label="Phí giao dịch"
          value={usd(st.total_fees)}
          sub={`= ${n2(st.fees_pct_of_capital)}% vốn ban đầu`}
          cls={st.fees_pct_of_capital > 5 ? "text-warn" : ""}
        />
        <M label="Chuỗi thua dài nhất" value={`${st.max_loss_streak} lệnh`} />
        <M label="Tháng có lãi" value={`${st.positive_months}/${st.monthly.length}`} />
        <M
          label="Giá trị lệnh TB"
          tip="Giá trị vị thế trung bình so với equity lúc vào. > 100% = đang dùng đòn bẩy."
          value={st.avg_notional_pct != null ? `${st.avg_notional_pct}%` : "—"}
          sub="của equity"
        />
      </section>

      {cmp.length > 1 && (
        <section className="rounded-xl border border-border bg-surface p-4">
          <h3 className="mb-2 text-sm font-semibold">So sánh cách quản lý vốn (cùng tín hiệu, cùng dữ liệu)</h3>
          <CompareCurves rows={cmp} />
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-faint">
                  <th className="px-2 py-1.5 font-medium">Cấu hình</th>
                  <th className="px-2 py-1.5 text-right font-medium">Vốn cuối</th>
                  <th className="px-2 py-1.5 text-right font-medium">Lợi nhuận</th>
                  <th className="px-2 py-1.5 text-right font-medium">/năm</th>
                  <th className="px-2 py-1.5 text-right font-medium">Sụt vốn</th>
                  <th className="px-2 py-1.5 text-right font-medium">Calmar</th>
                  <th className="px-2 py-1.5 text-right font-medium">PF</th>
                  <th className="px-2 py-1.5 text-right font-medium">Phí</th>
                  <th className="px-2 py-1.5 text-right font-medium">Lệnh TB</th>
                  <th className="px-2 py-1.5 font-medium">Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {cmp.map((c, i) => {
                  const best = Math.max(...cmp.map((x) => x.calmar ?? -Infinity));
                  const notes = [
                    c.liquidated && "cháy TK",
                    c.dd_halt_ts && "DỪNG do sụt vốn",
                    c.day_halts > 0 && `${c.day_halts} ngày nghỉ`,
                    Object.values(c.capped ?? {}).reduce((a, b) => a + b, 0) > 0 &&
                      `${Object.values(c.capped).reduce((a, b) => a + b, 0)} lệnh bị co`,
                  ].filter(Boolean);
                  return (
                    <tr key={i} className="border-t border-border">
                      <td className="px-2 py-1.5">
                        <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                        {sizingText(c.sizing)} · {c.leverage}×{i === 0 && <span className="ml-1 text-xs text-faint">(chính)</span>}
                        {c.calmar === best && cmp.length > 1 && best > 0 && (
                          <span className="ml-1 rounded bg-up/15 px-1 text-[11px] font-semibold text-up">tốt nhất theo Calmar</span>
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
            Cùng chuỗi tín hiệu nên winrate/R như nhau; khác nhau ở khối lượng → lợi nhuận, sụt vốn, phí và việc
            có chạm rào chắn hay không. Chọn cấu hình theo mức sụt vốn bạn chịu được, không chỉ theo lợi nhuận.
          </p>
        </section>
      )}

      {st.monthly.length > 0 && (
        <section className="rounded-xl border border-border bg-surface p-4">
          <h3 className="mb-2 text-sm font-semibold">Lợi nhuận theo tháng</h3>
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
