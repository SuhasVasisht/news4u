import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    headless: true,
  },
  webServer: process.env.E2E_BASE_URL ? undefined : {
    command: "npm run dev",
    env: {
      ...process.env,
      AUTH_SECRET: "playwright-secret",
      SYNC_API_KEY: "playwright-sync-key",
      INTERNAL_API_KEY: "playwright-internal-key",
      APP_TIMEZONE: "America/Los_Angeles",
      APP_DAILY_RESET_HOUR: "5",
    },
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
