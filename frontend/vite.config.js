import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api and /ws to the FastAPI backend so the frontend can use
// same-origin relative URLs in development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Accept any Host header so a public tunnel hostname (e.g. *.trycloudflare.com)
    // is not rejected when sharing the dev server.
    allowedHosts: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});
