// Badge mode nổi bật (US-15). Màu theo ma trận an toàn: paper=teal, testnet=amber, live=đỏ.
const STYLES: Record<string, string> = {
  PAPER: "bg-accent-500/15 text-accent-400 border-accent-500/30",
  TESTNET: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  LIVE: "bg-down/15 text-down border-down/30",
};

export default function ModeBadge({ mode }: { mode: string }) {
  const cls = STYLES[mode] ?? "bg-ink-800 text-ink-400 border-ink-700";
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ${cls}`}>
      {mode}
    </span>
  );
}
