import { useEffect, useRef } from "react";
import {
  ColorType,
  LineSeries,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";

export default function EquityCurve({ data }: { data: [number, number][] }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#9da1b3",
        attributionLogo: false,
      },
      grid: { vertLines: { color: "#1f2130" }, horzLines: { color: "#1f2130" } },
      rightPriceScale: { borderColor: "#1f2130" },
      timeScale: { borderColor: "#1f2130", timeVisible: true },
      autoSize: true,
    });
    chartRef.current = chart;
    const series = chart.addSeries(LineSeries, { color: "#46a99c", lineWidth: 2 });
    series.setData(
      data.map(([ts, v]) => ({ time: (ts / 1000) as Time, value: v })),
    );
    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [data]);

  return <div ref={ref} className="h-72 w-full" />;
}
