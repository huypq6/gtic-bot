import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, ArrowUpFromLine, Plus, RefreshCw, ShieldAlert, X } from "lucide-react";
import {
  createAccount,
  depositAccount,
  fetchAccounts,
  fetchEquity,
  fetchLedger,
  patchAccount,
  resumeAccount,
  syncAccount,
  withdrawAccount,
  type AccountInfo,
  type AccountSettings,
  type LedgerRow,
} from "../lib/api";
import EquityCurve from "../components/backtest/EquityCurve";
import InfoTip from "../components/InfoTip";
import ModeBadge from "../components/ModeBadge";
import { LensNote } from "../components/ModeLens";
import ExchangeCheck from "../components/account/ExchangeCheck";
import { inLens, useModeLens } from "../lib/modeLens";
import { t } from "../lib/i18n";

const usd = (n: number | null | undefined, sign = false) =>
  n == null
    ? "—"
    : `${sign && n > 0 ? "+" : ""}${n < 0 ? "-" : ""}${Math.abs(n).toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;
const pct = (n: number | null | undefined, sign = false) =>
  n == null ? "—" : `${sign && n > 0 ? "+" : ""}${n.toFixed(2)}%`;
const tone = (n: number | null | undefined) => (n == null || n === 0 ? "" : n > 0 ? "text-up" : "text-down");

const TXN: Record<LedgerRow["type"], string> = {
  DEPOSIT: t("Deposit"),
  WITHDRAW: t("Withdraw"),
  REALIZED_PNL: t("Trade PnL"),
  FEE: t("Fee"),
  ADJUST: t("Adjustment"),
};

export default function Account() {
  const qc = useQueryClient();
  const { data: allAccounts } = useQuery({
    queryKey: ["accounts"],
    queryFn: fetchAccounts,
    refetchInterval: 5000,
  });
  const lens = useModeLens((s) => s.lens);
  const accounts = allAccounts?.filter((a) => inLens(lens, a.mode));
  const [selId, setSelId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  useEffect(() => {
    if (accounts?.length && (selId == null || !accounts.some((a) => a.id === selId)))
      setSelId(accounts[0].id);
  }, [accounts, selId]);
  const acc = accounts?.find((a) => a.id === selId);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["accounts"] });
    qc.invalidateQueries({ queryKey: ["ledger"] });
    qc.invalidateQueries({ queryKey: ["equity"] });
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
      <LensNote />
      <div className="flex flex-wrap items-center gap-2">
        {accounts?.map((a) => (
          <button
            key={a.id}
            onClick={() => setSelId(a.id)}
            className={`rounded-lg border px-3 py-1.5 text-sm ${
              a.id === selId
                ? "border-accent bg-accent/10 font-semibold text-text"
                : "border-border text-muted hover:bg-surface-2"
            }`}
          >
            <span className="inline-flex items-center gap-2">
              {a.mode !== "PAPER" && <ModeBadge mode={a.mode} />}
              {a.name}
            </span>
            <span className="ml-2 text-xs tabular-nums text-faint">{usd(a.equity)} {a.currency}</span>
          </button>
        ))}
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-1 rounded-lg border border-dashed border-border px-3 py-1.5 text-sm text-muted hover:bg-surface-2"
        >
          <Plus className="h-4 w-4" /> {t("New account")}
        </button>
      </div>

      {creating && <CreateAccount onDone={() => { setCreating(false); refresh(); }} />}
      {!accounts?.length && !creating && (
        <p className="text-sm text-faint">
          {lens
            ? t("No {mode} account yet.", { mode: lens })
            : t("No accounts yet. Create a paper account to get started.")}
        </p>
      )}
      {acc && <AccountView key={acc.id} acc={acc} onChange={refresh} />}
    </div>
  );
}

function AccountView({ acc, onChange }: { acc: AccountInfo; onChange: () => void }) {
  const s = acc.settings;
  const blocked = acc.status === "HALTED" || acc.paused_today;
  const resume = useMutation({ mutationFn: () => resumeAccount(acc.id), onSuccess: onChange });

  return (
    <>
      {blocked && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-down/40 bg-down/10 px-4 py-3 text-sm">
          <ShieldAlert className="h-5 w-5 shrink-0 text-down" />
          <div className="flex-1">
            <div className="font-semibold text-down">
              {acc.status === "HALTED" ? t("Account HALTED — bots won't open new positions") : t("Paused until end of day (UTC)")}
            </div>
            <div className="text-muted">
              {acc.halted_reason}
              {acc.paused_today && acc.halted_until && ` · ${t("resumes at {time}", { time: new Date(acc.halted_until).toLocaleString() })}`}
              . {t("Open positions keep their SL/TP.")}
            </div>
          </div>
          <button
            onClick={() => resume.mutate()}
            className="rounded-md border border-down/50 px-3 py-1.5 text-xs font-medium text-down hover:bg-down/10"
          >
            {t("I've reviewed it — unlock")}
          </button>
        </div>
      )}

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-5">
        <Card
          big
          label={t("Total equity")}
          tip={t("Wallet balance + unrealized PnL of open positions.")}
          value={`${usd(acc.equity)} ${acc.currency}`}
        />
        <Card
          label={t("Cumulative PnL")}
          tip={t("Equity − net deposits (deposits − withdrawals). Deposits/withdrawals don't count as PnL.")}
          value={usd(acc.total_pnl, true)}
          sub={acc.total_pnl_pct != null ? pct(acc.total_pnl_pct, true) : undefined}
          cls={tone(acc.total_pnl)}
        />
        <Card
          label={t("Today (UTC)")}
          value={usd(acc.daily_pnl, true)}
          sub={`${pct(acc.daily_pnl_pct, true)}${s.daily_loss_pct != null ? ` · ${t("limit -{pct}%", { pct: s.daily_loss_pct })}` : ""}`}
          cls={tone(acc.daily_pnl)}
        />
        <Card
          label={t("Drawdown from peak")}
          tip={t("Current equity vs. its highest peak (excluding deposits/withdrawals). Hitting the limit → account HALTED.")}
          value={pct(-acc.dd_pct)}
          sub={`${t("peak {v}", { v: usd(acc.peak_equity) })}${s.max_dd_pct != null ? ` · ${t("halts at -{pct}%", { pct: s.max_dd_pct })}` : ""}`}
          cls={acc.dd_pct > 0 ? "text-down" : ""}
        />
        <Card label={t("Wallet balance")} tip={t("Deposits − withdrawals + realized PnL − fees.")} value={usd(acc.balance)} />
        <Card
          label={t("Margin in use")}
          value={usd(acc.used_margin)}
          sub={t("{n} open · leverage {lev}×", { n: acc.n_open, lev: s.leverage })}
        />
        <Card
          label={t("Available")}
          tip={t("Usable for new positions or withdrawals = equity − margin.")}
          value={usd(acc.available)}
        />
        <Card
          label={t("Unrealized PnL")}
          value={usd(acc.equity - acc.balance, true)}
          cls={tone(acc.equity - acc.balance)}
        />
        <Card
          label={t("Open risk")}
          tip={t("Total loss if every open position hits its SL.")}
          value={usd(acc.open_risk)}
          sub={`${pct(acc.equity ? (acc.open_risk / acc.equity) * 100 : 0)}${s.max_open_risk_pct != null ? ` / ${t("cap {pct}%", { pct: s.max_open_risk_pct })}` : ""}`}
        />
        <Card label={t("Fees paid")} value={usd(acc.total_fees)} sub={t("net deposits {v}", { v: usd(acc.net_deposit) })} />
      </section>

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="rounded-xl border border-border bg-surface p-4 lg:col-span-2">
          <Equity id={acc.id} />
        </section>
        <section className="rounded-xl border border-border bg-surface p-4">
          {acc.is_exchange ? <ExchangePanel acc={acc} onChange={onChange} /> : <MoneyForm acc={acc} onChange={onChange} />}
        </section>
      </div>

      <section className="rounded-xl border border-border bg-surface p-4">
        <SettingsForm acc={acc} onChange={onChange} />
      </section>

      <section className="rounded-xl border border-border bg-surface p-4">
        <Ledger id={acc.id} currency={acc.currency} />
      </section>
    </>
  );
}

function Card({
  label,
  value,
  sub,
  tip,
  cls = "",
  big = false,
}: {
  label: string;
  value: string;
  sub?: string;
  tip?: string;
  cls?: string;
  big?: boolean;
}) {
  return (
    <div className={`rounded-xl border border-border bg-surface px-4 py-3 ${big ? "col-span-2 md:col-span-1" : ""}`}>
      <div className="text-xs text-faint">{tip ? <InfoTip text={tip} align="left">{label}</InfoTip> : label}</div>
      <div className={`mt-1 font-semibold tabular-nums ${big ? "text-xl" : "text-base"} ${cls}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-faint">{sub}</div>}
    </div>
  );
}

