import { defineConfig } from "vite";
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
  build: { outDir: "dist", sourcemap: false },
});
