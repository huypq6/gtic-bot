import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LineChart } from "lucide-react";
import { fetchTrades, type TradeRow } from "../../lib/api";
import ModeBadge from "../ModeBadge";
import InfoTip from "../InfoTip";
import TradeDetail, { fmtPrice } from "../backtest/TradeDetail";
import { t } from "../../lib/i18n";

const RESULT: Record<TradeRow["result"], { label: string; cls: string }> = {
  WIN: { label: t("WIN"), cls: "bg-up/15 text-up" },
  LOSS: { label: t("LOSS"), cls: "bg-down/15 text-down" },
  BE: { label: t("BREAKEVEN"), cls: "bg-surface-2 text-muted" },
  OPEN: { label: t("OPEN"), cls: "bg-warn/15 text-warn" },
};

const REASON: Record<string, string> = {
  SL: t("SL hit"),
  TP: t("TP hit"),
  SIGNAL: t("Exit signal"),
  MANUAL: t("Manual close"),
  LIQUIDATION: t("Liquidated"),
};

const signed = (n: number | null, d = 2, suffix = "") =>
  n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(d)}${suffix}`;

// Money (USDT): small amounts (tiny paper sizes) still show significant digits.
const money = (n: number | null) =>
  n == null
    ? "—"
    : `${n >= 0 ? "+" : ""}${n.toLocaleString("en-US", {
        maximumSignificantDigits: Math.abs(n) >= 1 ? 6 : 3,
      })}`;

const tone = (n: number | null) => (n == null ? "" : n >= 0 ? "text-up" : "text-down");

// "ict_po3 v4" | "Bot #5 (deleted)" | "Manual order"
const stratLabel = (tr: TradeRow) =>
  tr.strategy ??
  (tr.source === "BOT"
    ? tr.bot_ref != null
      ? t("Bot #{id} (deleted)", { id: tr.bot_ref })
      : t("Bot (deleted)")
    : t("Manual order"));

const botLabel = (tr: TradeRow) =>
  tr.bot_ref != null ? `bot #${tr.bot_ref}${tr.bot_deleted ? ` ${t("(deleted)")}` : ""}` : t("manual");

// Normalization: tiny paper lots → real PnL ~0. Set "1R = X USDT" (risk per trade) → normalized PnL = R × X,
// comparable across pairs and easy to picture. Stored per browser.
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
  if (m < 60) return t("{n}m", { n: m });
  const h = Math.floor(m / 60);
  return h < 24 ? `${h}h${m % 60 ? t("{n}m", { n: m % 60 }) : ""}` : `${Math.floor(h / 24)}d${h % 24}h`;
}

