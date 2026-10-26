import { defineConfig, devices } from "@playwright/test";

/** End-to-end checks against the production build on saved data (RIPPLE_GATEWAY unset). */
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  fullyParallel: true,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:3100",
    ...devices["Desktop Chrome"],
    // CI installs the browser this Playwright expects; elsewhere PW_CHROMIUM can point at another Chromium.
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
  webServer: {
    command: "npx next start -p 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: !process.env.CI,
    env: { RIPPLE_DEMO: "1" },
    timeout: 120_000,
  },
});
