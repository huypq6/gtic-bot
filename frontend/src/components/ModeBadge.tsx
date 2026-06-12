// Badge mode nổi bật (US-15). Màu theo ma trận an toàn: paper=teal, testnet=amber, live=đỏ.
const STYLES: Record<string, string> = {
  PAPER: "bg-accent/15 text-accent border-accent/30",
  TESTNET: "bg-warn/15 text-warn border-warn/30",
  LIVE: "bg-down/15 text-down border-down/30",
};

export default function ModeBadge({ mode }: { mode: string }) {
  const cls = STYLES[mode] ?? "bg-surface-2 text-muted border-border";
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ${cls}`}>
      {mode}
    </span>
  );
}
