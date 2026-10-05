// Compare (docs/08 §5.3): the same strategy across modes & versions + live-vs-paper divergence.
// Cross-mode by design → not filtered by the lens (the lens mode is only highlighted).
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchModeCompare, type ModeCompareGroup, type ModeDivergence } from "../lib/api";
import { useModeLens } from "../lib/modeLens";
import ModeBadge from "../components/ModeBadge";
import InfoTip from "../components/InfoTip";
import { t } from "../lib/i18n";

const PERIODS = [
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
  { days: 90, label: "90d" },
  { days: 0, label: "All" },
];

const tone = (n: number | null | undefined) => (!n ? "" : n > 0 ? "text-up" : "text-down");
const sgn = (n: number | null | undefined, d = 2, unit = "") =>
  n == null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(d)}${unit}`;
const money = (n: number) =>
  `${n >= 0 ? "+" : "-"}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function Compare() {
  const [days, setDays] = useState(30);
  const [symbol, setSymbol] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["mode-compare", days, symbol],
    queryFn: () => fetchModeCompare(days, symbol),
    refetchInterval: 30_000,
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-base font-semibold">{t("Compare modes & versions")}</h1>
          <p className="max-w-2xl text-xs text-faint">
            {t(
              "Closed trades of the same strategy, symbol and TF side by side. Run a PAPER shadow of each LIVE bot (same version) to measure slippage and missed trades, and PAPER/TESTNET candidates (new versions) to decide what to promote.",
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2 text-sm">
          <div className="flex rounded-lg border border-border bg-surface-2 p-0.5 text-xs">
            {PERIODS.map((p) => (
              <button
                key={p.days}
                onClick={() => setDays(p.days)}
                className={`rounded-md px-2.5 py-1 font-medium ${
                  days === p.days ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text"
                }`}
              >
                {p.days ? p.label : t("All")}
              </button>
            ))}
          </div>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder={t("e.g. BTCUSDT")}
            aria-label="Symbol"
            className="w-28 rounded-md border border-border bg-surface-2 px-2 py-1"
          />
        </div>
      </div>

      {isLoading && <p className="text-sm text-faint">{t("Loading…")}</p>}
      {data && !data.groups.length && (
        <p className="rounded-xl border border-border bg-surface p-4 text-sm text-faint">
          {t("No closed bot trades in this period.")}
        </p>
      )}
      {data?.groups.map((g) => <GroupCard key={`${g.strategy}|${g.symbol}|${g.tf}`} g={g} />)}
    </div>
  );
}

function GroupCard({ g }: { g: ModeCompareGroup }) {
  const lens = useModeLens((s) => s.lens);
  // a version that only runs in PAPER/TESTNET while LIVE runs another one = candidate
  const liveVers = new Set(g.rows.filter((r) => r.mode === "LIVE").map((r) => r.version));
  const role = (mode: string, v: string) => {
    if (mode === "LIVE" || !liveVers.size) return null;
    return liveVers.has(v) ? t("shadow") : t("candidate");
  };

  return (
    <section className="rounded-xl border border-border bg-surface p-4">
      <h2 className="mb-2 text-sm font-semibold">
        {g.strategy} <span className="font-normal text-muted">· {g.symbol} · {g.tf}</span>
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-faint">
              <th className="px-2 py-1.5 font-medium">Mode</th>
              <th className="px-2 py-1.5 font-medium">{t("Version")}</th>
              <th className="px-2 py-1.5 text-right font-medium">{t("Trades")}</th>
              <th className="px-2 py-1.5 text-right font-medium">Win%</th>
              <th className="px-2 py-1.5 text-right font-medium">{t("Total R")}</th>
              <th className="px-2 py-1.5 text-right font-medium">
                <InfoTip text={t("Average R per trade (expectancy). Comparable across modes and position sizes.")}>
                  {t("Avg R")}
                </InfoTip>
              </th>
              <th className="px-2 py-1.5 text-right font-medium">PnL</th>
              <th className="px-2 py-1.5 text-right font-medium">{t("Fees")}</th>
              <th className="px-2 py-1.5 font-medium">Bots</th>
            </tr>
          </thead>
          <tbody>
            {g.rows.map((r) => {
              const rl = role(r.mode, r.version);
              return (
                <tr
                  key={`${r.mode}|${r.version}`}
                  className={`border-t border-border ${lens && lens === r.mode ? "bg-surface-2" : ""}`}
                >
                  <td className="px-2 py-1.5">
                    <ModeBadge mode={r.mode} />
                  </td>
                  <td className="px-2 py-1.5">
                    v{r.version || "?"}
                    {rl && <span className="ml-1.5 text-xs text-faint">{rl}</span>}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{r.trades}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {r.win_rate == null ? "—" : `${r.win_rate.toFixed(0)}%`}
                  </td>
                  <td className={`px-2 py-1.5 text-right font-medium tabular-nums ${tone(r.sum_r)}`}>
                    {sgn(r.sum_r, 2, "R")}
                  </td>
                  <td className={`px-2 py-1.5 text-right tabular-nums ${tone(r.avg_r)}`}>
                    {sgn(r.avg_r, 2, "R")}
                  </td>
                  <td className={`px-2 py-1.5 text-right tabular-nums ${tone(r.pnl)}`}>{money(r.pnl)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-muted">${r.fees.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-xs text-faint">{r.bots.map((b) => `#${b}`).join(" ")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {g.divergence.length > 0 && (
        <div className="mt-3 border-t border-border pt-3">
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-faint">
            <InfoTip
              text={t(
                "Trades of the same version in two modes, paired when opened within one candle on the same side. Slippage is positive when the first mode got a worse price. Unpaired trades = signals one side took and the other missed.",
              )}
            >
              {t("Divergence (same version)")}
            </InfoTip>
          </h3>
          <div className="flex flex-col gap-1.5">
            {g.divergence.map((d) => (
              <DivRow key={`${d.a}|${d.b}|${d.version}`} d={d} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function DivRow({ d }: { d: ModeDivergence }) {
  // adverse slippage / worse R on the "more real" side = bad → red
  const bad = (n: number | null) => (n == null || Math.abs(n) < 1e-9 ? "" : n > 0 ? "text-down" : "text-up");
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
      <span className="flex items-center gap-1">
        <ModeBadge mode={d.a} /> <span className="text-faint">vs</span> <ModeBadge mode={d.b} />
        <span className="text-muted">v{d.version}</span>
      </span>
      <span className="text-muted">
        {t("paired {n}", { n: d.paired })} · {t("only {mode} {n}", { mode: d.a, n: d.only_a })} ·{" "}
        {t("only {mode} {n}", { mode: d.b, n: d.only_b })}
      </span>
      {d.paired > 0 && (
        <span className="tabular-nums">
          {t("entry slip")} <span className={bad(d.entry_slip_bps)}>{sgn(d.entry_slip_bps, 1, " bps")}</span>
          {" · "}
          {t("exit slip")} <span className={bad(d.exit_slip_bps)}>{sgn(d.exit_slip_bps, 1, " bps")}</span>
          {" · "}
          {t("R diff")}{" "}
          <span className={d.r_diff == null ? "" : d.r_diff < 0 ? "text-down" : "text-up"}>
            {sgn(d.r_diff, 2, "R")}
          </span>
          <span className="text-faint">/{t("trade")}</span>
        </span>
      )}
    </div>
  );
}
