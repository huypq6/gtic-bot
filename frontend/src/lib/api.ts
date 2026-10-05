// REST client. Uses relative /api paths → Vite proxy (dev) / same origin (prod).
import { lang } from "./i18n";

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface Health {
  status: string;
}

export const fetchHealth = () => getJson<Health>("/api/health");

export interface VersionInfo {
  version: string;
  commit: string | null;
  build: string | null;
  commit_date: string | null;
  subject: string | null;
  built_at?: string | null;
  dirty?: boolean;
  started_at: string;
}

export const fetchVersion = () => getJson<VersionInfo>("/api/version");

export interface AppConfig {
  symbols: string[];
  timeframes: string[];
  default_tf: string;
}

export const fetchConfig = () => getJson<AppConfig>("/api/config");

export const addWatch = (symbol: string) =>
  postJson<{ added: string; symbols: string[] }>("/api/watchlist", { symbol });

export async function removeWatch(symbol: string) {
  const res = await fetch(`/api/watchlist/${symbol}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// Send JSON; on error → Error carrying FastAPI's `detail` (e.g. "insufficient balance") to show the user.
export async function sendJson<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* body is not JSON */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const syncKlines = (symbol: string, tf: string, start = "3 days ago UTC") =>
  postJson<{ synced: number }>("/api/klines/sync", { symbol, tf, start });

// ---- strategies / bots / positions ----
export interface StrategyInfo {
  id: number;
  name: string;
  version: string;
  default_params: Record<string, unknown>;
  param_schema: Record<string, unknown>;
  description?: string;
  source_file?: string | null;
}

export const fetchStrategyDoc = (name: string) =>
  getJson<{ name: string; markdown: string }>(`/api/strategies/${name}/doc?lang=${lang}`);

export interface BotInfo {
  id: number;
  strategy_id: number;
  strategy: string | null;
  symbol: string;
  tf: string;
  mode: string;
  params: Record<string, unknown>;
  status: string;
  /** open-time (ms) of the last closed candle the bot received live; null = none received yet. */
  last_candle?: number | null;
  account_id: number | null;
  sizing: Sizing | null;
}

export interface Sizing {
  method: string; // risk_pct | risk_usdt | notional_pct | notional_usdt | fixed_qty
  value: number;
}

export interface PositionRow {
  id: number;
  bot_id: number | null;
  mode: string;
  symbol: string;
  side: string;
  qty: number;
  entry_price: number;
  sl: number | null;
  tp: number | null;
}

export const fetchStrategies = () => getJson<StrategyInfo[]>("/api/strategies");

export interface VersionCompareRow {
  version: string;
  runs: number;
  best_pnl_pct: number | null;
  last_pnl_pct: number | null;
  last_winrate: number | null;
  last_max_dd: number | null;
  last_n_trades: number | null;
}

export const fetchCompare = (name: string) =>
  getJson<VersionCompareRow[]>(`/api/strategies/${name}/compare`);
export const fetchBots = (mode = "") => getJson<BotInfo[]>(`/api/bots${mode ? `?mode=${mode}` : ""}`);
export const fetchPositions = (mode = "") =>
  getJson<PositionRow[]>(`/api/positions${mode ? `?mode=${mode}` : ""}`);

export const createBot = (body: {
  strategy_id: number;
  symbol: string;
  tf: string;
  mode: string;
  params: Record<string, unknown>;
  confirm?: string;
  account_id?: number | null;
  sizing?: Sizing | null;
}) => sendJson<BotInfo>("POST", "/api/bots", body);

export const patchBot = (
  id: number,
  body: { status?: string; params?: object; sizing?: Sizing; account_id?: number },
) => sendJson<BotInfo>("PATCH", `/api/bots/${id}`, body);

export async function deleteBot(id: number) {
  const res = await fetch(`/api/bots/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

// ---- manual intervention (P3) ----
export const closePosition = (id: number, ref_price?: number) =>
  postJson(`/api/positions/${id}/close`, { ref_price });

export async function editSltp(id: number, sl: number | null, tp: number | null) {
  const res = await fetch(`/api/positions/${id}/sltp`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sl, tp }),
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export const manualOrder = (body: {
  symbol: string;
  side: string;
  type: string;
  qty: number;
  price?: number | null;
  sl?: number | null;
  tp?: number | null;
  ref_price?: number | null;
}) => sendJson("POST", "/api/orders", body);

export interface AuditRow {
  id: number;
  ts: string | null;
  source: string;
  mode: string | null;
  bot_id: number | null;
  symbol: string | null;
  action: string;
  detail: Record<string, unknown> | null;
}

export const fetchAudit = (mode = "") =>
  getJson<AuditRow[]>(`/api/audit${mode ? `?mode=${mode}` : ""}`);

// ---- mode workspaces (docs/08) ----
export interface ModeSummary {
  mode: "PAPER" | "TESTNET" | "LIVE";
  bots: Partial<Record<"RUNNING" | "PAUSED" | "STOPPED", number>>;
  open_positions: number;
  open_risk: number;
  today: { trades: number; pnl: number };
  week: { trades: number; wins: number; pnl: number; sum_r: number | null };
}
export const fetchModesSummary = () => getJson<ModeSummary[]>("/api/modes/summary");

export interface ModeCompareRow {
  mode: string;
  version: string;
  trades: number;
  wins: number;
  win_rate: number | null;
  sum_r: number | null;
  avg_r: number | null;
  pnl: number;
  fees: number;
  bots: number[];
}
export interface ModeDivergence {
  a: string;
  b: string;
  version: string;
  paired: number;
  only_a: number;
  only_b: number;
  entry_slip_bps: number | null;
  exit_slip_bps: number | null;
  r_diff: number | null;
}
export interface ModeCompareGroup {
  strategy: string;
  symbol: string;
  tf: string;
  trades: number;
  rows: ModeCompareRow[];
  divergence: ModeDivergence[];
}
export const fetchModeCompare = (days: number, symbol = "") =>
  getJson<{ days: number; groups: ModeCompareGroup[] }>(
    `/api/compare?days=${days}${symbol ? `&symbol=${symbol}` : ""}`,
  );

export interface OrderRow {
  id: number;
  bot_id: number | null;
  ext_id: string | null;
  source: string;
  mode: string;
  symbol: string;
  side: string;
  type: string;
  qty: number | null;
  price: number | null;
  sl: number | null;
  tp: number | null;
  filled_qty: number | null;
  avg_price: number | null;
  fee: number | null;
  status: string;
  created_at: string | null;
  // trade link: OPEN = entry fill, CLOSE = exit fill (null = not linked, e.g. pending/legacy)
  position_id: number | null;
  intent: "OPEN" | "CLOSE" | null;
  pos_side: "LONG" | "SHORT" | null;
  exit_reason: string | null;
}

export function fetchOrders(filters: Record<string, string> = {}) {
  const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
  const q = qs.toString();
  return getJson<OrderRow[]>(`/api/orders${q ? `?${q}` : ""}`);
}

// ---- trade review: 1 position = 1 trade (result, R, MFE/MAE) ----
export interface TradeRow {
  id: number;
  bot_id: number | null;
  mode: string;
  symbol: string;
  side: "LONG" | "SHORT";
  qty: number;
  entry_price: number;
  exit_price: number | null;
  sl: number | null;
  tp: number | null;
  init_sl: number | null;
  status: "OPEN" | "CLOSED";
  exit_reason: string | null; // SL | TP | SIGNAL | MANUAL | LIQUIDATION
  account_id: number | null;
  fee: number | null; // total entry + exit fees (USDT)
  margin: number | null;
  strategy: string | null;
  tf: string | null;
  params: Record<string, unknown> | null; // snapshot at entry
  source: string;
  bot_ref: number | null; // original bot id (kept even after the bot is deleted)
  bot_deleted: boolean;
  opened_at: number; // ms
  closed_at: number | null;
  result: "WIN" | "LOSS" | "BE" | "OPEN";
  notional: number;
  pnl: number | null;
  pnl_pct: number | null;
  risk_amount: number | null;
  r: number | null;
  mfe_pct: number | null;
  mae_pct: number | null;
  mfe_r: number | null;
  mae_r: number | null;
  mfe_pnl: number | null;
  mae_pnl: number | null;
  mfe_price: number | null;
  mae_price: number | null;
  mfe_ts: number | null;
  mae_ts: number | null;
}

export function fetchTrades(filters: Record<string, string> = {}) {
  const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
  const q = qs.toString();
  return getJson<TradeRow[]>(`/api/trades${q ? `?${q}` : ""}`);
}

// ---- backtest (P4) ----
// Indicator series: new form {pane, data} (pane 0 = price overlay, 1 = oscillator),
// or the legacy form (previously saved runs) as an array [[ts, value]] — treated as pane 0.
export type IndicatorSeries = [number, number][] | { pane?: number; data: [number, number][] };

export interface BacktestTrade {
  side: string;
  entry_ts: number | null;
  entry: number | null;
  exit_ts: number | null;
  exit: number | null;
  pnl_pct: number | null; // ACCOUNT engine: % of equity at entry
  sl: number | null;
  tp: number | null;
  // engine ACCOUNT
  qty?: number | null;
  pnl?: number | null;
  fee?: number | null;
  r?: number | null;
  reason?: string | null;
  mfe_r?: number | null;
  mae_r?: number | null;
}

export interface SimCompareRow {
  sizing: Sizing;
  leverage: number;
  final_equity: number;
  pnl_pct: number;
  cagr_pct: number | null;
  max_dd: number;
  calmar: number | null;
  sharpe: number | null;
  winrate: number;
  n_trades: number;
  profit_factor: number | null;
  avg_r: number | null;
  total_fees: number;
  day_halts: number;
  dd_halt_ts: number | null;
  liquidated: boolean;
  avg_notional_pct: number | null;
  capped: Record<string, number>;
  rejects: Record<string, number>;
  positive_months: number;
  n_months: number;
  equity_curve: [number, number][];
}

export interface SimStats {
  cagr_pct: number | null;
  longest_dd_days: number;
  calmar: number | null;
  profit_factor: number | null;
  avg_r: number | null;
  best_r: number | null;
  worst_r: number | null;
  max_loss_streak: number;
  total_fees: number;
  fees_pct_of_capital: number;
  day_halts: number;
  dd_halt_ts: number | null;
  liquidated: boolean;
  rejects: Record<string, number>;
  capped: Record<string, number>;
  avg_notional_pct: number | null;
  monthly: [string, number][];
  positive_months: number;
  compare: SimCompareRow[];
}

export interface BacktestResult {
  id: number;
  strategy_id: number;
  symbol: string;
  tf: string;
  capital: number | null;
  fee_rate: number | null;
  market: string | null;
  leverage: number | null;
  pnl_pct: number | null;
  winrate: number | null;
  max_dd: number | null;
  sharpe: number | null;
  n_trades: number | null;
  liquidated?: boolean;
  from_ts: number | null;
  to_ts: number | null;
  indicators: Record<string, IndicatorSeries>;
  equity_curve: [number, number][];
  trades: BacktestTrade[];
  engine?: "VBT" | "ACCOUNT";
  sizing?: Sizing | null;
  final_equity?: number | null;
  settings?: Record<string, number | null> | null;
  stats?: SimStats | null;
}

// ---- scanner (P7) ----
export interface ScanResultRow {
  symbol: string;
  score: number | null;
  signal: string;
  reason: string;
  entry: number | null;
  atr: number | null;
  sl: number | null;
  tp: number | null;
  ts: string | null;
}

export const fetchScan = () => getJson<ScanResultRow[]>("/api/scan");

export const runBacktest = (body: {
  strategy_id: number;
  symbol: string;
  tf: string;
  start: string;
  capital: number;
  market: string;
  leverage: number;
  fee_rate?: number | null;
  params?: Record<string, unknown> | null;
  engine?: "VBT" | "ACCOUNT";
  sizing?: Sizing & { leverage?: number | null };
  slippage_bps?: number;
  max_risk_pct?: number | null;
  daily_loss_pct?: number | null;
  max_dd_pct?: number | null;
  compare?: (Sizing & { leverage?: number | null })[];
}) => sendJson<BacktestResult>("POST", "/api/backtest", body);

// ---- account & money management (P9) ----
export interface AccountSettings {
  leverage: number;
  taker_fee: number;
  maker_fee: number;
  slippage_bps: number;
  max_risk_pct: number | null;
  max_open_risk_pct: number | null;
  max_positions: number | null;
  daily_loss_pct: number | null;
  max_dd_pct: number | null;
}

export interface AccountInfo {
  id: number;
  name: string;
  mode: string;
  currency: string;
  status: "ACTIVE" | "HALTED";
  halted_reason: string | null;
  halted_until: string | null;
  paused_today: boolean;
  settings: AccountSettings;
  balance: number;
  equity: number;
  used_margin: number;
  available: number;
  open_risk: number;
  n_open: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  day_start_balance: number;
  peak_equity: number;
  dd_pct: number;
  net_deposit: number;
  total_pnl: number;
  total_pnl_pct: number | null;
  total_fees: number;
  n_bots: number;
  market: string;
  is_exchange: boolean; // TESTNET/LIVE: figures synced from Binance Futures
  last_sync_at: string | null;
  sync_error: string | null;
}

export interface LedgerRow {
  id: number;
  ts: number;
  type: "DEPOSIT" | "WITHDRAW" | "REALIZED_PNL" | "FEE" | "ADJUST";
  amount: number;
  balance_after: number;
  position_id: number | null;
  bot_id: number | null;
  symbol: string | null;
  note: string | null;
}

export const fetchAccounts = () => getJson<AccountInfo[]>("/api/accounts");
export const fetchSizingMethods = () =>
  getJson<Record<string, string>>("/api/accounts/sizing-methods");
export const createAccount = (
  body: Partial<AccountSettings> & {
    name: string;
    mode?: string;
    initial_balance?: number | null;
    confirm?: string;
  },
) => sendJson<AccountInfo>("POST", "/api/accounts", body);
export const syncAccount = (id: number) => sendJson<AccountInfo>("POST", `/api/accounts/${id}/sync`);
export const patchAccount = (id: number, body: Partial<AccountSettings> & { name?: string }) =>
  sendJson<AccountInfo>("PATCH", `/api/accounts/${id}`, body);
export const depositAccount = (id: number, amount: number, note?: string) =>
  sendJson<{ balance: number }>("POST", `/api/accounts/${id}/deposit`, { amount, note });
export const withdrawAccount = (id: number, amount: number, note?: string) =>
  sendJson<{ balance: number }>("POST", `/api/accounts/${id}/withdraw`, { amount, note });
export const resumeAccount = (id: number) =>
  sendJson<{ resumed: number }>("POST", `/api/accounts/${id}/resume`);
export const fetchLedger = (id: number) => getJson<LedgerRow[]>(`/api/accounts/${id}/ledger`);
export const fetchEquity = (id: number) =>
  getJson<{ balance: [number, number][]; pnl: [number, number][] }>(`/api/accounts/${id}/equity`);
