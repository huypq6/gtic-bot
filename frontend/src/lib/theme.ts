// Theme switch sáng/tối — set/bỏ class `.dark` trên <html>, lưu localStorage.
import { create } from "zustand";

export type Theme = "light" | "dark";
const KEY = "gtic-theme";

function apply(t: Theme) {
  document.documentElement.classList.toggle("dark", t === "dark");
}

const stored = (localStorage.getItem(KEY) as Theme | null) ?? "light";
apply(stored);

interface ThemeState {
  theme: Theme;
  toggle: () => void;
  set: (t: Theme) => void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: stored,
  toggle: () => get().set(get().theme === "dark" ? "light" : "dark"),
  set: (t) => {
    localStorage.setItem(KEY, t);
    apply(t);
    set({ theme: t });
  },
}));
