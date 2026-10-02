import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// While developing, the website runs on port 5173 and the server on port 8000.
// Requests starting with /api are passed through to the server, so the browser
// treats both as one site.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": process.env.API_URL ?? "http://localhost:8000" },
  },
});
