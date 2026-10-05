// Exchange connection check (docs/09): keys, clock, permission, balance, position mode, symbols.
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, PlugZap, XCircle } from "lucide-react";
import { fetchExchangeCheck, type ExchangeCheckResult } from "../../lib/api";
import { t } from "../../lib/i18n";

const ICON = {
  ok: <CheckCircle2 className="h-4 w-4 shrink-0 text-up" />,
  warn: <AlertTriangle className="h-4 w-4 shrink-0 text-warn" />,
  fail: <XCircle className="h-4 w-4 shrink-0 text-down" />,
};
const SUMMARY: Record<ExchangeCheckResult["status"], string> = {
  ok: "Ready — bots can trade on this account.",
  warn: "Usable, but check the warnings.",
  fail: "Not ready — fix the failed items, restart the app if you edited .env, then check again.",
};

export default function ExchangeCheck({ mode, auto = false }: { mode: string; auto?: boolean }) {
  const check = useMutation({ mutationFn: () => fetchExchangeCheck(mode) });
  const r = check.data;
  return (
    <div className="space-y-2 text-sm">
      <button
        onClick={() => check.mutate()}
        disabled={check.isPending}
        className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2 disabled:opacity-50"
      >
        <PlugZap className={`h-4 w-4 ${check.isPending ? "animate-pulse" : ""}`} />
        {check.isPending ? t("Checking…") : t("Check connection")}
      </button>
      {check.isError && <p className="text-xs text-down">{(check.error as Error).message}</p>}
      {r && (
        <div className="rounded-lg border border-border bg-surface-2 p-3">
          <p className={`mb-2 flex items-center gap-1.5 font-medium ${r.status === "ok" ? "text-up" : r.status === "warn" ? "text-warn" : "text-down"}`}>
            {ICON[r.status]} {t(SUMMARY[r.status])}
          </p>
          <ul className="space-y-1.5">
            {r.checks.map((c) => (
              <li key={c.key} className="flex gap-2">
                {ICON[c.status]}
                <div className="min-w-0">
                  <span className="font-medium">{t(c.label)}</span>
                  {c.detail && <span className="ml-1.5 break-words text-muted">{c.detail}</span>}
                  {c.fix && <p className="text-xs text-faint">→ {c.fix}</p>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {auto && !r && !check.isPending && (
        <p className="text-xs text-faint">{t("Run this before creating the account.")}</p>
      )}
    </div>
  );
}
