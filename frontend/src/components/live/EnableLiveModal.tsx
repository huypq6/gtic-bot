import { useState } from "react";
import { AlertTriangle } from "lucide-react";

// US-14: rào chắn LIVE — gõ đúng "LIVE" mới cho phép. Cảnh báo đỏ.
export default function EnableLiveModal({
  symbol,
  onConfirm,
  onCancel,
}: {
  symbol: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState("");
  const ok = text === "LIVE";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-2xl border border-down/40 bg-ink-900 p-6 shadow-2xl">
        <div className="flex items-center gap-2 text-down">
          <AlertTriangle className="h-6 w-6" />
          <h2 className="text-lg font-bold">CHẾ ĐỘ LIVE — TIỀN THẬT</h2>
        </div>
        <p className="mt-3 text-sm text-ink-300">
          Bot <span className="font-semibold">{symbol}</span> sẽ đặt lệnh bằng{" "}
          <span className="font-semibold text-down">tiền thật</span> trên Binance. Đảm bảo key đã
          tắt quyền rút tiền + whitelist IP.
        </p>
        <p className="mt-3 text-sm text-ink-400">
          Gõ <span className="font-mono font-semibold text-down">LIVE</span> để xác nhận:
        </p>
        <input
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="LIVE"
          className="mt-2 w-full rounded-md border border-down/40 bg-ink-950 px-3 py-2 font-mono text-ink-100"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-md px-3 py-1.5 text-sm text-ink-400 hover:bg-ink-800"
          >
            Hủy
          </button>
          <button
            onClick={onConfirm}
            disabled={!ok}
            className="rounded-md bg-down px-3 py-1.5 text-sm font-semibold text-ink-950 hover:bg-down/90 disabled:opacity-40"
          >
            Chạy LIVE
          </button>
        </div>
      </div>
    </div>
  );
}
