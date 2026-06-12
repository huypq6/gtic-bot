import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  LineSeries,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
} from "lightweight-charts";
import { loadHistory, toBar } from "../../lib/datafeed";
import { ema } from "../../lib/indicators";
import { klineKey, useWsStore } from "../../lib/ws";

interface Props {
  symbol: string;
  tf: string;
  showEma: boolean;
  reloadToken?: number; // bump để load lại lịch sử (sau khi sync xong)
}

const COLORS = {
  up: "#46a99c",
  down: "#e5544b",
  text: "#9da1b3",
  grid: "#1f2130",
  emaFast: "#8b9cba",
  emaSlow: "#5cc3b4",
};

export default function CandleChart({ symbol, tf, showEma, reloadToken }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const emaFastRef = useRef<ISeriesApi<"Line"> | null>(null);
  const emaSlowRef = useRef<ISeriesApi<"Line"> | null>(null);
  const barsRef = useRef<CandlestickData[]>([]);

  // Tạo chart 1 lần.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: COLORS.text,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: COLORS.grid },
        horzLines: { color: COLORS.grid },
      },
      rightPriceScale: { borderColor: COLORS.grid },
      timeScale: { borderColor: COLORS.grid, timeVisible: true },
      autoSize: true,
    });
    chartRef.current = chart;
    candleRef.current = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.up,
      downColor: COLORS.down,
      borderVisible: false,
      wickUpColor: COLORS.up,
      wickDownColor: COLORS.down,
    });
    return () => {
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      emaFastRef.current = null;
      emaSlowRef.current = null;
    };
  }, []);

  // Load lịch sử khi đổi symbol/tf.
  useEffect(() => {
    let cancelled = false;
    loadHistory(symbol, tf).then((bars) => {
      if (cancelled || !candleRef.current) return;
      barsRef.current = bars;
      candleRef.current.setData(bars);
      redrawEma();
      chartRef.current?.timeScale().fitContent();
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, tf, reloadToken]);

  // EMA overlays bật/tắt.
  function redrawEma() {
    const chart = chartRef.current;
    if (!chart) return;
    if (showEma) {
      if (!emaFastRef.current)
        emaFastRef.current = chart.addSeries(LineSeries, {
          color: COLORS.emaFast,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        });
      if (!emaSlowRef.current)
        emaSlowRef.current = chart.addSeries(LineSeries, {
          color: COLORS.emaSlow,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        });
      emaFastRef.current.setData(ema(barsRef.current, 9));
      emaSlowRef.current.setData(ema(barsRef.current, 21));
    } else {
      if (emaFastRef.current) {
        chart.removeSeries(emaFastRef.current);
        emaFastRef.current = null;
      }
      if (emaSlowRef.current) {
        chart.removeSeries(emaSlowRef.current);
        emaSlowRef.current = null;
      }
    }
  }
  useEffect(redrawEma, [showEma]);

  // Cập nhật realtime từ WS store (nến cuối).
  const live = useWsStore((s) => s.lastKline[klineKey(symbol, tf)]);
  useEffect(() => {
    if (!live || !candleRef.current) return;
    const bar = toBar(live);
    candleRef.current.update(bar);
    const bars = barsRef.current;
    if (bars.length && bars[bars.length - 1].time === bar.time) {
      bars[bars.length - 1] = bar;
    } else {
      bars.push(bar);
    }
    if (showEma) redrawEma();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live]);

  return <div ref={containerRef} className="h-full w-full" />;
}
