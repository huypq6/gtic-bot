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
}

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
export const fetchBots = () => getJson<BotInfo[]>("/api/bots");
export const fetchPositions = () => getJson<PositionRow[]>("/api/positions");

export const createBot = (body: {
  strategy_id: number;
  symbol: string;
  tf: string;
  mode: string;
  params: Record<string, unknown>;
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
