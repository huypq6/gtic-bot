// Đọc màu chart từ CSS variable theme (không hardcode) → chart theo sáng/tối.
function v(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export interface ChartColors {
  up: string;
  down: string;
  text: string;
  grid: string;
  emaFast: string;
  emaSlow: string;
  line: string;
}

export function chartColors(): ChartColors {
  return {
    up: v("--up"),
    down: v("--down"),
    text: v("--muted"),
    grid: v("--border"),
    emaFast: v("--primary"),
    emaSlow: v("--accent"),
    line: v("--accent"),
  };
}
