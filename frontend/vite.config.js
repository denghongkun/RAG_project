import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    // 开发时前端走同源 /api，由 Vite 转发到 FastAPI，避免直连 8000 端口未开导致 ERR_CONNECTION_REFUSED
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
        timeout: 0,
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes, _req, res) => {
            const ct = proxyRes.headers["content-type"];
            if (ct && String(ct).toLowerCase().includes("text/event-stream") && typeof res.flushHeaders === "function") {
              res.flushHeaders();
            }
          });
        },
      },
    },
  },
});
