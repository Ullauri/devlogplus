import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

/**
 * Vitest configuration for integration tests.
 *
 * Differences from the default (unit) config:
 *   - Uses a globalSetup that starts/stops a Prism mock server
 *   - Targets only *.integration.test.ts files
 *   - Sets VITE_API_BASE_URL so the API client hits Prism
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.integration.test.{ts,tsx}"],
    globalSetup: ["./src/test/prism-global-setup.ts"],
    testTimeout: 15_000,
    env: {
      VITE_API_BASE_URL: "http://localhost:4010/api/v1",
    },
  },
});
