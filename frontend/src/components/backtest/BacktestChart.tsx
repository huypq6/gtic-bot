import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { loadRange } from "../../lib/datafeed";
import { chartColors } from "../../lib/chartTheme";
import { useTheme } from "../../lib/theme";
import type { BacktestTrade, IndicatorSeries } from "../../lib/api";
import { t } from "../../lib/i18n";

const LINE_COLORS = ["#8b9cba", "#5cc3b4", "#e0a458", "#c98bdb", "#6fb1e0", "#d98b8b"];
const OSC_PANE = 1; // secondary pane for oscillators (RSI/ADX/Stoch/MACD)
const OSC_PANE_HEIGHT = 130;

// Normalize series to {pane, data} — older runs stored a [[ts,v]] array (pane 0).
function normSeries(raw: IndicatorSeries): { pane: number; data: [number, number][] } {
  if (Array.isArray(raw)) return { pane: 0, data: raw };
  return { pane: raw.pane ?? 0, data: raw.data };
}

interface Props {
  symbol: string;
  tf: string;
  from: number;
  to: number;
  indicators: Record<string, IndicatorSeries>;
  trades: BacktestTrade[];
  onSelect?: (i: number) => void; // click marker/trade
}

// Backtest chart: candles + the strategy's indicator lines + entry/exit markers for each trade (US-11).
export default function BacktestChart({ symbol, tf, from, to, indicators, trades }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const theme = useTheme((s) => s.theme);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const c = chartColors();
    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: c.text,
        attributionLogo: false,
      },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.grid },
      timeScale: { borderColor: c.grid, timeVisible: true },
      autoSize: true,
    });
    chartRef.current = chart;
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: c.up,
      downColor: c.down,
      borderVisible: false,
      wickUpColor: c.up,
      wickDownColor: c.down,
    });
    candleRef.current = candle;

    let cancelled = false;
    loadRange(symbol, tf, from, to).then((bars) => {
      if (cancelled) return;
      candle.setData(bars);

      // indicator lines — pane 0 overlays price, pane 1 for oscillators (own scale).
      let hasOscPane = false;
      Object.entries(indicators).forEach(([name, raw], idx) => {
        const { pane, data } = normSeries(raw);
        if (pane === OSC_PANE) hasOscPane = true;
        const ls = chart.addSeries(
          LineSeries,
          {
            color: LINE_COLORS[idx % LINE_COLORS.length],
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: pane === OSC_PANE, // oscillator: show last value for readability
            title: name,
          },
          pane,
        );
        ls.setData(data.map(([ts, v]) => ({ time: (ts / 1000) as Time, value: v })));
      });
      if (hasOscPane) chart.panes()[OSC_PANE]?.setHeight(OSC_PANE_HEIGHT);

      // entry/exit marker for each trade
      const markers: SeriesMarker<Time>[] = [];
      for (const tr of trades) {
        const long = tr.side === "Long";
        if (tr.entry_ts)
          markers.push({
            time: (tr.entry_ts / 1000) as Time,
            position: long ? "belowBar" : "aboveBar",
            color: c.up,
            shape: long ? "arrowUp" : "arrowDown",
            text: t("entry"),
          });
        if (tr.exit_ts)
          markers.push({
            time: (tr.exit_ts / 1000) as Time,
            position: long ? "aboveBar" : "belowBar",
            color: (tr.pnl_pct ?? 0) >= 0 ? c.up : c.down,
            shape: long ? "arrowDown" : "arrowUp",
            text: `${t("exit")} ${(tr.pnl_pct ?? 0) >= 0 ? "+" : ""}${(tr.pnl_pct ?? 0).toFixed(1)}%`,
          });
      }
      markers.sort((a, b) => (a.time as number) - (b.time as number));
      createSeriesMarkers(candle, markers);
      chart.timeScale().fitContent();
    });

    return () => {
      cancelled = true;
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
    };
    // indicators/trades change when a new backtest runs on the same symbol+tf+range → must redraw.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, tf, from, to, theme, indicators, trades]);

  return <div ref={ref} className="h-96 w-full" />;
}
