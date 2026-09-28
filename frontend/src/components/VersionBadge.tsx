import { useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { fetchVersion, type VersionInfo } from "../lib/api";
import { t, lang } from "../lib/i18n";

const fmt = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString(lang === "vi" ? "vi-VN" : "en-GB", { hour12: false }) : "—";

function label(v: VersionInfo) {
  const parts = [`v${v.version}`];
  if (v.build) parts.push(`#${v.build}`);
  parts.push(v.commit ?? "dev");
  return parts.join(" · ") + (v.dirty ? "*" : "");
}

/** Running version shown in the header. Re-polls every minute: if the server runs a different build than the one loaded → reload button. */
export default function VersionBadge() {
  const { data } = useQuery({
    queryKey: ["version"],
    queryFn: fetchVersion,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
  const loaded = useRef<string | null>(null);
  if (!data) return null;
  const key = `${data.commit}|${data.built_at ?? ""}`;
  loaded.current ??= key;
  const outdated = loaded.current !== key;

  const title = [
    t("Version {v}", { v: label(data) }),
    data.subject && `Commit: ${data.subject}`,
    t("Commit date: {d}", { d: fmt(data.commit_date) }),
    data.built_at && `Build: ${fmt(data.built_at)}`,
    t("Server up since: {d}", { d: fmt(data.started_at) }),
  ]
    .filter(Boolean)
    .join("\n");

  if (outdated) {
    return (
      <button
        onClick={() => window.location.reload()}
        title={t("Server updated to {v} — click to reload", { v: label(data) })}
        className="flex items-center gap-1 rounded-md bg-primary/15 px-2 py-1 font-medium text-primary hover:bg-primary/25"
      >
        <RefreshCw className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">{t("Update available")}</span>
      </button>
    );
  }
  return (
    <span title={title} className="hidden cursor-default font-mono text-faint md:inline">
      {label(data)}
    </span>
  );
}
