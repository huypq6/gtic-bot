import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { Pause, Play, X } from "lucide-react";
import { loadRange } from "../../lib/datafeed";
import { chartColors } from "../../lib/chartTheme";
import { useTheme } from "../../lib/theme";
import type { BacktestTrade } from "../../lib/api";
import { t } from "../../lib/i18n";

const TF_MS: Record<string, number> = {
  "1m": 60_000,
  "5m": 300_000,
  "15m": 900_000,
  "1h": 3_600_000,
  "4h": 14_400_000,
  "1d": 86_400_000,
};

// Price: enough significant digits for both BTC (84559.32) and DOGE (0.09428).
export const fmtPrice = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString("en-US", { maximumSignificantDigits: 7 });

export interface ExtraLine {
  price: number;
  title: string;
  tone: "up" | "down" | "muted";
}

interface Props {
  symbol: string;
  tf: string;
  index: number;
  trade: BacktestTrade;
  onClose: () => void;
  title?: ReactNode; // replaces the default "Trade #n" title
  info?: ReactNode; // replaces the default info grid
  extraLines?: ExtraLine[]; // e.g. MFE/MAE
  tfChoices?: string[]; // allow switching timeframe during review
}

// Single-trade detail + TIME REPLAY: drag the slider / play to watch candles build up from entry → exit.
export default function TradeDetail({
  symbol,
  tf: tf0,
  index,
  trade,
  onClose,
  title,
  info,
  extraLines,
  tfChoices,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markersApiRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const markersRef = useRef<SeriesMarker<Time>[]>([]);
  const linesRef = useRef<IPriceLine[]>([]);
  const barsRef = useRef<CandlestickData[]>([]);
  const theme = useTheme((s) => s.theme);
  const [tf, setTf] = useState(tf0);
  const [n, setN] = useState(0); // number of candles loaded
  const [pos, setPos] = useState(0); // slider position (candle index)
  const [playing, setPlaying] = useState(false);
  const win = (trade.pnl_pct ?? 0) >= 0;

  // create chart + load candles around the trade.
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
      localization: { priceFormatter: (p: number) => fmtPrice(p) },
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
    linesRef.current = [];

    const ms = TF_MS[tf] ?? 60_000;
    const bar = (ts: number) => (Math.floor(ts / ms) * ms) / 1000; // ms → time of the candle containing ts
    const from = (trade.entry_ts ?? 0) - 40 * ms;
    const to = (trade.exit_ts ?? Date.now()) + 15 * ms;
    let cancelled = false;
    loadRange(symbol, tf, from, to).then((bars) => {
      if (cancelled) return;
      barsRef.current = bars;
      candle.setData(bars);
      setN(bars.length);
      setPos(bars.length - 1);
      chart.timeScale().fitContent();
      // entry/exit/SL/TP price lines (+ MFE/MAE if provided)
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
      mk(trade.entry, c.text, t("entry"));
      mk(trade.exit, win ? c.up : c.down, t("exit"), true);
      mk(trade.sl, c.down, "SL", true);
      mk(trade.tp, c.up, "TP", true);
      for (const l of extraLines ?? [])
        mk(l.price, l.tone === "up" ? c.up : l.tone === "down" ? c.down : c.text, l.title, true);

      // entry/exit markers on the corresponding candles
      const long = trade.side.toLowerCase() === "long";
      const m: SeriesMarker<Time>[] = [];
      if (trade.entry_ts)
        m.push({
          time: bar(trade.entry_ts) as Time,
          position: long ? "belowBar" : "aboveBar",
          color: long ? c.up : c.down,
          shape: long ? "arrowUp" : "arrowDown",
          text: t("entry"),
        });
      if (trade.exit_ts)
        m.push({
          time: bar(trade.exit_ts) as Time,
          position: long ? "aboveBar" : "belowBar",
          color: win ? c.up : c.down,
          shape: "circle",
          text: t("exit"),
        });
      markersRef.current = m;
      markersApiRef.current = createSeriesMarkers(candle, m);
    });

    return () => {
      cancelled = true;
      chart.remove();
      chartRef.current = null;
      markersApiRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, tf, index, theme]);

  // slider / play → show candles up to pos (time replay).
  useEffect(() => {
    if (!candleRef.current || !barsRef.current.length) return;
    const shown = barsRef.current.slice(0, pos + 1);
    candleRef.current.setData(shown);
    const last = shown[shown.length - 1]?.time as number | undefined;
    markersApiRef.current?.setMarkers(
      markersRef.current.filter((m) => last == null || (m.time as number) <= last),
    );
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
      <div className="flex max-h-full w-full max-w-4xl flex-col overflow-y-auto rounded-2xl border border-border bg-surface p-5 shadow-2xl">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">
            {title ?? (
              <>
                {t("Trade #{n}", { n: index + 1 })} · {symbol} ·{" "}
                <span className={trade.side === "Long" ? "text-up" : "text-down"}>{trade.side}</span>{" "}
                <span className={win ? "text-up" : "text-down"}>
                  {win ? "+" : ""}
                  {(trade.pnl_pct ?? 0).toFixed(2)}%
                </span>
              </>
            )}
          </h2>
          <div className="flex items-center gap-2">
            {tfChoices && (
              <div className="flex rounded-md border border-border text-xs">
                {tfChoices.map((t) => (
                  <button
                    key={t}
                    onClick={() => {
                      setPlaying(false);
                      setTf(t);
                    }}
                    className={`px-2 py-1 ${t === tf ? "bg-accent text-white" : "text-muted hover:bg-surface-2"}`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
            <button onClick={onClose} className="rounded-md p-1.5 text-muted hover:bg-surface-2">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {info ?? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted md:grid-cols-4">
            <span>{t("Opened:")} {trade.entry_ts ? new Date(trade.entry_ts).toLocaleString() : "—"}</span>
            <span>{t("Closed:")} {trade.exit_ts ? new Date(trade.exit_ts).toLocaleString() : "—"}</span>
            <span>Entry: {fmtPrice(trade.entry)}</span>
            <span>Exit: {fmtPrice(trade.exit)}</span>
            <span>SL: {fmtPrice(trade.sl)}</span>
            <span>TP: {fmtPrice(trade.tp)}</span>
          </div>
        )}

        <div ref={ref} className="mt-3 h-80 w-full shrink-0" />

        {/* time replay */}
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={() => {
              if (pos >= n - 1) setPos(0);
              setPlaying((p) => !p);
            }}
            className="rounded-md bg-accent px-2.5 py-1.5 text-white hover:bg-accent-strong"
            title={t("Play replay")}
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
          {t("Drag the slider or press ▶ to watch the chart evolve over time, from before entry → until exit.")}
        </p>
      </div>
    </div>
  );
}
