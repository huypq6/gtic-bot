import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, ArrowUpFromLine, Plus, ShieldAlert, X } from "lucide-react";
import {
  createAccount,
  depositAccount,
  fetchAccounts,
  fetchEquity,
  fetchLedger,
  patchAccount,
  resumeAccount,
  withdrawAccount,
  type AccountInfo,
  type AccountSettings,
  type LedgerRow,
} from "../lib/api";
import EquityCurve from "../components/backtest/EquityCurve";
import InfoTip from "../components/InfoTip";

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
  DEPOSIT: "Nạp",
  WITHDRAW: "Rút",
  REALIZED_PNL: "Lãi/lỗ lệnh",
  FEE: "Phí",
  ADJUST: "Điều chỉnh",
};

export default function Account() {
  const qc = useQueryClient();
  const { data: accounts } = useQuery({
    queryKey: ["accounts"],
    queryFn: fetchAccounts,
    refetchInterval: 5000,
  });
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
            {a.name}
            <span className="ml-2 text-xs tabular-nums text-faint">{usd(a.equity)} {a.currency}</span>
          </button>
        ))}
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-1 rounded-lg border border-dashed border-border px-3 py-1.5 text-sm text-muted hover:bg-surface-2"
        >
          <Plus className="h-4 w-4" /> Tài khoản paper mới
        </button>
      </div>

      {creating && <CreateAccount onDone={() => { setCreating(false); refresh(); }} />}
      {!accounts?.length && !creating && (
        <p className="text-sm text-faint">Chưa có tài khoản. Tạo một tài khoản paper để bắt đầu.</p>
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
              {acc.status === "HALTED" ? "Tài khoản đã DỪNG — bot không vào lệnh mới" : "Tạm nghỉ đến hết ngày (UTC)"}
            </div>
            <div className="text-muted">
              {acc.halted_reason}
              {acc.paused_today && acc.halted_until && ` · mở lại lúc ${new Date(acc.halted_until).toLocaleString()}`}
              . Lệnh đang mở vẫn giữ SL/TP.
            </div>
          </div>
          <button
            onClick={() => resume.mutate()}
            className="rounded-md border border-down/50 px-3 py-1.5 text-xs font-medium text-down hover:bg-down/10"
          >
            Tôi đã xem xét — mở khóa
          </button>
        </div>
      )}

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-5">
        <Card
          big
          label="Tổng tài sản (equity)"
          tip="Số dư ví + lãi/lỗ tạm của lệnh đang mở."
          value={`${usd(acc.equity)} ${acc.currency}`}
        />
        <Card
          label="Lãi/lỗ tích lũy"
          tip="Equity − tiền nạp ròng (nạp − rút). Nạp/rút không tính là lãi/lỗ."
          value={usd(acc.total_pnl, true)}
          sub={acc.total_pnl_pct != null ? pct(acc.total_pnl_pct, true) : undefined}
          cls={tone(acc.total_pnl)}
        />
        <Card
          label="Hôm nay (UTC)"
          value={usd(acc.daily_pnl, true)}
          sub={`${pct(acc.daily_pnl_pct, true)}${s.daily_loss_pct != null ? ` · giới hạn -${s.daily_loss_pct}%` : ""}`}
          cls={tone(acc.daily_pnl)}
        />
        <Card
          label="Sụt vốn từ đỉnh"
          tip="Equity hiện tại so với đỉnh cao nhất (đã loại trừ nạp/rút). Chạm giới hạn → tài khoản DỪNG."
          value={pct(-acc.dd_pct)}
          sub={`đỉnh ${usd(acc.peak_equity)}${s.max_dd_pct != null ? ` · dừng ở -${s.max_dd_pct}%` : ""}`}
          cls={acc.dd_pct > 0 ? "text-down" : ""}
        />
        <Card label="Số dư ví" tip="Nạp − rút + lãi/lỗ đã chốt − phí." value={usd(acc.balance)} />
        <Card
          label="Ký quỹ đang dùng"
          value={usd(acc.used_margin)}
          sub={`${acc.n_open} lệnh mở · đòn bẩy ${s.leverage}×`}
        />
        <Card
          label="Khả dụng"
          tip="Có thể dùng để vào lệnh mới hoặc rút = equity − ký quỹ."
          value={usd(acc.available)}
        />
        <Card
          label="Lãi/lỗ tạm"
          value={usd(acc.equity - acc.balance, true)}
          cls={tone(acc.equity - acc.balance)}
        />
        <Card
          label="Rủi ro đang mở"
          tip="Tổng tiền sẽ mất nếu mọi lệnh đang mở chạm SL."
          value={usd(acc.open_risk)}
          sub={`${pct(acc.equity ? (acc.open_risk / acc.equity) * 100 : 0)}${s.max_open_risk_pct != null ? ` / trần ${s.max_open_risk_pct}%` : ""}`}
        />
        <Card label="Phí đã trả" value={usd(acc.total_fees)} sub={`nạp ròng ${usd(acc.net_deposit)}`} />
      </section>

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="rounded-xl border border-border bg-surface p-4 lg:col-span-2">
          <Equity id={acc.id} />
        </section>
        <section className="rounded-xl border border-border bg-surface p-4">
          <MoneyForm acc={acc} onChange={onChange} />
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
        <h2 className="text-sm font-semibold">Diễn biến vốn</h2>
        <div className="flex rounded-md border border-border text-xs">
          {(
            [
              ["balance", "Tài sản"],
              ["pnl", "Lãi/lỗ (bỏ nạp/rút)"],
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
        <p className="py-10 text-center text-sm text-faint">Chưa đủ dữ liệu để vẽ.</p>
      )}
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
      setMsg({ ok: true, text: `${kind === "in" ? "Đã nạp" : "Đã rút"} ${amount} ${acc.currency}. Số dư ví: ${usd(r.balance)}` });
      setAmount("");
      setNote("");
      onChange();
    },
    onError: (e: Error) => setMsg({ ok: false, text: e.message }),
  });
  const valid = Number(amount) > 0;
  return (
    <>
      <h2 className="mb-3 text-sm font-semibold">Nạp / rút (giả lập)</h2>
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-faint">Số tiền ({acc.currency})</span>
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
          <span className="text-xs text-faint">Ghi chú (tùy chọn)</span>
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
            <ArrowDownToLine className="h-4 w-4" /> Nạp
          </button>
          <button
            disabled={!valid || move.isPending}
            onClick={() => move.mutate("out")}
            className="flex flex-1 items-center justify-center gap-1 rounded-md border border-border px-3 py-1.5 font-semibold hover:bg-surface-2 disabled:opacity-50"
          >
            <ArrowUpFromLine className="h-4 w-4" /> Rút
          </button>
        </div>
        <p className="text-xs text-faint">Rút tối đa {usd(Math.max(0, acc.available))} (khả dụng, trừ ký quỹ lệnh đang mở).</p>
        {msg && <p className={`text-xs ${msg.ok ? "text-up" : "text-down"}`}>{msg.text}</p>}
      </div>
    </>
  );
}

