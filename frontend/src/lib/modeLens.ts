// Global mode lens (docs/08): which trading "world" the UI shows — All, PAPER, TESTNET or LIVE.
// View filter only: it never changes which bots run or where orders go. Persisted per browser.
import { create } from "zustand";

export type Lens = "" | "PAPER" | "TESTNET" | "LIVE";
export const LENSES: Lens[] = ["", "PAPER", "TESTNET", "LIVE"];
const KEY = "gtic.lens";

function read(): Lens {
  try {
    const v = localStorage.getItem(KEY) ?? "";
    return (LENSES as string[]).includes(v) ? (v as Lens) : "";
  } catch {
    return "";
  }
}

interface LensState {
  lens: Lens;
  setLens: (l: Lens) => void;
}

export const useModeLens = create<LensState>((set) => ({
  lens: read(),
  setLens: (l) => {
    try {
      localStorage.setItem(KEY, l);
    } catch {
      /* private mode — keep it in memory only */
    }
    set({ lens: l });
  },
}));

/** true if a row of `mode` is visible under the current lens. */
export const inLens = (lens: Lens, mode: string | null | undefined) => !lens || mode === lens;
