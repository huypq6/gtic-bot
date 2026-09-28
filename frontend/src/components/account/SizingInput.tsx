import type { Sizing } from "../../lib/api";
import { t } from "../../lib/i18n";

// Choose how position size is derived from equity — used when creating a bot (Trading) + in backtest.
const SIZING_UNIT: Record<string, string> = {
  risk_pct: t("% equity"),
  risk_usdt: "USDT",
  notional_pct: t("% equity"),
  notional_usdt: "USDT",
  fixed_qty: "coin",
};

export const sizingText = (z: Sizing) =>
  z.method === "risk_pct"
    ? t("risk {v}%/trade", { v: z.value })
    : z.method === "risk_usdt"
      ? t("risk {v} USDT/trade", { v: z.value })
      : z.method === "notional_pct"
        ? t("size {v}% of equity", { v: z.value })
        : z.method === "notional_usdt"
          ? t("size {v} USDT", { v: z.value })
          : `${z.value || "size strategy"} coin`;

export default function SizingInput({
  value,
  onChange,
  methods,
  label = t("Position size"),
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

