// REST client. Dùng đường dẫn tương đối /api → Vite proxy (dev) / cùng origin (prod).

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface Health {
  status: string;
}

export const fetchHealth = () => getJson<Health>("/api/health");

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
  getJson<{ name: string; markdown: string }>(`/api/strategies/${name}/doc`);

export interface BotInfo {
  id: number;
  strategy_id: number;
  strategy: string | null;
  symbol: string;
  tf: string;
  mode: string;
  params: Record<string, unknown>;
  status: string;
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
export const fetchBots = () => getJson<BotInfo[]>("/api/bots");
export const fetchPositions = () => getJson<PositionRow[]>("/api/positions");

export const createBot = (body: {
  strategy_id: number;
  symbol: string;
  tf: string;
  mode: string;
  params: Record<string, unknown>;
  confirm?: string;
}) => postJson<BotInfo>("/api/bots", body);

export async function patchBot(id: number, body: { status?: string; params?: object }) {
  const res = await fetch(`/api/bots/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<BotInfo>;
}

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
}) => postJson("/api/orders", body);

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

export const fetchAudit = () => getJson<AuditRow[]>("/api/audit");

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
}

export function fetchOrders(filters: Record<string, string> = {}) {
  const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
  const q = qs.toString();
  return getJson<OrderRow[]>(`/api/orders${q ? `?${q}` : ""}`);
}

// ---- backtest (P4) ----
export interface BacktestTrade {
  side: string;
  entry_ts: number | null;
  entry: number | null;
  exit_ts: number | null;
  exit: number | null;
  pnl_pct: number | null;
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
  equity_curve: [number, number][];
  trades: BacktestTrade[];
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
}) => postJson<BacktestResult>("/api/backtest", body);
