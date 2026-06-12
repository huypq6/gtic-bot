// Zustand store cho realtime state (WebSocket). REST → React Query; WS → đây.
// Một kết nối /ws nhận firehose; store phân loại theo type và key symbol/tf.
import { create } from "zustand";

export type FeedStatus = "OK" | "RECONNECTING" | "DOWN" | "CONNECTING";

export interface Ticker {
  price: number;
  pct: number;
}

export interface KlineMsg {
  type: "kline";
  symbol: string;
  tf: string;
  ts: number; // open time ms
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  closed: boolean;
}

export const klineKey = (symbol: string, tf: string) => `${symbol}.${tf}`;

interface WsState {
  feed: FeedStatus;
  tickers: Record<string, Ticker>;
  lastKline: Record<string, KlineMsg>; // key = symbol.tf
  connected: boolean;
  connect: () => void;
}

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export const useWsStore = create<WsState>((set) => ({
  feed: "CONNECTING",
  tickers: {},
  lastKline: {},
  connected: false,

  connect: () => {
    if (socket && socket.readyState <= WebSocket.OPEN) return;

    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${location.host}/ws`;
    socket = new WebSocket(url);

    socket.onopen = () => set({ connected: true, feed: "OK" });

    socket.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === "ticker") {
        set((s) => ({
          tickers: { ...s.tickers, [m.symbol]: { price: m.price, pct: m.pct } },
        }));
      } else if (m.type === "kline") {
        set((s) => ({
          lastKline: { ...s.lastKline, [klineKey(m.symbol, m.tf)]: m as KlineMsg },
        }));
      } else if (m.type === "feed") {
        set({ feed: m.status as FeedStatus });
      }
    };

    const scheduleReconnect = () => {
      set({ connected: false, feed: "RECONNECTING" });
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(() => useWsStore.getState().connect(), 2000);
    };

    socket.onclose = scheduleReconnect;
    socket.onerror = () => socket?.close();
  },
}));
