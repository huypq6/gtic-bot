// Overview (docs/08 §5.2): one card per trading mode — bots, open positions, equity, results.
// Clicking a card sets the global mode lens and opens Trading for that world.
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { ArrowRight } from "lucide-react";
import { fetchAccounts, fetchModesSummary, type ModeSummary } from "../lib/api";
import { useModeLens, type Lens } from "../lib/modeLens";
import ModeBadge from "../components/ModeBadge";
import { t } from "../lib/i18n";

const BORDER: Record<string, string> = {
  PAPER: "border-t-accent",
  TESTNET: "border-t-warn",
  LIVE: "border-t-down",
};
const HINT: Record<string, string> = {
  PAPER: "Simulated fills on real-time data — shadow & candidate bots live here.",
  TESTNET: "Real orders on the Binance Futures sandbox (fake money).",
  LIVE: "Real orders, real money. Needs ENABLE_LIVE=1 + a LIVE account.",
};

const money = (n: number) =>
  `${n >= 0 ? "+" : "-"}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const tone = (n: number | null | undefined) => (!n ? "" : n > 0 ? "text-up" : "text-down");

export default function Overview() {
  const { data: summary } = useQuery({
    queryKey: ["modes-summary"],
    queryFn: fetchModesSummary,
    refetchInterval: 5000,
  });
  const { data: accounts } = useQuery({
    queryKey: ["accounts"],
    queryFn: fetchAccounts,
    refetchInterval: 5000,
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
      <div>
        <h1 className="text-base font-semibold">{t("Overview")}</h1>
        <p className="text-xs text-faint">
          {t("Every trading mode at a glance. Open one to focus the whole app on it.")}
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {(summary ?? []).map((s) => (
          <ModeCard
            key={s.mode}
            s={s}
            accounts={(accounts ?? []).filter((a) => a.mode === s.mode)}
          />
        ))}
      </div>
    </div>
  );
}

function ModeCard({
  s,
  accounts,
}: {
  s: ModeSummary;
  accounts: { id: number; name: string; equity: number; currency: string; status: string }[];
}) {
  const setLens = useModeLens((x) => x.setLens);
  const nav = useNavigate();
  const open = () => {
    setLens(s.mode as Lens);
    nav("/trade");
  };
  const run = s.bots.RUNNING ?? 0;
  const pause = s.bots.PAUSED ?? 0;
  const stop = s.bots.STOPPED ?? 0;
  const w = s.week;

  return (
    <section
      className={`flex flex-col gap-3 rounded-xl border border-t-4 border-border bg-surface p-4 ${BORDER[s.mode]}`}
    >
      <div className="flex items-center justify-between">
        <ModeBadge mode={s.mode} />
        <span className="text-[11px] text-faint">{t("7 days · UTC")}</span>
      </div>

      {accounts.length ? (
        accounts.map((a) => (
          <div key={a.id} className="flex items-baseline justify-between gap-2">
            <span className="truncate text-sm">
              {a.name}
              {a.status === "HALTED" && <span className="ml-1 text-xs text-down">HALTED</span>}
            </span>
            <span className="font-semibold tabular-nums">
              {a.equity.toLocaleString("en-US", { maximumFractionDigits: 2 })} {a.currency}
            </span>
          </div>
        ))
      ) : (
        <p className="text-sm text-faint">{t("No {mode} account", { mode: s.mode })}</p>
      )}

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
        <dt className="text-faint">Bots</dt>
        <dd className="flex flex-wrap items-center gap-x-2 text-muted">
          <span className="flex items-center gap-1">
            <span className={`h-2 w-2 rounded-full ${run ? "bg-up" : "bg-faint"}`} />
            {t("{n} running", { n: run })}
          </span>
          {pause > 0 && <span className="text-warn">{t("{n} paused", { n: pause })}</span>}
          {stop > 0 && <span>{t("{n} stopped", { n: stop })}</span>}
        </dd>
        <dt className="text-faint">{t("Open")}</dt>
        <dd className="text-muted">
          {t("{n} position(s)", { n: s.open_positions })}
          {s.open_risk > 0 && ` · ${t("risk {v}", { v: `$${s.open_risk.toFixed(2)}` })}`}
        </dd>
        <dt className="text-faint">{t("Today")}</dt>
        <dd>
          {t("{n} trade(s)", { n: s.today.trades })}{" "}
          {s.today.trades > 0 && <span className={`tabular-nums ${tone(s.today.pnl)}`}>{money(s.today.pnl)}</span>}
        </dd>
        <dt className="text-faint">7d</dt>
        <dd>
          {w.trades ? (
            <span className="tabular-nums">
              {t("{n} trade(s)", { n: w.trades })} · {((w.wins / w.trades) * 100).toFixed(0)}%
              {w.sum_r != null && (
                <span className={`ml-1 font-medium ${tone(w.sum_r)}`}>
                  {w.sum_r > 0 ? "+" : ""}
                  {w.sum_r.toFixed(2)}R
                </span>
              )}
              <span className={`ml-1 ${tone(w.pnl)}`}>{money(w.pnl)}</span>
            </span>
          ) : (
            <span className="text-faint">—</span>
          )}
        </dd>
      </dl>

      <p className="text-xs text-faint">{t(HINT[s.mode])}</p>
      <button
        onClick={open}
        className="mt-auto flex items-center justify-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2"
      >
        {t("Open {mode}", { mode: s.mode })} <ArrowRight className="h-4 w-4" />
      </button>
    </section>
  );
}
