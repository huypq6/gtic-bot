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
import type { BacktestTrade } from "../../lib/api";

const LINE_COLORS = ["#8b9cba", "#5cc3b4", "#e0a458", "#c98bdb", "#6fb1e0", "#d98b8b"];

interface Props {
  symbol: string;
  tf: string;
  from: number;
  to: number;
  indicators: Record<string, [number, number][]>;
  trades: BacktestTrade[];
  onSelect?: (i: number) => void; // click marker/trade
}

// Chart backtest: nến + đường indicator theo chiến lược + marker vào/ra mỗi lệnh (US-11).
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

      // đường indicator
      Object.entries(indicators).forEach(([name, pts], idx) => {
        const ls = chart.addSeries(LineSeries, {
          color: LINE_COLORS[idx % LINE_COLORS.length],
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          title: name,
        });
        ls.setData(pts.map(([ts, v]) => ({ time: (ts / 1000) as Time, value: v })));
      });

      // marker vào/ra mỗi lệnh
      const markers: SeriesMarker<Time>[] = [];
      for (const t of trades) {
        const long = t.side === "Long";
        if (t.entry_ts)
          markers.push({
            time: (t.entry_ts / 1000) as Time,
            position: long ? "belowBar" : "aboveBar",
            color: c.up,
            shape: long ? "arrowUp" : "arrowDown",
            text: "vào",
          });
        if (t.exit_ts)
          markers.push({
            time: (t.exit_ts / 1000) as Time,
            position: long ? "aboveBar" : "belowBar",
            color: (t.pnl_pct ?? 0) >= 0 ? c.up : c.down,
            shape: long ? "arrowDown" : "arrowUp",
            text: `ra ${(t.pnl_pct ?? 0) >= 0 ? "+" : ""}${(t.pnl_pct ?? 0).toFixed(1)}%`,
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, tf, from, to, theme]);

  return <div ref={ref} className="h-96 w-full" />;
}
