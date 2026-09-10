import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The SPA is served under /app while the old Jinja app still owns /. Phase 8
// flips both this base and the router basename to "/" and deletes the templates.
export default defineConfig({
  base: "/app/",
  plugins: [react()],
  server: {
    port: 5173,
    // In development the Flask API runs separately on 5000. Proxying keeps the
    // browser on one origin, so the session cookie and CSRF header behave
    // exactly as they do in production.
    proxy: {
      "/api": { target: "http://127.0.0.1:5000", changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
