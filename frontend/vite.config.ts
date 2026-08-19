/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import path from "path";

import { seoPlugin } from "./vite-plugin-seo";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    // Refuse to start rather than drift to 8081 when 8080 is busy. The drift is
    // silent and the page still loads, so the app looks up - but its Origin is
    // no longer in the backend's CORS allowlist (backend/app/api_guard.py
    // DEFAULT_ORIGINS), so every API call dies at the preflight with a bare
    // "400 Bad Request" in the uvicorn log. start.bat polls 8080 too, so it
    // never opens the browser either. A stale dev server from a previous run is
    // the usual cause, and a loud "port in use" points straight at it.
    strictPort: true,
    hmr: {
      overlay: false,
    },
  },
  plugins: [
    react(),
    // Emits dist/404.html always, and dist/sitemap.xml plus the robots.txt
    // pointer only when a real origin is configured. Reads the same route
    // table as the app and the Caddyfile.
    seoPlugin({ siteUrl: process.env.VITE_SITE_URL }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime"],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // Narrow on purpose. The default glob would also collect e2e/*.spec.ts,
    // where Playwright's `test` and `expect` are different objects from
    // vitest's — the two harnesses must not see each other's files.
    include: ["src/**/*.test.{ts,tsx}"],
  },
}));
