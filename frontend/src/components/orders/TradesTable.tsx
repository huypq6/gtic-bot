import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LineChart } from "lucide-react";
import { fetchTrades, type TradeRow } from "../../lib/api";
import ModeBadge from "../ModeBadge";
import InfoTip from "../InfoTip";
import TradeDetail, { fmtPrice } from "../backtest/TradeDetail";

const RESULT: Record<TradeRow["result"], { label: string; cls: string }> = {
  WIN: { label: "THẮNG", cls: "bg-up/15 text-up" },
  LOSS: { label: "THUA", cls: "bg-down/15 text-down" },
  BE: { label: "HÒA", cls: "bg-surface-2 text-muted" },
  OPEN: { label: "ĐANG MỞ", cls: "bg-warn/15 text-warn" },
};

const REASON: Record<string, string> = {
  SL: "Chạm SL",
  TP: "Chạm TP",
  SIGNAL: "Tín hiệu đóng",
  MANUAL: "Đóng tay",
};

const signed = (n: number | null, d = 2, suffix = "") =>
  n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(d)}${suffix}`;

// Tiền (USDT): số nhỏ (paper size bé) vẫn hiện được chữ số có nghĩa.
const money = (n: number | null) =>
  n == null
    ? "—"
    : `${n >= 0 ? "+" : ""}${n.toLocaleString("en-US", {
        maximumSignificantDigits: Math.abs(n) >= 1 ? 6 : 3,
      })}`;

const tone = (n: number | null) => (n == null ? "" : n >= 0 ? "text-up" : "text-down");

// "ict_po3 v4" | "Bot #5 (đã xóa)" | "Lệnh tay"
const stratLabel = (t: TradeRow) =>
  t.strategy ?? (t.source === "BOT" ? `Bot${t.bot_ref != null ? ` #${t.bot_ref}` : ""} (đã xóa)` : "Lệnh tay");

const botLabel = (t: TradeRow) =>
  t.bot_ref != null ? `bot #${t.bot_ref}${t.bot_deleted ? " (đã xóa)" : ""}` : "tay";

// Quy đổi: lot paper bé → PnL thật ~0. Đặt "1R = X USDT" (rủi ro mỗi lệnh) → PnL quy đổi = R × X,
// so được giữa các cặp và ra con số dễ hình dung. Lưu theo trình duyệt.
const RISK_KEY = "gtic.riskPerR";
const loadRisk = () => {
  try {
    const v = Number(localStorage.getItem(RISK_KEY));
    return v > 0 ? v : 10;
  } catch {
    return 10;
  }
};
const usd = (n: number | null) =>
  n == null ? "—" : `${n >= 0 ? "+" : "-"}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function duration(from: number, to: number | null) {
  const m = Math.round(((to ?? Date.now()) - from) / 60_000);
  if (m < 60) return `${m}p`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h}h${m % 60 ? `${m % 60}p` : ""}` : `${Math.floor(h / 24)}d${h % 24}h`;
}

