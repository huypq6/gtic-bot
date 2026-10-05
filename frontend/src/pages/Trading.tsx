import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { Copy, Pause, Play, Square, Trash2 } from "lucide-react";
import {
  createBot,
  deleteBot,
  fetchAccounts,
  fetchBots,
  fetchConfig,
  fetchSizingMethods,
  fetchStrategies,
  patchBot,
  type BotInfo,
  type Sizing,
} from "../lib/api";
import ModeBadge from "../components/ModeBadge";
import { LensNote } from "../components/ModeLens";
import PositionsTable from "../components/orders/PositionsTable";
import ManualOrderForm from "../components/orders/ManualOrderForm";
import ParamsForm from "../components/strategy/ParamsForm";
import EnableLiveModal from "../components/live/EnableLiveModal";
import SizingInput, { sizingText } from "../components/account/SizingInput";
import { t } from "../lib/i18n";
import { inLens, useModeLens } from "../lib/modeLens";

export default function Trading() {
  const qc = useQueryClient();
  const { data: strategies } = useQuery({ queryKey: ["strategies"], queryFn: fetchStrategies });
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: fetchConfig });
  const { data: allBots } = useQuery({
    queryKey: ["bots"],
    queryFn: () => fetchBots(),
    refetchInterval: 5000,
  });
  const lens = useModeLens((s) => s.lens);
  const bots = allBots?.filter((b) => inLens(lens, b.mode));

  const [searchParams] = useSearchParams();
  const urlSymbol = searchParams.get("symbol");
  const [stratId, setStratId] = useState<number | "">("");
  const [symbol, setSymbol] = useState("");
  const [tf, setTf] = useState("");
  const [mode, setMode] = useState<string>(lens || "PAPER");
  // the create form follows the lens (All → keep the current choice)
  useEffect(() => {
    if (lens) setMode(lens);
  }, [lens]);
  const formRef = useRef<HTMLElement>(null);
  const cloneParams = useRef<Record<string, unknown> | null>(null);
  const [clonedFrom, setClonedFrom] = useState<number | null>(null);
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [showLiveModal, setShowLiveModal] = useState(false);
  const { data: accounts } = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });
  const { data: methods } = useQuery({ queryKey: ["sizing-methods"], queryFn: fetchSizingMethods });
  const [accountId, setAccountId] = useState<number | "">("");
  const [sizing, setSizing] = useState<Sizing>({ method: "risk_pct", value: 1 });
  const modeAccounts = (accounts ?? []).filter((a) => a.mode === mode);
  useEffect(() => {
    // on mode change → pick the first account of that mode (or leave empty if there is none)
    if (!modeAccounts.some((a) => a.id === accountId))
      setAccountId(modeAccounts.length ? modeAccounts[0].id : "");
  }, [modeAccounts, accountId]);

  const selectedStrat = strategies?.find((s) => s.id === stratId);
  // symbol from the scanner (?symbol=) may be outside the watchlist → add it to the options.
  const extra = [urlSymbol, symbol].filter(
    (x, i, a): x is string => !!x && !config?.symbols.includes(x) && a.indexOf(x) === i,
  );
  const symbolOptions = [...extra, ...(config?.symbols ?? [])];

  useEffect(() => {
    if (strategies?.length && stratId === "") setStratId(strategies[0].id);
  }, [strategies, stratId]);
  useEffect(() => {
    if (urlSymbol) setSymbol(urlSymbol);
  }, [urlSymbol]);
  // reset params to defaults when the strategy/version changes (a clone keeps the bot's params).
  useEffect(() => {
    if (!selectedStrat) return;
    setParams(cloneParams.current ?? { ...selectedStrat.default_params });
    cloneParams.current = null;
  }, [selectedStrat?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Clone (docs/08): pre-fill the create form from a bot + target mode; the user still presses
  // Create, so every guard (LIVE modal, account/mode check) stays on the single create path.
  const cloneTo = (b: BotInfo, target: string) => {
    if (b.strategy_id === stratId) setParams({ ...b.params });
    else cloneParams.current = { ...b.params };
    setStratId(b.strategy_id);
    setSymbol(b.symbol);
    setTf(b.tf);
    setMode(target);
    if (b.sizing) setSizing(b.sizing);
    setClonedFrom(b.id);
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  useEffect(() => {
    if (config && !symbol) {
      setSymbol(config.symbols[0]);
      setTf(config.default_tf);
    }
  }, [config, symbol]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["bots"] });
    qc.invalidateQueries({ queryKey: ["positions"] });
  };

  const create = useMutation({
    mutationFn: (confirm?: string) =>
      createBot({
        strategy_id: stratId as number,
        symbol,
        tf,
        mode,
        params,
        confirm,
        ...(accountId !== "" ? { account_id: accountId, sizing } : {}),
      }),
    onSuccess: () => {
      setShowLiveModal(false);
      setClonedFrom(null);
      refresh();
    },
  });

  const onCreate = () => {
    if (mode === "LIVE") setShowLiveModal(true);
    else create.mutate(undefined);
  };

  const setStatus = useMutation({
    mutationFn: (v: { id: number; status: string }) => patchBot(v.id, { status: v.status }),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: (id: number) => deleteBot(id), onSuccess: refresh });

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
      <LensNote />
      {/* Create bot */}
      <section ref={formRef} className="scroll-mt-4 rounded-xl border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold">{t("Create bot")}</h2>
        {clonedFrom != null && (
          <p className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-accent/30 bg-accent/10 px-3 py-1.5 text-xs">
            {t("Cloned from bot #{id} → {mode}. Review the settings, then press Create.", {
              id: clonedFrom,
              mode,
            })}
            <button onClick={() => setClonedFrom(null)} className="text-muted underline">
              {t("Dismiss")}
            </button>
          </p>
        )}
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Strategy">
            <select
              value={stratId}
              onChange={(e) => setStratId(Number(e.target.value))}
              className="rounded-md border border-border bg-surface-2 px-2 py-1.5 text-sm"
            >
              {strategies?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} v{s.version}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Symbol">
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="rounded-md border border-border bg-surface-2 px-2 py-1.5 text-sm"
            >
              {symbolOptions.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </Field>
          <Field label="TF">
            <select
              value={tf}
              onChange={(e) => setTf(e.target.value)}
              className="rounded-md border border-border bg-surface-2 px-2 py-1.5 text-sm"
            >
              {config?.timeframes.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </Field>
          <Field label="Mode">
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="rounded-md border border-border bg-surface-2 px-2 py-1.5 text-sm"
            >
              <option>PAPER</option>
              <option>TESTNET</option>
              <option>LIVE</option>
            </select>
          </Field>
          {modeAccounts.length > 0 && (
            <>
              <Field label={t("Account")}>
                <select
                  value={accountId}
                  onChange={(e) => setAccountId(Number(e.target.value))}
                  className="rounded-md border border-border bg-surface-2 px-2 py-1.5 text-sm"
                >
                  {modeAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({Math.round(a.equity).toLocaleString("en-US")} {a.currency})
                    </option>
                  ))}
                </select>
              </Field>
              <SizingInput value={sizing} onChange={setSizing} methods={methods} />
            </>
          )}
          <button
            onClick={onCreate}
            disabled={create.isPending || stratId === ""}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold disabled:opacity-50 ${
              mode === "LIVE"
                ? "bg-down text-white hover:bg-down/90"
                : "bg-accent text-white hover:bg-accent-strong"
            }`}
          >
            {create.isPending ? t("Creating…") : mode === "LIVE" ? t("Create (LIVE)") : t("Create & run")}
          </button>
        </div>
        {selectedStrat && Object.keys(selectedStrat.param_schema ?? {}).length > 0 && (
          <div className="mt-3 border-t border-border pt-3">
            <p className="mb-2 text-xs text-faint">{t("Params (tune without editing code)")}</p>
            <ParamsForm
              schema={selectedStrat.param_schema as Record<string, never>}
              values={params}
              onChange={setParams}
            />
          </div>
        )}
        {create.isError && <p className="mt-2 text-sm text-down">{t("Error: {msg}", { msg: (create.error as Error).message })}</p>}
      </section>

      {/* Bots */}
      <section className="rounded-xl border border-border bg-surface p-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          Bots {lens && <ModeBadge mode={lens} />}
          {lens && allBots && allBots.length > (bots?.length ?? 0) && (
            <span className="text-xs font-normal text-faint">
              {t("{n} more in other modes", { n: allBots.length - (bots?.length ?? 0) })}
            </span>
          )}
        </h2>
        {!bots?.length ? (
          <p className="text-sm text-faint">{lens ? t("No {mode} bots.", { mode: lens }) : t("No bots yet.")}</p>
        ) : (
          <div className="flex flex-col gap-2">
            {bots.map((b) => (
              <div
                key={b.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface-2 px-3 py-2"
              >
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <ModeBadge mode={b.mode} />
                  <span className="font-medium">{b.strategy}</span>
                  <span className="text-muted">
                    {b.symbol} · {b.tf}
                  </span>
                  <StatusDot status={b.status} />
                  <BotSizing bot={b} methods={methods} accountName={accounts?.find((a) => a.id === b.account_id)?.name} onSaved={refresh} />
                  <span
                    className="text-xs text-faint"
                    title={t("Last closed candle received by the bot (UTC)")}
                  >
                    {b.last_candle
                      ? t("last candle {time}", { time: new Date(b.last_candle).toISOString().slice(5, 16).replace("T", " ") })
                      : t("no candles yet")}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  {b.status !== "RUNNING" && (
                    <IconBtn title="Run" onClick={() => setStatus.mutate({ id: b.id, status: "RUNNING" })}>
                      <Play className="h-4 w-4" />
                    </IconBtn>
                  )}
                  {b.status === "RUNNING" && (
                    <IconBtn title="Pause" onClick={() => setStatus.mutate({ id: b.id, status: "PAUSED" })}>
                      <Pause className="h-4 w-4" />
                    </IconBtn>
                  )}
                  <IconBtn title="Stop" onClick={() => setStatus.mutate({ id: b.id, status: "STOPPED" })}>
                    <Square className="h-4 w-4" />
                  </IconBtn>
                  <CloneMenu bot={b} onPick={(m) => cloneTo(b, m)} />
                  <IconBtn title="Delete" onClick={() => remove.mutate(b.id)}>
                    <Trash2 className="h-4 w-4 text-down" />
                  </IconBtn>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {showLiveModal && (
        <EnableLiveModal
          symbol={symbol}
          onConfirm={() => create.mutate("LIVE")}
          onCancel={() => setShowLiveModal(false)}
        />
      )}

      {/* Manual order */}
      <section className="rounded-xl border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold">{t("Place manual order")}</h2>
        <ManualOrderForm />
      </section>

      {/* Positions realtime */}
      <section className="rounded-xl border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold">{t("Open positions (realtime PnL)")}</h2>
        <PositionsTable />
      </section>
    </div>
  );
}

// "Clone to…" — pick the target mode; to the same mode = run a second copy (e.g. new params).
function CloneMenu({ bot, onPick }: { bot: BotInfo; onPick: (mode: string) => void }) {
  const [open, setOpen] = useState(false);
  const hint: Record<string, string> = {
    PAPER: bot.mode === "LIVE" ? t("shadow") : "",
    TESTNET: "",
    LIVE: t("needs confirm"),
  };
  return (
    <div className="relative">
      <IconBtn title={t("Clone to…")} onClick={() => setOpen((o) => !o)}>
        <Copy className="h-4 w-4" />
      </IconBtn>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-20 mt-1 w-44 rounded-lg border border-border bg-surface p-1 text-sm shadow-lg">
            <p className="px-2 py-1 text-[11px] text-faint">{t("Clone to…")}</p>
            {["PAPER", "TESTNET", "LIVE"].map((m) => (
              <button
                key={m}
                onClick={() => {
                  setOpen(false);
                  onPick(m);
                }}
                className="flex w-full items-center justify-between rounded-md px-2 py-1.5 hover:bg-surface-2"
              >
                <ModeBadge mode={m} />
                <span className="text-[11px] text-faint">{hint[m]}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// Show + quick-edit the bot's position sizing (applies to the next order, no restart needed).
function BotSizing({
  bot,
  methods,
  accountName,
  onSaved,
}: {
  bot: BotInfo;
  methods?: Record<string, string>;
  accountName?: string;
  onSaved: () => void;
}) {
  const [edit, setEdit] = useState<Sizing | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (bot.account_id == null) return <span className="text-xs text-faint">{t("no account linked · strategy sizing")}</span>;
  const cur = bot.sizing ?? { method: "fixed_qty", value: 0 };
  if (!edit)
    return (
      <button
        onClick={() => setEdit(cur)}
        title={t("Edit order size")}
        className="rounded border border-border px-1.5 py-0.5 text-xs text-muted hover:bg-surface"
      >
        {accountName ?? t("Account #{id}", { id: bot.account_id })} · {sizingText(cur)}
      </button>
    );
  return (
    <span className="flex flex-wrap items-end gap-1">
      <SizingInput value={edit} onChange={setEdit} methods={methods} />
      <button
        onClick={async () => {
          try {
            await patchBot(bot.id, { sizing: edit });
            setEdit(null);
            setErr(null);
            onSaved();
          } catch (e) {
            setErr((e as Error).message);
          }
        }}
        className="rounded bg-accent px-2 py-1.5 text-xs font-medium text-white"
      >
        {t("Save")}
      </button>
      <button onClick={() => setEdit(null)} className="px-1.5 py-1.5 text-xs text-muted">
        {t("Cancel")}
      </button>
      {err && <span className="w-full text-xs text-down">{err}</span>}
    </span>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-faint">{label}</span>
      {children}
    </label>
  );
}

function IconBtn({
  title,
  onClick,
  children,
}: {
  title: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text"
    >
      {children}
    </button>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "RUNNING" ? "bg-up" : status === "PAUSED" ? "bg-warn" : "bg-faint";
  return (
    <span className="flex items-center gap-1 text-xs text-muted">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {status}
    </span>
  );
}
