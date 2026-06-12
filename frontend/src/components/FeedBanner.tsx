import { AlertTriangle, Wifi } from "lucide-react";
import { useWsStore } from "../lib/ws";

// US-27: cảnh báo khi mất kết nối feed. OK → ẩn.
export default function FeedBanner() {
  const feed = useWsStore((s) => s.feed);
  if (feed === "OK") return null;

  const down = feed === "DOWN";
  return (
    <div
      className={`flex items-center gap-2 px-4 py-1.5 text-sm ${
        down ? "bg-down/20 text-down" : "bg-brand-600/20 text-brand-300"
      }`}
    >
      {down ? <AlertTriangle className="h-4 w-4" /> : <Wifi className="h-4 w-4" />}
      <span>
        {feed === "CONNECTING" && "Đang kết nối feed…"}
        {feed === "RECONNECTING" && "Mất feed — đang kết nối lại, bot sẽ tạm dừng."}
        {feed === "DOWN" && "Feed DOWN — không có dữ liệu realtime."}
      </span>
    </div>
  );
}
