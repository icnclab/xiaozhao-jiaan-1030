import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// 開發時 /api 代理到本機 FastAPI；正式部署由 nginx 反向代理（見 deploy/nginx.conf）。
// VITE_API_PROXY_TARGET 可覆寫代理目標（例如另開一個隔離測試用後端），預設維持原行為不變。
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8140", changeOrigin: false },
    },
  },
  // `frontend/dist` is the production directory mounted by FastAPI.  A normal
  // developer build must never mutate it; the reviewed deployment script uses
  // an explicit, timestamped --outDir and atomically publishes index.html.
  build: { outDir: "build", sourcemap: false },
  test: {
    // This host also runs the live 小照 services (8140/8147/8165/8166/Ollama).
    // Vitest's default thread pool spins up one jsdom worker per CPU core
    // (20 here); under real production load that starves individual tests'
    // async waits (e.g. findByRole) well before anything is actually broken,
    // which showed up as a test that only failed in the full run, never
    // alone. Capping concurrency fixes the actual resource contention
    // instead of papering over it with a longer per-test timeout.
    // A maxThreads cap (tried 4) still intermittently starved the slowest
    // multi-hop async test under real host load, so this runs one worker at
    // a time; each test file still gets its own fresh module/DOM instance.
    poolOptions: { threads: { singleThread: true } },
  },
});
