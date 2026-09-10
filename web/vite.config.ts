import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The client owns every URL now: Phase 8 deleted the Jinja pages, so there is
// nothing left at "/" for it to share the site with. Flask serves /api and
// nothing else.
export default defineConfig({
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
  // `vite preview` serves web/dist the way Vercel will: static files, and
  // index.html for any path that is not one. The proxy is what makes it a
  // rehearsal rather than a demonstration -- without it the built bundle
  // has no API to talk to, and the only place the build gets exercised is
  // production.
  preview: {
    port: 4173,
    proxy: {
      "/api": { target: "http://127.0.0.1:5000", changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
