// Render form params từ param_schema (US-06) — không cần sửa code.
interface Spec {
  type?: string;
  min?: number;
  max?: number;
  default?: number;
}

export default function ParamsForm({
  schema,
  values,
  onChange,
}: {
  schema: Record<string, Spec>;
  values: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}) {
  const keys = Object.keys(schema ?? {});
  if (!keys.length) return null;

  return (
    <div className="flex flex-wrap items-end gap-2">
      {keys.map((k) => {
        const spec = schema[k];
        return (
          <label key={k} className="flex flex-col gap-1">
            <span className="text-xs text-faint">
              {k}
              {spec.min !== undefined && (
                <span className="ml-1 text-faint">
                  [{spec.min}…{spec.max ?? "∞"}]
                </span>
              )}
            </span>
            <input
              type="number"
              step={spec.type === "int" ? 1 : "any"}
              value={String(values[k] ?? spec.default ?? "")}
              onChange={(e) =>
                onChange({
                  ...values,
                  [k]: e.target.value === "" ? "" : Number(e.target.value),
                })
              }
              className="w-24 rounded-md border border-border bg-surface-2 px-2 py-1.5 text-sm"
            />
          </label>
        );
      })}
    </div>
  );
}
