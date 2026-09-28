// i18n — English is the source language; strings are written in English and looked up
// in the Vietnamese dictionary when lang = "vi". Switching language reloads the page, so a
// plain `t()` call (no hook) is always consistent, even in module-level helpers.
import { VI } from "../locales/vi";

export type Lang = "en" | "vi";
const KEY = "gtic-lang";

function readLang(): Lang {
  try {
    return localStorage.getItem(KEY) === "vi" ? "vi" : "en";
  } catch {
    return "en";
  }
}

export const lang: Lang = readLang();
document.documentElement.lang = lang;

export function setLang(l: Lang) {
  try {
    localStorage.setItem(KEY, l);
  } catch {
    /* ignore */
  }
  location.reload();
}

/** Translate an English source string; `{name}` placeholders are filled from `vars`. */
export function t(s: string, vars?: Record<string, string | number>): string {
  let out = lang === "vi" ? (VI[s] ?? s) : s;
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v));
  return out;
}
