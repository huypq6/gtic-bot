import { Info } from "lucide-react";
import { GLOSSARY } from "../lib/glossary";

// Nhãn kèm icon ⓘ; hover hiện tooltip giải thích (từ glossary theo `term`, hoặc `text`).
export default function InfoTip({
  term,
  text,
  children,
  align = "center",
}: {
  term?: string;
  text?: string;
  children: React.ReactNode;
  align?: "center" | "left";
}) {
  const tip = text ?? (term ? GLOSSARY[term] : undefined);
  if (!tip) return <>{children}</>;

  const pos = align === "left" ? "left-0" : "left-1/2 -translate-x-1/2";
  return (
    <span className="group/tip relative inline-flex items-center gap-1">
      {children}
      <Info className="h-3 w-3 shrink-0 cursor-help text-faint" />
      <span
        className={`pointer-events-none absolute top-full ${pos} z-40 mt-1 w-56 whitespace-normal rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs font-normal normal-case tracking-normal text-muted opacity-0 shadow-lg transition-opacity duration-150 group-hover/tip:opacity-100`}
      >
        {tip}
      </span>
    </span>
  );
}
