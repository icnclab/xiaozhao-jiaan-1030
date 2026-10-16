import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 開發時 /api 代理到本機 FastAPI；正式部署由 nginx 反向代理（見 deploy/nginx.conf）。
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8140", changeOrigin: false },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
