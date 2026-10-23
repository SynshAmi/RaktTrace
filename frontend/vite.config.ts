import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// RAKT_API (env or frontend/.env.local) points the proxy at a backend on another port.
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": loadEnv(mode, ".", "RAKT_").RAKT_API || "http://127.0.0.1:8000" },
  },
}));
