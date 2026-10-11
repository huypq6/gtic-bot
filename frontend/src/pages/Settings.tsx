// Settings (stored in the DB, edited here — no .env): Telegram notifications.
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Search, Send, XCircle } from "lucide-react";
import {
  fetchTelegram,
  findTelegramChats,
  saveTelegram,
  testTelegram,
  type NotifyEvent,
  type TelegramPatch,
  type TelegramSettings,
} from "../lib/api";
import ModeBadge from "../components/ModeBadge";
import { t } from "../lib/i18n";

const EVENTS: { key: NotifyEvent; label: string; hint: string }[] = [
  { key: "trade_open", label: "Trade opened", hint: "side, entry, size, SL/TP, risk" },
  { key: "trade_close", label: "Trade closed", hint: "reason (SL/TP/…), PnL and R" },
  { key: "order_error", label: "Order failed", hint: "exchange rejected / network error" },
  { key: "protection", label: "Position protection", hint: "SL/TP not placed on the exchange, untracked position" },
  { key: "account_halt", label: "Account halted / resumed", hint: "daily loss or drawdown limit" },
  { key: "risk_reject", label: "Signal blocked by risk guard", hint: "can be frequent" },
  { key: "feed", label: "Market feed down / back", hint: "bots are auto-paused when the feed drops" },
  { key: "live_change", label: "LIVE bot / account created", hint: "security alert" },
];
const MODES = ["PAPER", "TESTNET", "LIVE"] as const;