export default function TradesTable() {
  const [mode, setMode] = useState("");
  const [risk, setRisk] = useState(loadRisk);
  const changeRisk = (v: number) => {
    setRisk(v);
    try {
      if (v > 0) localStorage.setItem(RISK_KEY, String(v));
    } catch {
      /* private mode — ignore */
    }
  };
  const [symbol, setSymbol] = useState("");
  const [sel, setSel] = useState<TradeRow | null>(null);
  const { data: trades } = useQuery({
    queryKey: ["trades", mode, symbol],
    queryFn: () => fetchTrades({ mode, symbol }),
    refetchInterval: 10_000,
  });

  const closed = (trades ?? []).filter((tr) => tr.status === "CLOSED");
  const wins = closed.filter((tr) => tr.result === "WIN").length;
  const sumPnl = closed.reduce((a, tr) => a + (tr.pnl ?? 0), 0);
  const rs = closed.filter((tr) => tr.r != null);
  const sumR = rs.reduce((a, tr) => a + (tr.r ?? 0), 0);

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div className="flex flex-wrap gap-2 text-xs">
          <Stat label={t("Closed trades")} value={`${closed.length}`} />
          <Stat
            label={t("Wins / Losses")}
            value={`${wins} / ${closed.length - wins}`}
            sub={closed.length ? `${((wins / closed.length) * 100).toFixed(0)}% winrate` : undefined}
          />
          <Stat
            label={t("Normalized PnL (1R = ${risk})", { risk })}
            value={usd(sumR * risk)}
            cls={tone(sumR)}
            sub={t("actual {v} USDT", { v: money(sumPnl) })}
          />
          <Stat
            label={t("Total R")}
            value={signed(sumR, 2, "R")}
            cls={tone(sumR)}
            sub={rs.length ? t("avg {v}/trade", { v: signed(sumR / rs.length, 2, "R") }) : undefined}
          />
        </div>
        <div className="flex items-end gap-2 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-faint">
              <InfoTip text={t("Amount you accept to lose per trade (1R), used to normalize PnL. Paper lots are tiny so real PnL is near 0 — normalized = R × this amount, comparable across pairs.")}>
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
              <option value="">{t("All")}</option>
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
              placeholder={t("e.g. BTCUSDT")}
              className="w-28 rounded-md border border-border bg-surface-2 px-2 py-1.5"
            />
          </label>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-faint">
              <th className="px-2 py-1.5 font-medium">{t("Opened")}</th>
              <th className="px-2 py-1.5 font-medium">{t("Strategy")}</th>
              <th className="px-2 py-1.5 font-medium">Symbol</th>
              <th className="px-2 py-1.5 font-medium">Side</th>
              <th className="px-2 py-1.5 text-right font-medium">Entry → Exit</th>
              <th className="px-2 py-1.5 font-medium">{t("Result")}</th>
              <th className="px-2 py-1.5 text-right font-medium">{t("Normalized PnL")}</th>
              <th className="px-2 py-1.5 text-right font-medium">
                <InfoTip term="r">R</InfoTip>
              </th>
              <th className="px-2 py-1.5 text-right font-medium">
                <InfoTip term="mfe">MFE</InfoTip>
              </th>
              <th className="px-2 py-1.5 text-right font-medium">
                <InfoTip term="mae">MAE</InfoTip>
              </th>
              <th className="px-2 py-1.5 text-right font-medium">{t("Held")}</th>
              <th className="px-2 py-1.5" />
            </tr>
          </thead>
          <tbody>
            {(trades ?? []).map((tr) => (
              <tr
                key={tr.id}
                onClick={() => setSel(tr)}
                className="cursor-pointer border-t border-border hover:bg-surface-2"
              >
                <td className="px-2 py-1.5 text-xs tabular-nums text-muted">
                  {new Date(tr.opened_at).toLocaleString()}
                  <div className="mt-0.5">
                    <ModeBadge mode={tr.mode} />
                  </div>
                </td>
                <td className="px-2 py-1.5">
                  <div className="font-medium">{stratLabel(tr)}</div>
                  <div className="text-xs text-faint">
                    {botLabel(tr)}
                    {tr.tf ? ` · ${tr.tf}` : ""}
                  </div>
                </td>
                <td className="px-2 py-1.5 font-medium">{tr.symbol}</td>
                <td className={`px-2 py-1.5 font-medium ${tr.side === "LONG" ? "text-up" : "text-down"}`}>
                  {tr.side}
                </td>
                <td className="px-2 py-1.5 text-right text-xs tabular-nums">
                  {fmtPrice(tr.entry_price)} → {fmtPrice(tr.exit_price)}
                  <div className="text-faint">{tr.exit_reason ? REASON[tr.exit_reason] ?? tr.exit_reason : ""}</div>
                </td>
                <td className="px-2 py-1.5">
                  <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${RESULT[tr.result].cls}`}>
                    {RESULT[tr.result].label}
                  </span>
                </td>
                <td className={`px-2 py-1.5 text-right tabular-nums ${tone(tr.r ?? tr.pnl)}`}>
                  <span className="font-medium">{usd(tr.r != null ? tr.r * risk : null)}</span>
                  <div className="text-xs">{signed(tr.pnl_pct, 2, "%")}</div>
                  <div className="text-[11px] text-faint" title={t("Real PnL based on the size the bot placed")}>
                    {t("real {v}", { v: money(tr.pnl) })}
                  </div>
                </td>
                <td className={`px-2 py-1.5 text-right font-medium tabular-nums ${tone(tr.r)}`}>
                  {signed(tr.r, 2, "R")}
                </td>
                <td className="px-2 py-1.5 text-right text-xs tabular-nums text-up">
                  {signed(tr.mfe_pct, 2, "%")}
                  <div>{tr.mfe_r != null ? signed(tr.mfe_r, 2, "R") : ""}</div>
                </td>
                <td className="px-2 py-1.5 text-right text-xs tabular-nums text-down">
                  {tr.mae_pct != null ? signed(-tr.mae_pct, 2, "%") : "—"}
                  <div>{tr.mae_r != null ? signed(-tr.mae_r, 2, "R") : ""}</div>
                </td>
                <td className="px-2 py-1.5 text-right text-xs tabular-nums text-muted">
                  {duration(tr.opened_at, tr.closed_at)}
                </td>
                <td className="px-2 py-1.5 text-right">
                  <LineChart className="inline h-4 w-4 text-muted" aria-label={t("View chart")} />
                </td>
              </tr>
            ))}
            {!trades?.length && (
              <tr>
                <td colSpan={12} className="px-2 py-4 text-sm text-faint">
                  {t("No trades yet.")}
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

// Single-trade review modal: stats + candle chart around the trade (entry/exit/SL/TP/MFE/MAE) + replay.
function TradeReview({ t: tr, risk, onClose }: { t: TradeRow; risk: number; onClose: () => void }) {
  const r = RESULT[tr.result];
  const time = (ms: number | null) => (ms ? new Date(ms).toLocaleString() : "—");
  const Item = ({ k, v, cls = "" }: { k: string; v: string; cls?: string }) => (
    <div className="flex justify-between gap-2">
      <span className="text-faint">{k}</span>
      <span className={`tabular-nums ${cls}`}>{v}</span>
    </div>
  );
  return (
    <TradeDetail
      symbol={tr.symbol}
      tf={tr.tf ?? "1m"}
      index={tr.id}
      tfChoices={[...new Set(["1m", tr.tf ?? "1m"])]} // server only stores 1m + the bot's tf
      trade={{
        side: tr.side === "LONG" ? "Long" : "Short",
        entry_ts: tr.opened_at,
        entry: tr.entry_price,
        exit_ts: tr.closed_at,
        exit: tr.exit_price,
        pnl_pct: tr.pnl_pct,
        sl: tr.init_sl ?? tr.sl,
        tp: tr.tp,
      }}
      extraLines={[
        ...(tr.mfe_price != null ? [{ price: tr.mfe_price, title: "MFE", tone: "up" as const }] : []),
        ...(tr.mae_price != null ? [{ price: tr.mae_price, title: "MAE", tone: "down" as const }] : []),
      ]}
      onClose={onClose}
      title={
        <span className="flex flex-wrap items-center gap-2">
          <span>
            {t("Trade #{id}", { id: tr.id })} · {tr.symbol} ·{" "}
            <span className={tr.side === "LONG" ? "text-up" : "text-down"}>{tr.side}</span>
          </span>
          <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${r.cls}`}>{r.label}</span>
          <span className={tone(tr.pnl)}>
            {signed(tr.r, 2, "R")} ≈ {usd(tr.r != null ? tr.r * risk : null)}
          </span>
        </span>
      }
      info={
        <div className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
          <div className="space-y-1">
            <Item k={t("Strategy")} v={stratLabel(tr)} />
            <Item k={t("Bot / timeframe")} v={`${botLabel(tr)} · ${tr.tf ?? "—"}`} />
            <Item k={t("Opened")} v={time(tr.opened_at)} />
            <Item k={t("Closed")} v={time(tr.closed_at)} />
            <Item k={t("Holding time")} v={duration(tr.opened_at, tr.closed_at)} />
          </div>
          <div className="space-y-1">
            <Item k="Entry" v={fmtPrice(tr.entry_price)} />
            <Item k="Exit" v={`${fmtPrice(tr.exit_price)}${tr.exit_reason ? ` (${REASON[tr.exit_reason] ?? tr.exit_reason})` : ""}`} />
            <Item k={t("Initial SL / TP")} v={`${fmtPrice(tr.init_sl ?? tr.sl)} / ${fmtPrice(tr.tp)}`} />
            <Item k={t("Size")} v={`${tr.qty} (${tr.notional.toLocaleString("en-US", { maximumSignificantDigits: 4 })} USDT)`} />
            <Item k={t("1R risk (real)")} v={tr.risk_amount != null ? `${money(tr.risk_amount).replace("+", "")} USDT` : "—"} />
          </div>
          <div className="space-y-1">
            <Item k={t("Normalized PnL (1R = ${risk})", { risk })} v={usd(tr.r != null ? tr.r * risk : null)} cls={tone(tr.r)} />
            <Item k={t("Real PnL")} v={`${money(tr.pnl)} USDT (${signed(tr.pnl_pct, 2, "%")})`} cls={tone(tr.pnl)} />
            {tr.fee != null && <Item k={t("Fees (entry + exit)")} v={`${money(-tr.fee)} USDT`} cls="text-down" />}
            {tr.margin != null && <Item k={t("Locked margin")} v={`${money(tr.margin).replace("+", "")} USDT`} />}
            <Item k={t("Realized R")} v={signed(tr.r, 2, "R")} cls={tone(tr.r)} />
            <Item
              k={t("MFE (max favorable excursion)")}
              v={`${signed(tr.mfe_pct, 2, "%")}${tr.mfe_r != null ? ` · ${signed(tr.mfe_r, 2, "R")} ≈ ${usd(tr.mfe_r * risk)}` : ""} @ ${fmtPrice(tr.mfe_price)}`}
              cls="text-up"
            />
            <Item
              k={t("MAE (max adverse excursion)")}
              v={`${tr.mae_pct != null ? signed(-tr.mae_pct, 2, "%") : "—"}${tr.mae_r != null ? ` · ${signed(-tr.mae_r, 2, "R")} ≈ ${usd(-tr.mae_r * risk)}` : ""} @ ${fmtPrice(tr.mae_price)}`}
              cls="text-down"
            />
            <Item k={t("MFE / MAE time")} v={`${tr.mfe_ts ? new Date(tr.mfe_ts).toLocaleTimeString() : "—"} / ${tr.mae_ts ? new Date(tr.mae_ts).toLocaleTimeString() : "—"}`} />
          </div>
          {tr.params && (
            <details className="sm:col-span-3">
              <summary className="cursor-pointer text-faint">{t("Bot params at entry")}</summary>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-muted">
                {Object.entries(tr.params).map(([k, v]) => (
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
