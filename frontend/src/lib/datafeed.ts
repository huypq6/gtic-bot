// Datafeed adapter — ISOLATES the chart data source. When swapping lightweight-charts →
// TradingView Charting Library, only edit this file, not the chart components.
import type { CandlestickData, UTCTimestamp } from "lightweight-charts";
import { getJson } from "./api";
import type { KlineMsg } from "./ws";

interface RawKline {
  ts: number; // ms
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export const toBar = (k: RawKline | KlineMsg): CandlestickData => ({
  time: (k.ts / 1000) as UTCTimestamp,
  open: k.open,
  high: k.high,
  low: k.low,
  close: k.close,
});

// History (REST). Backend returns an array in ascending time order.
export async function loadHistory(
  symbol: string,
  tf: string,
  limit = 500,
): Promise<CandlestickData[]> {
  const raw = await getJson<RawKline[]>(
    `/api/klines?symbol=${symbol}&tf=${tf}&limit=${limit}`,
  );
  return raw.map(toBar);
}

// Candles in the range [from, to] (ms) — for the backtest chart.
export async function loadRange(
  symbol: string,
  tf: string,
  from: number,
  to: number,
): Promise<CandlestickData[]> {
  const raw = await getJson<RawKline[]>(
    `/api/klines?symbol=${symbol}&tf=${tf}&start=${from}&end=${to}&limit=5000`,
  );
  return raw.map(toBar);
}
