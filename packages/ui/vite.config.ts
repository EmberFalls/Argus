import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  envDir: path.resolve(rootDir, "../.."),
  plugins: [react()],
  resolve: {
    alias: { "@": rootDir },
  },
  server: { port: 5173 },
  preview: { port: 4173 },
});
