import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// DEV: mở http://localhost:5173. Proxy /api + /ws sang FastAPI.
// Target: host dev → localhost:8000; docker dev → api:8000 (VITE_PROXY_TARGET).
// PROD: build ra dist/, FastAPI serve static (không qua Vite).
const target = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";
const wsTarget = target.replace(/^http/, "ws");

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target, changeOrigin: true },
      "/ws": { target: wsTarget, ws: true },
    },
  },
  build: {
    outDir: "dist",
  },
});
