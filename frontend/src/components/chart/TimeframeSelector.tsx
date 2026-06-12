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
              ? "bg-primary text-white"
              : "text-muted hover:bg-surface-2 hover:text-text"
          }`}
        >
          {tf}
        </button>
      ))}
    </div>
  );
}
