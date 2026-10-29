import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run build` writes into the folder FastAPI serves; `npm run dev` proxies
// API calls to the running Python server.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../academic_helpdesk/web/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