type FormVals = Record<keyof AccountSettings, string>;

const FIELDS: { k: keyof AccountSettings; label: string; tip: string; unit: string; optional?: boolean; scale?: number }[] = [
  { k: "leverage", label: "Đòn bẩy", tip: "Ký quỹ = giá trị lệnh / đòn bẩy. >1× có giá thanh lý.", unit: "×" },
  { k: "taker_fee", label: "Phí taker", tip: "Lệnh market, SL/TP. Binance Futures VIP0: 0.05%.", unit: "%", scale: 100 },
  { k: "maker_fee", label: "Phí maker", tip: "Lệnh limit khớp. Binance Futures VIP0: 0.02%.", unit: "%", scale: 100 },
  { k: "slippage_bps", label: "Trượt giá", tip: "Lệnh market/stop khớp lệch bất lợi. 1 bps = 0.01%.", unit: "bps" },
  { k: "max_risk_pct", label: "Trần rủi ro / lệnh", tip: "Lệnh nào đòi rủi ro hơn mức này sẽ bị co lại.", unit: "% vốn", optional: true },
  { k: "max_open_risk_pct", label: "Trần tổng rủi ro mở", tip: "Tổng tiền mất nếu mọi lệnh chạm SL không vượt mức này.", unit: "% vốn", optional: true },
  { k: "max_positions", label: "Số lệnh mở tối đa", tip: "Số vị thế mở cùng lúc trên tài khoản.", unit: "lệnh", optional: true },
  { k: "daily_loss_pct", label: "Lỗ tối đa / ngày", tip: "Chạm → nghỉ vào lệnh mới đến hết ngày UTC.", unit: "%", optional: true },
  { k: "max_dd_pct", label: "Sụt vốn tối đa", tip: "Từ đỉnh equity. Chạm → DỪNG tài khoản đến khi bạn mở khóa.", unit: "%", optional: true },
];

const toForm = (s: AccountSettings): FormVals =>
  Object.fromEntries(
    FIELDS.map((f) => {
      const v = s[f.k];
      return [f.k, v == null ? "" : String(+(v * (f.scale ?? 1)).toPrecision(10))];
    }),
  ) as FormVals;

