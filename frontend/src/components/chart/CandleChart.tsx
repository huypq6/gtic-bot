import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { loadHistory, toBar } from "../../lib/datafeed";
import { ema } from "../../lib/indicators";
import { klineKey, useWsStore } from "../../lib/ws";
import { chartColors } from "../../lib/chartTheme";
import { useTheme } from "../../lib/theme";

interface Props {
  symbol: string;
  tf: string;
  showEma: boolean;
  reloadToken?: number; // bump để load lại lịch sử (sau khi sync xong)
}

export default function CandleChart({ symbol, tf, showEma, reloadToken }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const emaFastRef = useRef<ISeriesApi<"Line"> | null>(null);
  const emaSlowRef = useRef<ISeriesApi<"Line"> | null>(null);
  const barsRef = useRef<CandlestickData[]>([]);
  const markersApiRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const markersRef = useRef<SeriesMarker<Time>[]>([]);
  const processedOrdersRef = useRef(0);
  const theme = useTheme((s) => s.theme);

  // Tạo chart 1 lần.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const c = chartColors();
    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: c.text,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: c.grid },
        horzLines: { color: c.grid },
      },
      rightPriceScale: { borderColor: c.grid },
      timeScale: { borderColor: c.grid, timeVisible: true },
      autoSize: true,
    });
    chartRef.current = chart;
    candleRef.current = chart.addSeries(CandlestickSeries, {
      upColor: c.up,
      downColor: c.down,
      borderVisible: false,
      wickUpColor: c.up,
      wickDownColor: c.down,
    });
    markersApiRef.current = createSeriesMarkers(candleRef.current, []);
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
    const c = chartColors();
    if (showEma) {
      if (!emaFastRef.current)
        emaFastRef.current = chart.addSeries(LineSeries, {
          color: c.emaFast,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        });
      if (!emaSlowRef.current)
        emaSlowRef.current = chart.addSeries(LineSeries, {
          color: c.emaSlow,
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

  // Áp lại màu khi đổi theme sáng/tối (không phá data/series).
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const c = chartColors();
    chart.applyOptions({
      layout: { textColor: c.text },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.grid },
      timeScale: { borderColor: c.grid },
    });
    candleRef.current?.applyOptions({
      upColor: c.up,
      downColor: c.down,
      wickUpColor: c.up,
      wickDownColor: c.down,
    });
    emaFastRef.current?.applyOptions({ color: c.emaFast });
    emaSlowRef.current?.applyOptions({ color: c.emaSlow });
  }, [theme]);

  // Marker vào/ra lệnh (US-04) — từ order WS, đặt tại nến cuối khi khớp.
  const orders = useWsStore((s) => s.orders);
  useEffect(() => {
    const last = barsRef.current[barsRef.current.length - 1];
    if (!last) return;
    const delta = orders.length - processedOrdersRef.current;
    if (delta <= 0) return;
    const c = chartColors();
    const fresh = orders.slice(0, delta).reverse(); // cũ → mới
    for (const o of fresh) {
      if (o.symbol !== symbol || o.status !== "FILLED") continue;
      const buy = o.side === "BUY";
      markersRef.current.push({
        time: last.time as Time,
        position: buy ? "belowBar" : "aboveBar",
        color: buy ? c.up : c.down,
        shape: buy ? "arrowUp" : "arrowDown",
        text: o.side,
      });
    }
    processedOrdersRef.current = orders.length;
    markersApiRef.current?.setMarkers(markersRef.current.slice(-50));
  }, [orders, symbol]);

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