export default function TradesTable() {
  const [mode, setMode] = useState("");
  const [risk, setRisk] = useState(loadRisk);
  const changeRisk = (v: number) => {
    setRisk(v);
    try {
      if (v > 0) localStorage.setItem(RISK_KEY, String(v));
    } catch {
      /* private mode — bỏ qua */
    }
  };
  const [symbol, setSymbol] = useState("");
  const [sel, setSel] = useState<TradeRow | null>(null);
  const { data: trades } = useQuery({
    queryKey: ["trades", mode, symbol],
    queryFn: () => fetchTrades({ mode, symbol }),
    refetchInterval: 10_000,
  });

  const closed = (trades ?? []).filter((t) => t.status === "CLOSED");
  const wins = closed.filter((t) => t.result === "WIN").length;
  const sumPnl = closed.reduce((a, t) => a + (t.pnl ?? 0), 0);
  const rs = closed.filter((t) => t.r != null);
  const sumR = rs.reduce((a, t) => a + (t.r ?? 0), 0);

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div className="flex flex-wrap gap-2 text-xs">
          <Stat label="Lệnh đã đóng" value={`${closed.length}`} />
          <Stat
            label="Thắng / Thua"
            value={`${wins} / ${closed.length - wins}`}
            sub={closed.length ? `${((wins / closed.length) * 100).toFixed(0)}% winrate` : undefined}
          />
          <Stat
            label={`PnL quy đổi (1R = $${risk})`}
            value={usd(sumR * risk)}
            cls={tone(sumR)}
            sub={`thực tế ${money(sumPnl)} USDT`}
          />
          <Stat
            label="Tổng R"
            value={signed(sumR, 2, "R")}
            cls={tone(sumR)}
            sub={rs.length ? `TB ${signed(sumR / rs.length, 2, "R")}/lệnh` : undefined}
          />
        </div>
        <div className="flex items-end gap-2 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-faint">
              <InfoTip text="Số tiền chấp nhận mất mỗi lệnh (1R) để quy đổi PnL. Lot paper nhỏ nên PnL thật gần 0 — quy đổi = R × số này, so được giữa các cặp.">
                1R = USDT
              </InfoTip>
            </span>
            <input
              type="number"
              min={0}
              step="any"
              value={risk}
              onChange={(e) => changeRisk(Number(e.target.value))}
              className="w-20 rounded-md border border-border bg-surface-2 px-2 py-1.5"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-faint">Mode</span>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="rounded-md border border-border bg-surface-2 px-2 py-1.5"
            >
              <option value="">Tất cả</option>
              {["PAPER", "TESTNET", "LIVE"].map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-faint">Symbol</span>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="vd BTCUSDT"
              className="w-28 rounded-md border border-border bg-surface-2 px-2 py-1.5"
            />
          </label>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-faint">
              <th className="px-2 py-1.5 font-medium">Vào lúc</th>
              <th className="px-2 py-1.5 font-medium">Chiến lược</th>
              <th className="px-2 py-1.5 font-medium">Symbol</th>
              <th className="px-2 py-1.5 font-medium">Side</th>
              <th className="px-2 py-1.5 text-right font-medium">Entry → Exit</th>
              <th className="px-2 py-1.5 font-medium">Kết quả</th>
              <th className="px-2 py-1.5 text-right font-medium">PnL quy đổi</th>
              <th className="px-2 py-1.5 text-right font-medium">
                <InfoTip term="r">R</InfoTip>
              </th>
              <th className="px-2 py-1.5 text-right font-medium">
                <InfoTip term="mfe">MFE</InfoTip>
              </th>
              <th className="px-2 py-1.5 text-right font-medium">
                <InfoTip term="mae">MAE</InfoTip>
              </th>
              <th className="px-2 py-1.5 text-right font-medium">Giữ</th>
              <th className="px-2 py-1.5" />
            </tr>
          </thead>
          <tbody>
            {(trades ?? []).map((t) => (
              <tr
                key={t.id}
                onClick={() => setSel(t)}
                className="cursor-pointer border-t border-border hover:bg-surface-2"
              >
                <td className="px-2 py-1.5 text-xs tabular-nums text-muted">
                  {new Date(t.opened_at).toLocaleString()}
                  <div className="mt-0.5">
                    <ModeBadge mode={t.mode} />
                  </div>
                </td>
                <td className="px-2 py-1.5">
                  <div className="font-medium">{stratLabel(t)}</div>
                  <div className="text-xs text-faint">
                    {botLabel(t)}
                    {t.tf ? ` · ${t.tf}` : ""}
                  </div>
                </td>
                <td className="px-2 py-1.5 font-medium">{t.symbol}</td>
                <td className={`px-2 py-1.5 font-medium ${t.side === "LONG" ? "text-up" : "text-down"}`}>
                  {t.side}
                </td>
                <td className="px-2 py-1.5 text-right text-xs tabular-nums">
                  {fmtPrice(t.entry_price)} → {fmtPrice(t.exit_price)}
                  <div className="text-faint">{t.exit_reason ? REASON[t.exit_reason] ?? t.exit_reason : ""}</div>
                </td>
                <td className="px-2 py-1.5">
                  <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${RESULT[t.result].cls}`}>
                    {RESULT[t.result].label}
                  </span>
                </td>
                <td className={`px-2 py-1.5 text-right tabular-nums ${tone(t.r ?? t.pnl)}`}>
                  <span className="font-medium">{usd(t.r != null ? t.r * risk : null)}</span>
                  <div className="text-xs">{signed(t.pnl_pct, 2, "%")}</div>
                  <div className="text-[11px] text-faint" title="PnL thật theo khối lượng bot đã đặt">
                    thật {money(t.pnl)}
                  </div>
                </td>
                <td className={`px-2 py-1.5 text-right font-medium tabular-nums ${tone(t.r)}`}>
                  {signed(t.r, 2, "R")}
                </td>
                <td className="px-2 py-1.5 text-right text-xs tabular-nums text-up">
                  {signed(t.mfe_pct, 2, "%")}
                  <div>{t.mfe_r != null ? signed(t.mfe_r, 2, "R") : ""}</div>
                </td>
                <td className="px-2 py-1.5 text-right text-xs tabular-nums text-down">
                  {t.mae_pct != null ? signed(-t.mae_pct, 2, "%") : "—"}
                  <div>{t.mae_r != null ? signed(-t.mae_r, 2, "R") : ""}</div>
                </td>
                <td className="px-2 py-1.5 text-right text-xs tabular-nums text-muted">
                  {duration(t.opened_at, t.closed_at)}
                </td>
                <td className="px-2 py-1.5 text-right">
                  <LineChart className="inline h-4 w-4 text-muted" aria-label="Xem biểu đồ" />
                </td>
              </tr>
            ))}
            {!trades?.length && (
              <tr>
                <td colSpan={12} className="px-2 py-4 text-sm text-faint">
                  Chưa có lệnh nào.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {sel && <TradeReview t={sel} risk={risk} onClose={() => setSel(null)} />}
    </>
  );
}

function Stat({ label, value, sub, cls = "" }: { label: string; value: string; sub?: string; cls?: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface-2 px-3 py-1.5">
      <div className="text-faint">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${cls}`}>{value}</div>
      {sub && <div className="text-faint">{sub}</div>}
    </div>
  );
}

// Modal review 1 lệnh: số liệu + biểu đồ nến quanh lệnh (vào/ra/SL/TP/MFE/MAE) + phát lại.
function TradeReview({ t, risk, onClose }: { t: TradeRow; risk: number; onClose: () => void }) {
  const r = RESULT[t.result];
  const time = (ms: number | null) => (ms ? new Date(ms).toLocaleString() : "—");
  const Item = ({ k, v, cls = "" }: { k: string; v: string; cls?: string }) => (
    <div className="flex justify-between gap-2">
      <span className="text-faint">{k}</span>
      <span className={`tabular-nums ${cls}`}>{v}</span>
    </div>
  );
  return (
    <TradeDetail
      symbol={t.symbol}
      tf={t.tf ?? "1m"}
      index={t.id}
      tfChoices={[...new Set(["1m", t.tf ?? "1m"])]} // server chỉ lưu 1m + tf của bot
      trade={{
        side: t.side === "LONG" ? "Long" : "Short",
        entry_ts: t.opened_at,
        entry: t.entry_price,
        exit_ts: t.closed_at,
        exit: t.exit_price,
        pnl_pct: t.pnl_pct,
        sl: t.init_sl ?? t.sl,
        tp: t.tp,
      }}
      extraLines={[
        ...(t.mfe_price != null ? [{ price: t.mfe_price, title: "MFE", tone: "up" as const }] : []),
        ...(t.mae_price != null ? [{ price: t.mae_price, title: "MAE", tone: "down" as const }] : []),
      ]}
      onClose={onClose}
      title={
        <span className="flex flex-wrap items-center gap-2">
          <span>
            Lệnh #{t.id} · {t.symbol} ·{" "}
            <span className={t.side === "LONG" ? "text-up" : "text-down"}>{t.side}</span>
          </span>
          <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${r.cls}`}>{r.label}</span>
          <span className={tone(t.pnl)}>
            {signed(t.r, 2, "R")} ≈ {usd(t.r != null ? t.r * risk : null)}
          </span>
        </span>
      }
      info={
        <div className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
          <div className="space-y-1">
            <Item k="Chiến lược" v={stratLabel(t)} />
            <Item k="Bot / khung" v={`${botLabel(t)} · ${t.tf ?? "—"}`} />
            <Item k="Vào lúc" v={time(t.opened_at)} />
            <Item k="Ra lúc" v={time(t.closed_at)} />
            <Item k="Thời gian giữ" v={duration(t.opened_at, t.closed_at)} />
          </div>
          <div className="space-y-1">
            <Item k="Entry" v={fmtPrice(t.entry_price)} />
            <Item k="Exit" v={`${fmtPrice(t.exit_price)}${t.exit_reason ? ` (${REASON[t.exit_reason] ?? t.exit_reason})` : ""}`} />
            <Item k="SL ban đầu / TP" v={`${fmtPrice(t.init_sl ?? t.sl)} / ${fmtPrice(t.tp)}`} />
            <Item k="Khối lượng" v={`${t.qty} (${t.notional.toLocaleString("en-US", { maximumSignificantDigits: 4 })} USDT)`} />
            <Item k="Rủi ro 1R (thật)" v={t.risk_amount != null ? `${money(t.risk_amount).replace("+", "")} USDT` : "—"} />
          </div>
          <div className="space-y-1">
            <Item k={`PnL quy đổi (1R = $${risk})`} v={usd(t.r != null ? t.r * risk : null)} cls={tone(t.r)} />
            <Item k="PnL thật" v={`${money(t.pnl)} USDT (${signed(t.pnl_pct, 2, "%")})`} cls={tone(t.pnl)} />
            <Item k="R thực hiện" v={signed(t.r, 2, "R")} cls={tone(t.r)} />
            <Item
              k="MFE (lời tối đa)"
              v={`${signed(t.mfe_pct, 2, "%")}${t.mfe_r != null ? ` · ${signed(t.mfe_r, 2, "R")} ≈ ${usd(t.mfe_r * risk)}` : ""} @ ${fmtPrice(t.mfe_price)}`}
              cls="text-up"
            />
            <Item
              k="MAE (lỗ tối đa)"
              v={`${t.mae_pct != null ? signed(-t.mae_pct, 2, "%") : "—"}${t.mae_r != null ? ` · ${signed(-t.mae_r, 2, "R")} ≈ ${usd(-t.mae_r * risk)}` : ""} @ ${fmtPrice(t.mae_price)}`}
              cls="text-down"
            />
            <Item k="Lúc MFE / MAE" v={`${t.mfe_ts ? new Date(t.mfe_ts).toLocaleTimeString() : "—"} / ${t.mae_ts ? new Date(t.mae_ts).toLocaleTimeString() : "—"}`} />
          </div>
          {t.params && (
            <details className="sm:col-span-3">
              <summary className="cursor-pointer text-faint">Tham số bot lúc vào lệnh</summary>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-muted">
                {Object.entries(t.params).map(([k, v]) => (
                  <span key={k}>
                    {k}={String(v)}
                  </span>
                ))}
              </div>
            </details>
          )}
        </div>
      }
    />
  );
}
