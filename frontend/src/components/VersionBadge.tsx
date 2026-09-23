import { useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { fetchVersion, type VersionInfo } from "../lib/api";

const fmt = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("vi-VN", { hour12: false }) : "—";

function label(v: VersionInfo) {
  const parts = [`v${v.version}`];
  if (v.build) parts.push(`#${v.build}`);
  parts.push(v.commit ?? "dev");
  return parts.join(" · ") + (v.dirty ? "*" : "");
}

/** Phiên bản đang chạy ở header. Hỏi lại mỗi phút: server lên bản khác bản đã tải → nút tải lại. */
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
    `Phiên bản ${label(data)}`,
    data.subject && `Commit: ${data.subject}`,
    `Ngày commit: ${fmt(data.commit_date)}`,
    data.built_at && `Build: ${fmt(data.built_at)}`,
    `Server chạy từ: ${fmt(data.started_at)}`,
  ]
    .filter(Boolean)
    .join("\n");

  if (outdated) {
    return (
      <button
        onClick={() => window.location.reload()}
        title={`Server đã cập nhật lên ${label(data)} — bấm để tải lại`}
        className="flex items-center gap-1 rounded-md bg-primary/15 px-2 py-1 font-medium text-primary hover:bg-primary/25"
      >
        <RefreshCw className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Có bản mới</span>
      </button>
    );
  }
  return (
    <span title={title} className="hidden cursor-default font-mono text-faint md:inline">
      {label(data)}
    </span>
  );
}
