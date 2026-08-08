import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// BFF is a separate Cloud Run service in every real environment; in local
// dev, proxy /api to it directly so the SPA can call relative paths
// (matches how it's called once both sit behind the same IAP-fronted load
// balancer in prod -- see plan §1/§4).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.BFF_URL ?? "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
