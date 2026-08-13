import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["web/test/**/*.test.ts", "web/test/**/*.test.tsx"],
    environment: "jsdom",
    setupFiles: "./web/test/setup.ts",
    css: true,
  },
});
