import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// DEV: mở http://localhost:5173. Proxy /api + /ws sang FastAPI.
// Target: host dev → localhost:8000; docker dev → api:8000 (VITE_PROXY_TARGET).
// PROD: build ra dist/, FastAPI serve static (không qua Vite).
const target = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";
const wsTarget = target.replace(/^http/, "ws");

// Cho phép truy cập dev server từ host lạ (mobile qua LAN/Tailscale, vd "tsp32").
// VITE_ALLOWED_HOSTS="tsp32,my-host" để giới hạn; mặc định true = mọi host.
const allowedHosts =
  process.env.VITE_ALLOWED_HOSTS?.split(",").map((h) => h.trim()) ?? true;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true, // lắng nghe 0.0.0.0 → truy cập được từ điện thoại cùng mạng
    port: 5173,
    allowedHosts,
    proxy: {
      "/api": { target, changeOrigin: true },
      "/ws": { target: wsTarget, ws: true },
    },
  },
  build: {
    outDir: "dist",
  },
});
