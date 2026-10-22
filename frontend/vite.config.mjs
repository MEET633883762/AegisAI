import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const frontendRoot = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: frontendRoot,
  base: "./",
  plugins: [react()],
  publicDir: false,
  build: {
    outDir: resolve(frontendRoot, ".vite-build"),
    emptyOutDir: true,
    sourcemap: false,
    target: ["chrome107", "edge107", "firefox104", "safari16"],
    rollupOptions: {
      input: {
        index: resolve(frontendRoot, "index.html"),
        dashboard: resolve(frontendRoot, "dashboard.html"),
        privacy: resolve(frontendRoot, "privacy.html"),
      },
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: (asset) => asset.name?.endsWith(".css")
          ? "assets/app.css"
          : `assets/${asset.name ?? "asset"}`,
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/public_shell.test.ts", "tests/research_demo.test.ts"],
    restoreMocks: true,
    clearMocks: true,
  },
});
