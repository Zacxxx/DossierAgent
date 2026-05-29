import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiProxyTarget = process.env.DOSSIERAGENT_API_PROXY_TARGET ?? "http://127.0.0.1:8000";
const devHost = process.env.VITE_DEV_HOST ?? "127.0.0.1";
const devPort = Number.parseInt(process.env.VITE_DEV_PORT ?? "5173", 10);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: devHost,
    port: devPort,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
});
