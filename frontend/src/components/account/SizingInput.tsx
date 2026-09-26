import type { Sizing } from "../../lib/api";

// Chọn cách tính khối lượng lệnh theo vốn — dùng ở tạo bot (Trading) + backtest.
const SIZING_UNIT: Record<string, string> = {
  risk_pct: "% vốn",
  risk_usdt: "USDT",
  notional_pct: "% vốn",
  notional_usdt: "USDT",
  fixed_qty: "coin",
};

export const sizingText = (z: Sizing) =>
  z.method === "risk_pct"
    ? `rủi ro ${z.value}%/lệnh`
    : z.method === "risk_usdt"
      ? `rủi ro ${z.value} USDT/lệnh`
      : z.method === "notional_pct"
        ? `lệnh ${z.value}% vốn`
        : z.method === "notional_usdt"
          ? `lệnh ${z.value} USDT`
          : `${z.value || "size strategy"} coin`;

export default function SizingInput({
  value,
  onChange,
  methods,
  label = "Khối lượng lệnh",
}: {
  value: Sizing;
  onChange: (z: Sizing) => void;
  methods?: Record<string, string>;
  label?: string;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-faint">{label}</span>
      <div className="flex items-center gap-1">
        <select
          value={value.method}
          onChange={(e) => onChange({ ...value, method: e.target.value })}
          title={methods?.[value.method]}
          className="rounded-md border border-border bg-surface-2 px-2 py-1.5 text-sm"
        >
          {Object.entries(methods ?? { risk_pct: "" }).map(([k, d]) => (
            <option key={k} value={k} title={d}>
              {d || k}
            </option>
          ))}
        </select>
        <input
          type="number"
          min={0}
          step="any"
          value={value.value}
          onChange={(e) => onChange({ ...value, value: Number(e.target.value) })}
          className="w-20 rounded-md border border-border bg-surface-2 px-2 py-1.5 text-sm"
        />
        <span className="text-xs text-faint">{SIZING_UNIT[value.method]}</span>
      </div>
    </label>
  );
}

