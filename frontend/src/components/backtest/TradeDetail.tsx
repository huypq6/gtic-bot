import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  type CandlestickData,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
} from "lightweight-charts";
import { Pause, Play, X } from "lucide-react";
import { loadRange } from "../../lib/datafeed";
import { chartColors } from "../../lib/chartTheme";
import { useTheme } from "../../lib/theme";
import type { BacktestTrade } from "../../lib/api";

const TF_MS: Record<string, number> = {
  "1m": 60_000,
  "5m": 300_000,
  "15m": 900_000,
  "1h": 3_600_000,
  "4h": 14_400_000,
  "1d": 86_400_000,
};

interface Props {
  symbol: string;
  tf: string;
  index: number;
  trade: BacktestTrade;
  onClose: () => void;
}

// Chi tiết 1 lệnh + MÔ PHỎNG THỜI GIAN: kéo thanh / play để xem nến lớn dần từ vào → ra.
export default function TradeDetail({ symbol, tf, index, trade, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const linesRef = useRef<IPriceLine[]>([]);
  const barsRef = useRef<CandlestickData[]>([]);
  const theme = useTheme((s) => s.theme);
  const [n, setN] = useState(0); // số nến đang hiển thị
  const [pos, setPos] = useState(0); // vị trí thanh (index nến)
  const [playing, setPlaying] = useState(false);

  // tạo chart + nạp nến quanh lệnh.
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

    const ms = TF_MS[tf] ?? 60_000;
    const from = (trade.entry_ts ?? 0) - 40 * ms;
    const to = (trade.exit_ts ?? trade.entry_ts ?? 0) + 15 * ms;
    let cancelled = false;
    loadRange(symbol, tf, from, to).then((bars) => {
      if (cancelled) return;
      barsRef.current = bars;
      candle.setData(bars);
      setN(bars.length);
      setPos(bars.length - 1);
      chart.timeScale().fitContent();
      // đường giá vào/ra/SL/TP
      const mk = (price: number | null, color: string, title: string, dashed = false) =>
        price != null &&
        linesRef.current.push(
          candle.createPriceLine({
            price,
            color,
            lineWidth: 1,
            lineStyle: dashed ? 2 : 0,
            axisLabelVisible: true,
            title,
          }),
        );
      mk(trade.entry, c.text, "vào");
      mk(trade.exit, (trade.pnl_pct ?? 0) >= 0 ? c.up : c.down, "ra", true);
      mk(trade.sl, c.down, "SL", true);
      mk(trade.tp, c.up, "TP", true);
    });

    return () => {
      cancelled = true;
      chart.remove();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, tf, index, theme]);

  // kéo thanh / play → hiển thị nến tới vị trí pos (mô phỏng thời gian).
  useEffect(() => {
    if (candleRef.current && barsRef.current.length)
      candleRef.current.setData(barsRef.current.slice(0, pos + 1));
  }, [pos]);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setPos((p) => {
        if (p >= n - 1) {
          setPlaying(false);
          return p;
        }
        return p + 1;
      });
    }, 180);
    return () => clearInterval(id);
  }, [playing, n]);

  const curTime = barsRef.current[pos]?.time as number | undefined;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex w-full max-w-3xl flex-col rounded-2xl border border-border bg-surface p-5 shadow-2xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">
            Lệnh #{index + 1} · {symbol} ·{" "}
            <span className={trade.side === "Long" ? "text-up" : "text-down"}>{trade.side}</span>{" "}
            <span className={`${(trade.pnl_pct ?? 0) >= 0 ? "text-up" : "text-down"}`}>
              {(trade.pnl_pct ?? 0) >= 0 ? "+" : ""}
              {(trade.pnl_pct ?? 0).toFixed(2)}%
            </span>
          </h2>
          <button onClick={onClose} className="rounded-md p-1.5 text-muted hover:bg-surface-2">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted md:grid-cols-4">
          <span>Vào: {trade.entry_ts ? new Date(trade.entry_ts).toLocaleString() : "—"}</span>
          <span>Ra: {trade.exit_ts ? new Date(trade.exit_ts).toLocaleString() : "—"}</span>
          <span>Entry: {trade.entry?.toFixed(2) ?? "—"}</span>
          <span>Exit: {trade.exit?.toFixed(2) ?? "—"}</span>
          <span>SL: {trade.sl?.toFixed(2) ?? "—"}</span>
          <span>TP: {trade.tp?.toFixed(2) ?? "—"}</span>
        </div>

        <div ref={ref} className="mt-3 h-80 w-full" />

        {/* mô phỏng thời gian */}
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={() => {
              if (pos >= n - 1) setPos(0);
              setPlaying((p) => !p);
            }}
            className="rounded-md bg-accent px-2.5 py-1.5 text-white hover:bg-accent-strong"
            title="Phát mô phỏng"
          >
            {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </button>
          <input
            type="range"
            min={0}
            max={Math.max(0, n - 1)}
            value={pos}
            onChange={(e) => {
              setPlaying(false);
              setPos(Number(e.target.value));
            }}
            className="flex-1 accent-[var(--accent)]"
          />
          <span className="w-40 shrink-0 text-right text-xs tabular-nums text-faint">
            {curTime ? new Date(curTime * 1000).toLocaleString() : "—"}
          </span>
        </div>
        <p className="mt-1 text-xs text-faint">
          Kéo thanh hoặc bấm ▶ để xem biểu đồ biến đổi theo thời gian từ trước khi vào → đến khi ra
          lệnh.
        </p>
      </div>
    </div>
  );
}
