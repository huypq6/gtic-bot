import { useEffect, useRef } from "react";
import {
  ColorType,
  LineSeries,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import { chartColors } from "../../lib/chartTheme";
import { useTheme } from "../../lib/theme";

export default function EquityCurve({ data }: { data: [number, number][] }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
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
    const series = chart.addSeries(LineSeries, { color: c.line, lineWidth: 2 });
    series.setData(data.map(([ts, value]) => ({ time: (ts / 1000) as Time, value })));
    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
    };
    // theme: rebuild để áp màu mới
  }, [data, theme]);

  return <div ref={ref} className="h-72 w-full" />;
}
