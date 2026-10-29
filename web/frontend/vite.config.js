import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run build` writes ./dist, which web/backend/service.py serves.
// `npm run dev` proxies API calls to the running Python service.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
