import { AlertTriangle, Wifi } from "lucide-react";
import { useWsStore } from "../lib/ws";
import { t } from "../lib/i18n";

// US-27: warning when the feed connection is lost. OK → hidden.
export default function FeedBanner() {
  const feed = useWsStore((s) => s.feed);
  if (feed === "OK") return null;

  const down = feed === "DOWN";
  return (
    <div
      className={`flex items-center gap-2 px-4 py-1.5 text-sm ${
        down ? "bg-down/20 text-down" : "bg-primary/20 text-muted"
      }`}
    >
      {down ? <AlertTriangle className="h-4 w-4" /> : <Wifi className="h-4 w-4" />}
      <span>
        {feed === "CONNECTING" && t("Connecting to feed…")}
        {feed === "RECONNECTING" && t("Feed lost — reconnecting…")}
        {feed === "DOWN" && t("Feed DOWN — bots auto-PAUSED (US-27). Reconnecting does not auto-resume.")}
      </span>
    </div>
  );
}
