import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e-product-reset",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  outputDir: "test-results/product-reset",
  use: {
    baseURL: "http://127.0.0.1:3022",
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: "npm run start -- --hostname 127.0.0.1 --port 3022",
    cwd: ".",
    env: { NEXT_TELEMETRY_DISABLED: "1" },
    url: "http://127.0.0.1:3022/product-reset-preview",
    timeout: 120_000,
    reuseExistingServer: false,
  },
});
