// Datafeed adapter — CÔ LẬP nguồn dữ liệu chart. Khi swap lightweight-charts →
// TradingView Charting Library, chỉ sửa file này, không đụng component chart.
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

// Lịch sử (REST). Backend trả mảng theo thời gian tăng dần.
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
