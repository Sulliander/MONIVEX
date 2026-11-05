import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 90000,
  expect: { timeout: 20000 },
  workers: 1,
  retries: 0,
  use: {
    baseURL: process.env.MONIVEX_TEST_URL || "http://localhost:18080",
    launchOptions: process.env.MONIVEX_CHROMIUM
      ? { executablePath: process.env.MONIVEX_CHROMIUM }
      : {},
  },
  reporter: "list",
});
