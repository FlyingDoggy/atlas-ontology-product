import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    sourcemap: false,
    target: "es2022",
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8790",
      "/control": "http://127.0.0.1:8791",
      "/agent-control": "http://127.0.0.1:8792",
      "/auth": "http://127.0.0.1:8793",
    },
  },
  test: {
    environment: "jsdom",
  },
});
