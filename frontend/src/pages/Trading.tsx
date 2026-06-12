import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, Square, Trash2 } from "lucide-react";
import {
  createBot,
  deleteBot,
  fetchBots,
  fetchConfig,
  fetchStrategies,
  patchBot,
} from "../lib/api";
import ModeBadge from "../components/ModeBadge";
import PositionsTable from "../components/orders/PositionsTable";
import ManualOrderForm from "../components/orders/ManualOrderForm";
import ParamsForm from "../components/strategy/ParamsForm";
import EnableLiveModal from "../components/live/EnableLiveModal";

export default function Trading() {
  const qc = useQueryClient();
  const { data: strategies } = useQuery({ queryKey: ["strategies"], queryFn: fetchStrategies });
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: fetchConfig });
  const { data: bots } = useQuery({ queryKey: ["bots"], queryFn: fetchBots, refetchInterval: 5000 });

  const [stratId, setStratId] = useState<number | "">("");
  const [symbol, setSymbol] = useState("");
  const [tf, setTf] = useState("");
  const [mode, setMode] = useState("PAPER");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [showLiveModal, setShowLiveModal] = useState(false);

  const selectedStrat = strategies?.find((s) => s.id === stratId);

  useEffect(() => {
    if (strategies?.length && stratId === "") setStratId(strategies[0].id);
  }, [strategies, stratId]);
  // reset params về default khi đổi strategy/version.
  useEffect(() => {
    if (selectedStrat) setParams({ ...selectedStrat.default_params });
  }, [selectedStrat?.id]); // eslint-disable-line react-hooks/exhaustive-deps
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
      }),
    onSuccess: () => {
      setShowLiveModal(false);
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
      {/* Tạo bot */}
      <section className="rounded-xl border border-ink-700 bg-ink-900 p-4">
        <h2 className="mb-3 text-sm font-semibold">Tạo bot (PAPER)</h2>
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Strategy">
            <select
              value={stratId}
              onChange={(e) => setStratId(Number(e.target.value))}
              className="rounded-md border border-ink-700 bg-ink-800 px-2 py-1.5 text-sm"
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
              className="rounded-md border border-ink-700 bg-ink-800 px-2 py-1.5 text-sm"
            >
              {config?.symbols.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </Field>
          <Field label="TF">
            <select
              value={tf}
              onChange={(e) => setTf(e.target.value)}
              className="rounded-md border border-ink-700 bg-ink-800 px-2 py-1.5 text-sm"
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
              className="rounded-md border border-ink-700 bg-ink-800 px-2 py-1.5 text-sm"
            >
              <option>PAPER</option>
              <option>TESTNET</option>
              <option>LIVE</option>
            </select>
          </Field>
          <button
            onClick={onCreate}
            disabled={create.isPending || stratId === ""}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold disabled:opacity-50 ${
              mode === "LIVE"
                ? "bg-down text-ink-950 hover:bg-down/90"
                : "bg-accent-500 text-ink-950 hover:bg-accent-400"
            }`}
          >
            {create.isPending ? "Đang tạo…" : mode === "LIVE" ? "Tạo (LIVE)" : "Tạo & chạy"}
          </button>
        </div>
        {selectedStrat && Object.keys(selectedStrat.param_schema ?? {}).length > 0 && (
          <div className="mt-3 border-t border-ink-800 pt-3">
            <p className="mb-2 text-xs text-ink-500">Params (chỉnh không cần sửa code)</p>
            <ParamsForm
              schema={selectedStrat.param_schema as Record<string, never>}
              values={params}
              onChange={setParams}
            />
          </div>
        )}
        {create.isError && <p className="mt-2 text-sm text-down">Lỗi: {String(create.error)}</p>}
      </section>

      {/* Bots */}
      <section className="rounded-xl border border-ink-700 bg-ink-900 p-4">
        <h2 className="mb-3 text-sm font-semibold">Bots</h2>
        {!bots?.length ? (
          <p className="text-sm text-ink-500">Chưa có bot.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {bots.map((b) => (
              <div
                key={b.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-ink-800 bg-ink-850 px-3 py-2"
              >
                <div className="flex items-center gap-3">
                  <ModeBadge mode={b.mode} />
                  <span className="font-medium">{b.strategy}</span>
                  <span className="text-ink-400">
                    {b.symbol} · {b.tf}
                  </span>
                  <StatusDot status={b.status} />
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

      {/* Lệnh tay */}
      <section className="rounded-xl border border-ink-700 bg-ink-900 p-4">
        <h2 className="mb-3 text-sm font-semibold">Đặt lệnh tay</h2>
        <ManualOrderForm />
      </section>

      {/* Positions realtime */}
      <section className="rounded-xl border border-ink-700 bg-ink-900 p-4">
        <h2 className="mb-3 text-sm font-semibold">Vị thế mở (realtime PnL)</h2>
        <PositionsTable />
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-ink-500">{label}</span>
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
      className="rounded-md p-1.5 text-ink-300 hover:bg-ink-800 hover:text-ink-100"
    >
      {children}
    </button>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "RUNNING" ? "bg-up" : status === "PAUSED" ? "bg-amber-400" : "bg-ink-500";
  return (
    <span className="flex items-center gap-1 text-xs text-ink-400">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {status}
    </span>
  );
}
