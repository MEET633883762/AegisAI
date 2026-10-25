import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const frontendRoot = dirname(fileURLToPath(import.meta.url));

function localDashboardUrls(command) {
  return {
    name: "aegisai-local-dashboard-urls",
    configureServer(server) {
      if (command !== "serve") return;

      server.httpServer?.once("listening", () => {
        const urls = server.resolvedUrls;
        if (!urls) return;

        console.log("\n  AegisAI local operations dashboard:");
        for (const url of urls.local ?? []) {
          console.log(`  Local:   ${url}local-dashboard.html`);
        }
        for (const url of urls.network ?? []) {
          console.log(`  Network: ${url}local-dashboard.html`);
        }
      });
    },
  };
}

export default defineConfig(({ command }) => ({
  root: frontendRoot,
  base: "./",
  plugins: [react(), localDashboardUrls(command)],
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
        "local-dashboard": resolve(frontendRoot, "local-dashboard.html"),
      },

      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: (asset) =>
          asset.name?.endsWith(".css")
            ? "assets/app.css"
            : `assets/${asset.name ?? "asset"}`,
      },
    },
  },
  test: {
    environment: "jsdom",
    include: [
      "tests/public_shell.test.ts",
      "tests/research_demo.test.ts",
      "tests/local_dashboard.test.tsx",
    ],
    restoreMocks: true,
    clearMocks: true,
  },
}));
