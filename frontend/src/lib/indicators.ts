// Indicator tính client-side (US-02). P1: EMA overlay. RSI/MACD subpane sau.
import type { CandlestickData, LineData, UTCTimestamp } from "lightweight-charts";

export function ema(bars: CandlestickData[], period: number): LineData[] {
  if (bars.length < period) return [];
  const k = 2 / (period + 1);
  const out: LineData[] = [];
  let prev = bars.slice(0, period).reduce((s, b) => s + b.close, 0) / period;
  out.push({ time: bars[period - 1].time as UTCTimestamp, value: prev });
  for (let i = period; i < bars.length; i++) {
    prev = bars[i].close * k + prev * (1 - k);
    out.push({ time: bars[i].time as UTCTimestamp, value: prev });
  }
  return out;
}