function SettingsForm({ acc, onChange }: { acc: AccountInfo; onChange: () => void }) {
  const [vals, setVals] = useState<FormVals>(() => toForm(acc.settings));
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, number | null> = {};
      for (const f of FIELDS) {
        const raw = vals[f.k].trim();
        if (raw === "") {
          if (f.optional) body[f.k] = null; // bỏ trống = tắt rào chắn
          continue;
        }
        body[f.k] = Number(raw) / (f.scale ?? 1);
      }
      return patchAccount(acc.id, body);
    },
    onSuccess: (a) => {
      setVals(toForm(a.settings));
      setMsg({ ok: true, text: "Đã lưu — áp dụng cho lệnh mới." });
      onChange();
    },
    onError: (e: Error) => setMsg({ ok: false, text: e.message }),
  });
  return (
    <>
      <h2 className="mb-1 text-sm font-semibold">Mô phỏng sàn & rào chắn rủi ro</h2>
      <p className="mb-3 text-xs text-faint">
        Mô phỏng Binance USDT-M Futures. Bỏ trống ô rào chắn = tắt. Lệnh đang mở giữ nguyên cấu hình lúc vào.
      </p>
      <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3 xl:grid-cols-5">
        {FIELDS.map((f) => (
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
                placeholder={f.optional ? "tắt" : ""}
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
          Lưu cấu hình
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
      <h2 className="mb-3 text-sm font-semibold">Sổ cái (mọi biến động số dư)</h2>
      <div className="max-h-96 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface">
            <tr className="text-left text-xs uppercase tracking-wide text-faint">
              <th className="px-2 py-1.5 font-medium">Thời gian</th>
              <th className="px-2 py-1.5 font-medium">Loại</th>
              <th className="px-2 py-1.5 font-medium">Chi tiết</th>
              <th className="px-2 py-1.5 text-right font-medium">Số tiền</th>
              <th className="px-2 py-1.5 text-right font-medium">Số dư sau</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((t) => (
              <tr key={t.id} className="border-t border-border">
                <td className="px-2 py-1.5 text-xs tabular-nums text-muted">{new Date(t.ts).toLocaleString()}</td>
                <td className="px-2 py-1.5">{TXN[t.type]}</td>
                <td className="px-2 py-1.5 text-xs text-muted">
                  {[t.symbol, t.bot_id != null ? `bot #${t.bot_id}` : null, t.position_id != null ? `lệnh #${t.position_id}` : null, t.note]
                    .filter(Boolean)
                    .join(" · ")}
                </td>
                <td className={`px-2 py-1.5 text-right tabular-nums ${tone(t.amount)}`}>
                  {Math.abs(t.amount) < 0.01 && t.amount !== 0
                    ? `${t.amount > 0 ? "+" : ""}${t.amount.toPrecision(3)}`
                    : usd(t.amount, true)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">{usd(t.balance_after)} {currency}</td>
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
  const [bal, setBal] = useState("1000");
  const [lev, setLev] = useState("1");
  const create = useMutation({
    mutationFn: () => createAccount({ name, initial_balance: Number(bal), leverage: Number(lev) }),
    onSuccess: onDone,
  });
  return (
    <section className="rounded-xl border border-accent/40 bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Tạo tài khoản paper</h2>
        <button onClick={onDone} className="rounded p-1 text-muted hover:bg-surface-2">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-faint">Tên</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="vd Thử ict_po3 rủi ro 2%"
            className="w-64 rounded-md border border-border bg-surface-2 px-2 py-1.5"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-faint">Vốn ban đầu (USDT)</span>
          <input
            type="number"
            min={0}
            value={bal}
            onChange={(e) => setBal(e.target.value)}
            className="w-32 rounded-md border border-border bg-surface-2 px-2 py-1.5"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-faint">Đòn bẩy</span>
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
          disabled={!name.trim() || !(Number(bal) > 0) || create.isPending}
          onClick={() => create.mutate()}
          className="rounded-md bg-accent px-3 py-1.5 font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
        >
          Tạo
        </button>
      </div>
      <p className="mt-2 text-xs text-faint">
        Mặc định: phí 0.05%/0.02%, trượt 2 bps, rủi ro tối đa 2%/lệnh, tổng rủi ro mở 6%, lỗ ngày 3%, sụt vốn 15%. Chỉnh sau trong phần cấu hình.
      </p>
      {create.isError && <p className="mt-2 text-xs text-down">{(create.error as Error).message}</p>}
    </section>
  );
}
