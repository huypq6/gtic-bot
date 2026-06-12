interface Props {
  timeframes: string[];
  active: string;
  onSelect: (tf: string) => void;
}

export default function TimeframeSelector({ timeframes, active, onSelect }: Props) {
  return (
    <div className="flex gap-1">
      {timeframes.map((tf) => (
        <button
          key={tf}
          onClick={() => onSelect(tf)}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
            tf === active
              ? "bg-brand-600 text-ink-100"
              : "text-ink-400 hover:bg-ink-800 hover:text-ink-100"
          }`}
        >
          {tf}
        </button>
      ))}
    </div>
  );
}
