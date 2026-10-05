// Header segmented control for the global mode lens (docs/08) + the colored "world" stripe.
import { useQuery } from "@tanstack/react-query";
import { fetchModesSummary } from "../lib/api";
import { LENSES, useModeLens, type Lens } from "../lib/modeLens";
import { t } from "../lib/i18n";

// same colour matrix as ModeBadge: paper=teal, testnet=amber, live=red
const ACTIVE: Record<string, string> = {
  "": "bg-surface text-text shadow-sm",
  PAPER: "bg-accent text-white",
  TESTNET: "bg-warn text-white",
  LIVE: "bg-down text-white",
};

const label = (l: Lens) => (l === "" ? t("All") : l[0] + l.slice(1).toLowerCase());

export default function ModeLens() {
  const lens = useModeLens((s) => s.lens);
  const setLens = useModeLens((s) => s.setLens);
  const { data } = useQuery({
    queryKey: ["modes-summary"],
    queryFn: fetchModesSummary,
    refetchInterval: 5000,
  });
  const running = (m: Lens) => data?.find((x) => x.mode === m)?.bots.RUNNING ?? 0;

  return (
    <div
      role="radiogroup"
      aria-label={t("Mode lens")}
      title={t("Show only this trading mode across all pages (view filter — does not affect bots)")}
      className="flex shrink-0 items-center gap-0.5 rounded-lg border border-border bg-surface-2 p-0.5 text-xs"
    >
      {LENSES.map((l) => {
        const on = lens === l;
        const n = l ? running(l) : 0;
        return (
          <button
            key={l || "ALL"}
            role="radio"
            aria-checked={on}
            onClick={() => setLens(l)}
            className={`flex items-center gap-1 rounded-md px-2 py-1 font-medium transition ${
              on ? ACTIVE[l] : "text-muted hover:text-text"
            }`}
          >
            {label(l)}
            {n > 0 && (
              <span
                title={t("{n} running bot(s)", { n })}
                className={`rounded-full px-1 text-[10px] tabular-nums ${on ? "bg-white/25" : "bg-surface"}`}
              >
                {n}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Thin banner under the header so TESTNET / LIVE views can't be mistaken for paper. */
export function LensStripe() {
  const lens = useModeLens((s) => s.lens);
  if (lens !== "TESTNET" && lens !== "LIVE") return null;
  const live = lens === "LIVE";
  return (
    <div
      className={`px-3 py-0.5 text-center text-[11px] font-semibold tracking-wide text-white ${
        live ? "bg-down" : "bg-warn"
      }`}
    >
      {live ? t("LIVE view — real money") : t("TESTNET view — exchange sandbox")}
    </div>
  );
}

/** "Showing PAPER only · All" — inline reminder on pages scoped by the lens. */
export function LensNote() {
  const lens = useModeLens((s) => s.lens);
  const setLens = useModeLens((s) => s.setLens);
  if (!lens) return null;
  return (
    <p className="flex items-center gap-2 text-xs text-faint">
      {t("Showing {mode} only", { mode: lens })}
      <button onClick={() => setLens("")} className="underline hover:text-text">
        {t("Show all modes")}
      </button>
    </p>
  );
}