export default function Settings() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["tg"], queryFn: fetchTelegram, refetchInterval: 10_000 });
  const [form, setForm] = useState<TelegramSettings | null>(null);
  const [token, setToken] = useState("");
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    if (data && !dirty) setForm(data);
  }, [data, dirty]);

  const upd = (p: Partial<TelegramSettings>) => {
    setForm((f) => (f ? { ...f, ...p } : f));
    setDirty(true);
  };

  const save = useMutation({
    mutationFn: () => {
      const body: TelegramPatch = {
        enabled: form!.enabled, chat_id: form!.chat_id, lang: form!.lang,
        modes: form!.modes, events: form!.events,
        ...(token.trim() ? { bot_token: token.trim() } : {}),
      };
      return saveTelegram(body);
    },
    onSuccess: (d) => {
      qc.setQueryData(["tg"], d);
      setForm(d);
      setToken("");
      setDirty(false);
    },
  });
  const test = useMutation({
    mutationFn: () => testTelegram({ bot_token: token.trim() || undefined, chat_id: form?.chat_id || undefined }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["tg"] }),
  });
  const chats = useMutation({ mutationFn: () => findTelegramChats({ bot_token: token.trim() || undefined }) });

  if (!form) return <div className="p-4 text-sm text-faint">{t("Loading…")}</div>;
  const canTalk = (token.trim() || form.has_token) && form.chat_id;
  const st = form.status;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
      <section className="mx-auto w-full max-w-3xl rounded-xl border border-border bg-surface p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">{t("Telegram notifications")}</h2>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => upd({ enabled: e.target.checked })}
              className="h-4 w-4 accent-accent"
            />
            {form.enabled ? t("On") : t("Off")}
          </label>
        </div>

        <p className="mb-3 text-xs text-faint">
          {st.last_error ? (
            <span className="flex items-center gap-1 text-down">
              <XCircle className="h-3.5 w-3.5" /> {t("Last error:")} {st.last_error}
            </span>
          ) : st.last_ok_at ? (
            <span className="flex items-center gap-1 text-up">
              <CheckCircle2 className="h-3.5 w-3.5" />
              {t("Last sent {time} · {n} message(s) since start", {
                time: new Date(st.last_ok_at * 1000).toLocaleString(),
                n: st.sent,
              })}
            </span>
          ) : (
            t("Nothing sent yet.")
          )}
        </p>

        {/* setup */}
        <ol className="mb-4 space-y-3 text-sm">
          <li>
            <p className="font-medium">1. {t("Create a bot")}</p>
            <p className="text-xs text-faint">
              {t("In Telegram open @BotFather → /newbot → choose a name → copy the token it gives you.")}
            </p>
            <input
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => {
                setToken(e.target.value);
                setDirty(true);
              }}
              placeholder={form.has_token ? t("saved {hint} — paste a new token to replace", { hint: form.token_hint }) : "123456789:AA…"}
              className="mt-1.5 w-full rounded-md border border-border bg-surface-2 px-2 py-1.5"
            />
          </li>
          <li>
            <p className="font-medium">2. {t("Find your chat")}</p>
            <p className="text-xs text-faint">
              {t("Open your new bot in Telegram, press Start (or send any message), then press Find my chat. For a group: add the bot to the group and send a message there.")}
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <button
                onClick={() => chats.mutate()}
                disabled={chats.isPending || !(token.trim() || form.has_token)}
                className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2 disabled:opacity-50"
              >
                <Search className="h-4 w-4" /> {chats.isPending ? t("Looking…") : t("Find my chat")}
              </button>
              <input
                value={form.chat_id}
                onChange={(e) => upd({ chat_id: e.target.value })}
                placeholder={t("chat id")}
                className="w-40 rounded-md border border-border bg-surface-2 px-2 py-1.5"
              />
            </div>
            {chats.isError && <p className="mt-1 text-xs text-down">{(chats.error as Error).message}</p>}
            {chats.data && (
              <div className="mt-2 rounded-md border border-border bg-surface-2 p-2 text-xs">
                <p className="mb-1 text-faint">@{chats.data.bot.username}</p>
                {chats.data.chats.length ? (
                  chats.data.chats.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => upd({ chat_id: c.id })}
                      className={`mr-2 mb-1 rounded border px-2 py-1 ${form.chat_id === c.id ? "border-accent bg-accent/10" : "border-border hover:bg-surface"}`}
                    >
                      {c.name || c.username || c.id} <span className="text-faint">· {c.type} · {c.id}</span>
                    </button>
                  ))
                ) : (
                  <p className="text-warn">{t("No messages yet — send a message to the bot first, then try again.")}</p>
                )}
              </div>
            )}
          </li>
          <li>
            <p className="font-medium">3. {t("Send a test")}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <button
                onClick={() => test.mutate()}
                disabled={test.isPending || !canTalk}
                className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2 disabled:opacity-50"
              >
                <Send className="h-4 w-4" /> {test.isPending ? t("Sending…") : t("Send test message")}
              </button>
              {test.isSuccess && <span className="text-xs text-up">{t("Sent — check Telegram.")}</span>}
              {test.isError && <span className="text-xs text-down">{(test.error as Error).message}</span>}
            </div>
          </li>
        </ol>

        {/* what to send */}
        <div className="mb-4 border-t border-border pt-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">{t("What to send")}</p>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {EVENTS.map((ev) => (
              <label key={ev.key} className="flex cursor-pointer items-start gap-2 rounded-md px-1 py-1 text-sm hover:bg-surface-2">
                <input
                  type="checkbox"
                  checked={form.events[ev.key]}
                  onChange={(e) => upd({ events: { ...form.events, [ev.key]: e.target.checked } })}
                  className="mt-0.5 h-4 w-4"
                />
                <span>
                  {t(ev.label)}
                  <span className="block text-xs text-faint">{t(ev.hint)}</span>
                </span>
              </label>
            ))}
          </div>
        </div>

        <div className="mb-4 flex flex-wrap items-start gap-6 border-t border-border pt-3">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">{t("For which modes")}</p>
            <div className="flex flex-wrap gap-3">
              {MODES.map((m) => (
                <label key={m} className="flex cursor-pointer items-center gap-1.5 text-sm">
                  <input
                    type="checkbox"
                    checked={form.modes[m]}
                    onChange={(e) => upd({ modes: { ...form.modes, [m]: e.target.checked } })}
                    className="h-4 w-4"
                  />
                  <ModeBadge mode={m} />
                </label>
              ))}
            </div>
            <p className="mt-1 text-xs text-faint">{t("Feed and LIVE-security alerts are always sent.")}</p>
          </div>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs font-semibold uppercase tracking-wide text-faint">{t("Message language")}</span>
            <select
              value={form.lang}
              onChange={(e) => upd({ lang: e.target.value as "vi" | "en" })}
              className="rounded-md border border-border bg-surface-2 px-2 py-1.5"
            >
              <option value="vi">Tiếng Việt</option>
              <option value="en">English</option>
            </select>
          </label>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-border pt-3">
          {save.isError && <span className="text-xs text-down">{(save.error as Error).message}</span>}
          {dirty && <span className="text-xs text-warn">{t("Unsaved changes")}</span>}
          <button
            onClick={() => save.mutate()}
            disabled={!dirty || save.isPending}
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
          >
            {save.isPending ? t("Saving…") : t("Save")}
          </button>
        </div>
      </section>
    </div>
  );
}
