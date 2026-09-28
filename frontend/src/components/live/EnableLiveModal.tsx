import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { t } from "../../lib/i18n";

// US-14: LIVE safeguard — only allowed after typing "LIVE" exactly. Red warning.
export default function EnableLiveModal({
  symbol,
  onConfirm,
  onCancel,
}: {
  symbol: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState("");
  const ok = text === "LIVE";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-2xl border border-down/40 bg-surface p-6 shadow-2xl">
        <div className="flex items-center gap-2 text-down">
          <AlertTriangle className="h-6 w-6" />
          <h2 className="text-lg font-bold">{t("LIVE MODE — REAL MONEY")}</h2>
        </div>
        <p className="mt-3 text-sm text-muted">
          {t("Bot")} <span className="font-semibold">{symbol}</span> {t("will place orders with")}{" "}
          <span className="font-semibold text-down">{t("real money")}</span>{" "}
          {t("on Binance. Make sure the API key has withdrawals disabled + IP whitelist.")}
        </p>
        <p className="mt-3 text-sm text-muted">
          {t("Type ")}<span className="font-mono font-semibold text-down">LIVE</span>{" "}
          {t("to confirm:")}
        </p>
        <input
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="LIVE"
          className="mt-2 w-full rounded-md border border-down/40 bg-bg px-3 py-2 font-mono text-text"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-md px-3 py-1.5 text-sm text-muted hover:bg-surface-2"
          >
            {t("Cancel")}
          </button>
          <button
            onClick={onConfirm}
            disabled={!ok}
            className="rounded-md bg-down px-3 py-1.5 text-sm font-semibold text-white hover:bg-down/90 disabled:opacity-40"
          >
            {t("Run LIVE")}
          </button>
        </div>
      </div>
    </div>
  );
}