function Equity({ id }: { id: number }) {
  const [view, setView] = useState<"balance" | "pnl">("balance");
  const { data } = useQuery({
    queryKey: ["equity", id],
    queryFn: () => fetchEquity(id),
    refetchInterval: 15_000,
  });
  return (
    <>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold">{t("Equity history")}</h2>
        <div className="flex rounded-md border border-border text-xs">
          {(
            [
              ["balance", t("Equity")],
              ["pnl", t("PnL (excl. deposits/withdrawals)")],
            ] as const
          ).map(([k, l]) => (
            <button
              key={k}
              onClick={() => setView(k)}
              className={`px-2 py-1 ${view === k ? "bg-accent text-white" : "text-muted hover:bg-surface-2"}`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>
      {data && data[view].length > 1 ? (
        <EquityCurve data={data[view]} />
      ) : (
        <p className="py-10 text-center text-sm text-faint">{t("Not enough data to plot yet.")}</p>
      )}
    </>
  );
}

function ExchangePanel({ acc, onChange }: { acc: AccountInfo; onChange: () => void }) {
  const sync = useMutation({ mutationFn: () => syncAccount(acc.id), onSuccess: onChange });
  return (
    <>
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        {t("Binance Futures sync")} <ModeBadge mode={acc.mode} />
      </h2>
      <div className="space-y-2 text-sm">
        <p className="text-muted">
          {t(
            "Balance, margin and unrealized PnL come from the exchange; PnL, fees, funding and transfers are imported from the exchange's income history (automatically every 15 seconds).",
          )}
        </p>
        <p className="text-xs text-faint">
          {t("Last sync:")} {acc.last_sync_at ? new Date(acc.last_sync_at).toLocaleString() : t("never synced")}
        </p>
        {acc.sync_error && (
          <p className="rounded-md border border-down/40 bg-down/10 px-2 py-1.5 text-xs text-down">
            {t("Exchange connection error:")} {acc.sync_error}
          </p>
        )}
        <button
          onClick={() => sync.mutate()}
          disabled={sync.isPending}
          className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${sync.isPending ? "animate-spin" : ""}`} /> {t("Sync now")}
        </button>
        {sync.isError && <p className="text-xs text-down">{(sync.error as Error).message}</p>}
        <ExchangeCheck mode={acc.mode} />
        <p className="text-xs text-faint">
          {t("Deposits/withdrawals: transfer USDT Spot ↔ USDⓈ-M Futures on Binance — the ledger records them automatically.")}
          {acc.mode === "LIVE" && ` ⚠️ ${t("REAL-MONEY account.")}`}
        </p>
      </div>
    </>
  );
}

function MoneyForm({ acc, onChange }: { acc: AccountInfo; onChange: () => void }) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const move = useMutation({
    mutationFn: (kind: "in" | "out") =>
      (kind === "in" ? depositAccount : withdrawAccount)(acc.id, Number(amount), note || undefined),
    onSuccess: (r, kind) => {
      setMsg({
        ok: true,
        text: t(kind === "in" ? "Deposited {amount} {cur}. Wallet balance: {bal}" : "Withdrew {amount} {cur}. Wallet balance: {bal}", {
          amount,
          cur: acc.currency,
          bal: usd(r.balance),
        }),
      });
      setAmount("");
      setNote("");
      onChange();
    },
    onError: (e: Error) => setMsg({ ok: false, text: e.message }),
  });
  const valid = Number(amount) > 0;
  return (
    <>
      <h2 className="mb-3 text-sm font-semibold">{t("Deposit / withdraw (simulated)")}</h2>
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-faint">{t("Amount ({cur})", { cur: acc.currency })}</span>
          <input
            type="number"
            min={0}
            step="any"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="rounded-md border border-border bg-surface-2 px-2 py-1.5"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-faint">{t("Note (optional)")}</span>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="rounded-md border border-border bg-surface-2 px-2 py-1.5"
          />
        </label>
        <div className="flex gap-2">
          <button
            disabled={!valid || move.isPending}
            onClick={() => move.mutate("in")}
            className="flex flex-1 items-center justify-center gap-1 rounded-md bg-up/90 px-3 py-1.5 font-semibold text-white hover:bg-up disabled:opacity-50"
          >
            <ArrowDownToLine className="h-4 w-4" /> {t("Deposit")}
          </button>
          <button
            disabled={!valid || move.isPending}
            onClick={() => move.mutate("out")}
            className="flex flex-1 items-center justify-center gap-1 rounded-md border border-border px-3 py-1.5 font-semibold hover:bg-surface-2 disabled:opacity-50"
          >
            <ArrowUpFromLine className="h-4 w-4" /> {t("Withdraw")}
          </button>
        </div>
        <p className="text-xs text-faint">{t("Max withdrawal {v} (available balance, minus margin of open positions).", { v: usd(Math.max(0, acc.available)) })}</p>
        {msg && <p className={`text-xs ${msg.ok ? "text-up" : "text-down"}`}>{msg.text}</p>}
      </div>
    </>
  );
}

type FormVals = Record<keyof AccountSettings, string>;

const FIELDS: { k: keyof AccountSettings; label: string; tip: string; unit: string; optional?: boolean; scale?: number }[] = [
  { k: "leverage", label: t("Leverage"), tip: t("Margin = position value / leverage. Above 1× there is a liquidation price."), unit: "×" },
  { k: "taker_fee", label: t("Taker fee"), tip: t("Market orders, SL/TP. Binance Futures VIP0: 0.05%."), unit: "%", scale: 100 },
  { k: "maker_fee", label: t("Maker fee"), tip: t("Filled limit orders. Binance Futures VIP0: 0.02%."), unit: "%", scale: 100 },
  { k: "slippage_bps", label: t("Slippage"), tip: t("Market/stop orders fill at a worse price. 1 bps = 0.01%."), unit: "bps" },
  { k: "max_risk_pct", label: t("Max risk / trade"), tip: t("Trades requiring more risk than this are scaled down."), unit: t("% equity"), optional: true },
  { k: "max_open_risk_pct", label: t("Max total open risk"), tip: t("Total loss if every position hits its SL will not exceed this."), unit: t("% equity"), optional: true },
  { k: "max_positions", label: t("Max open positions"), tip: t("Number of positions open at the same time on the account."), unit: t("positions"), optional: true },
  { k: "daily_loss_pct", label: t("Max daily loss"), tip: t("When hit → no new positions until the end of the UTC day."), unit: "%", optional: true },
  { k: "max_dd_pct", label: t("Max drawdown"), tip: t("From peak equity. When hit → account HALTED until you unlock it."), unit: "%", optional: true },
];

const toForm = (s: AccountSettings): FormVals =>
  Object.fromEntries(
    FIELDS.map((f) => {
      const v = s[f.k];
      return [f.k, v == null ? "" : String(+(v * (f.scale ?? 1)).toPrecision(10))];
    }),
  ) as FormVals;

function SettingsForm({ acc, onChange }: { acc: AccountInfo; onChange: () => void }) {
  // exchange account: slippage is real (not simulated); fees are only used to estimate unrealized PnL
  const fields = acc.is_exchange ? FIELDS.filter((f) => f.k !== "slippage_bps") : FIELDS;
  const [vals, setVals] = useState<FormVals>(() => toForm(acc.settings));
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, number | null> = {};
      for (const f of fields) {
        const raw = vals[f.k].trim();
        if (raw === "") {
          if (f.optional) body[f.k] = null; // empty = guard disabled
          continue;
        }
        body[f.k] = Number(raw) / (f.scale ?? 1);
      }
      return patchAccount(acc.id, body);
    },
    onSuccess: (a) => {
      setVals(toForm(a.settings));
      setMsg({ ok: true, text: t("Saved — applies to new positions.") });
      onChange();
    },
    onError: (e: Error) => setMsg({ ok: false, text: e.message }),
  });
  return (
    <>
      <h2 className="mb-1 text-sm font-semibold">
        {acc.is_exchange ? t("Leverage & risk guards") : t("Exchange simulation & risk guards")}
      </h2>
      <p className="mb-3 text-xs text-faint">
        {acc.is_exchange
          ? t("Leverage is set on the exchange before each order. Fees are only used to estimate unrealized PnL — actual fees come from the exchange.")
          : t("Simulates Binance USDT-M Futures. Open positions keep the settings they were opened with.")}{" "}
        {t("Leave a guard field empty to disable it.")}
      </p>
      <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3 xl:grid-cols-5">
        {fields.map((f) => (
          <label key={f.k} className="flex flex-col gap-1">
            <span className="text-xs text-faint">
              <InfoTip text={f.tip} align="left">{f.label}</InfoTip>
            </span>
            <div className="flex items-center gap-1">
              <input
                type="number"
                min={0}
                step="any"
                value={vals[f.k]}
                placeholder={f.optional ? t("off") : ""}
                onChange={(e) => setVals({ ...vals, [f.k]: e.target.value })}
                className="w-full min-w-0 rounded-md border border-border bg-surface-2 px-2 py-1.5"
              />
              <span className="shrink-0 text-xs text-faint">{f.unit}</span>
            </div>
          </label>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
        >
          {t("Save settings")}
        </button>
        {msg && <span className={`text-xs ${msg.ok ? "text-up" : "text-down"}`}>{msg.text}</span>}
      </div>
    </>
  );
}

function Ledger({ id, currency }: { id: number; currency: string }) {
  const { data } = useQuery({
    queryKey: ["ledger", id],
    queryFn: () => fetchLedger(id),
    refetchInterval: 10_000,
  });
  return (
    <>
      <h2 className="mb-3 text-sm font-semibold">{t("Ledger (all balance changes)")}</h2>
      <div className="max-h-96 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface">
            <tr className="text-left text-xs uppercase tracking-wide text-faint">
              <th className="px-2 py-1.5 font-medium">{t("Time")}</th>
              <th className="px-2 py-1.5 font-medium">{t("Type")}</th>
              <th className="px-2 py-1.5 font-medium">{t("Details")}</th>
              <th className="px-2 py-1.5 text-right font-medium">{t("Amount")}</th>
              <th className="px-2 py-1.5 text-right font-medium">{t("Balance after")}</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((r) => (
              <tr key={r.id} className="border-t border-border">
                <td className="px-2 py-1.5 text-xs tabular-nums text-muted">{new Date(r.ts).toLocaleString()}</td>
                <td className="px-2 py-1.5">{TXN[r.type]}</td>
                <td className="px-2 py-1.5 text-xs text-muted">
                  {[r.symbol, r.bot_id != null ? `bot #${r.bot_id}` : null, r.position_id != null ? t("position #{id}", { id: r.position_id }) : null, r.note]
                    .filter(Boolean)
                    .join(" · ")}
                </td>
                <td className={`px-2 py-1.5 text-right tabular-nums ${tone(r.amount)}`}>
                  {Math.abs(r.amount) < 0.01 && r.amount !== 0
                    ? `${r.amount > 0 ? "+" : ""}${r.amount.toPrecision(3)}`
                    : usd(r.amount, true)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">{usd(r.balance_after)} {currency}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function CreateAccount({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("");
  const lens = useModeLens((s) => s.lens);
  const [mode, setMode] = useState<string>(lens || "PAPER");
  const [bal, setBal] = useState("1000");
  const [lev, setLev] = useState("1");
  const [confirm, setConfirm] = useState("");
  const paper = mode === "PAPER";
  const create = useMutation({
    mutationFn: () =>
      createAccount({
        name,
        mode,
        initial_balance: paper ? Number(bal) : null,
        leverage: Number(lev),
        ...(mode === "LIVE" ? { confirm } : {}),
      }),
    onSuccess: onDone,
  });
  const ok = name.trim() && (!paper || Number(bal) > 0) && (mode !== "LIVE" || confirm === "LIVE");
  return (
    <section className="rounded-xl border border-accent/40 bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold">{t("Create account")}</h2>
        <button onClick={onDone} className="rounded p-1 text-muted hover:bg-surface-2">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-faint">{t("Name")}</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("e.g. Test ict_po3 at 2% risk")}
            className="w-64 rounded-md border border-border bg-surface-2 px-2 py-1.5"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-faint">{t("Type")}</span>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            className="rounded-md border border-border bg-surface-2 px-2 py-1.5"
          >
            <option value="PAPER">{t("PAPER (simulated)")}</option>
            <option value="TESTNET">TESTNET (Binance Futures Demo Trading)</option>
            <option value="LIVE">{t("LIVE (real money)")}</option>
          </select>
        </label>
        {paper && (
          <label className="flex flex-col gap-1">
            <span className="text-xs text-faint">{t("Starting balance (USDT)")}</span>
            <input
              type="number"
              min={0}
              value={bal}
              onChange={(e) => setBal(e.target.value)}
              className="w-32 rounded-md border border-border bg-surface-2 px-2 py-1.5"
            />
          </label>
        )}
        {mode === "LIVE" && (
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-down">{t("Type LIVE to confirm")}</span>
            <input
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-28 rounded-md border border-down/60 bg-surface-2 px-2 py-1.5"
            />
          </label>
        )}
        <label className="flex flex-col gap-1">
          <span className="text-xs text-faint">{t("Leverage")}</span>
          <input
            type="number"
            min={1}
            max={20}
            value={lev}
            onChange={(e) => setLev(e.target.value)}
            className="w-20 rounded-md border border-border bg-surface-2 px-2 py-1.5"
          />
        </label>
        <button
          disabled={!ok || create.isPending}
          onClick={() => create.mutate()}
          className="rounded-md bg-accent px-3 py-1.5 font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
        >
          {t("Create")}
        </button>
      </div>
      <p className="mt-2 text-xs text-faint">
        {paper
          ? t("Defaults: fees 0.05%/0.02%, slippage 2 bps, max risk 2%/trade, total open risk 6%, daily loss 3%, drawdown 15%. Adjust later in the settings section.")
          : t(
              "Balance is read from the Binance USDⓈ-M Futures wallet {env} using the keys in .env ({keys}). One account per type. Default guards are the same as paper.",
              {
                env: mode === "TESTNET" ? "testnet" : t("(REAL MONEY)"),
                keys: mode === "TESTNET" ? "BINANCE_TESTNET_KEY/SECRET" : "BINANCE_KEY/SECRET + ENABLE_LIVE=1",
              },
            )}
      </p>
      {!paper && (
        <div className="mt-3 border-t border-border pt-3">
          <ExchangeCheck key={mode} mode={mode} auto />
        </div>
      )}
      {create.isError && <p className="mt-2 text-xs text-down">{(create.error as Error).message}</p>}
    </section>
  );
}
