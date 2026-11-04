import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // Vite 8 transforms JSX with oxc; no React plugin is needed for tests.
  oxc: { jsx: { runtime: "automatic" } },
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    // No simulated latency in tests; the default data mode is mock.
    env: { NEXT_PUBLIC_MOCK_LATENCY_MS: "0" },
  },
});
