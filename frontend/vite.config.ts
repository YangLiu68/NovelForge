import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API runs separately (uvicorn on :8000 by default); the dev server proxies /api to it.
const apiTarget = process.env.NOVELFORGE_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.NOVELFORGE_WEB_PORT ?? 5173),
    strictPort: true,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  preview: {
    port: Number(process.env.NOVELFORGE_WEB_PORT ?? 4173),
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
});
