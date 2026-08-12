import { mkdtempSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

const runtimeDirectory = process.env.TRIP_COMPILER_E2E_RUNTIME_DIR ?? mkdtempSync(join(tmpdir(), "ai-trip-compiler-e2e-"));
const databasePath = process.env.TRIP_COMPILER_E2E_DATABASE_PATH ?? join(runtimeDirectory, "trips.sqlite3");
const artifactRoot = join(runtimeDirectory, "artifacts");

mkdirSync(artifactRoot, { recursive: true });
process.env.TRIP_COMPILER_E2E_RUNTIME_DIR = runtimeDirectory;
process.env.TRIP_COMPILER_E2E_DATABASE_PATH = databasePath;

export default defineConfig({
  testDir: "tests/e2e",
  testMatch: "trip-compiler.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 12_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  outputDir: "test-results/trip-compiler",
  use: {
    baseURL: "http://127.0.0.1:3028",
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: `${process.env.TRIP_E2E_PYTHON ?? ".venv/bin/python"} -m uvicorn app.main:app --host 127.0.0.1 --port 8028`,
      cwd: "../backend",
      env: {
        APP_ENV: "development",
        AMAP_API_KEY: "",
        OPENAI_API_KEY: "",
        POI_DISCOVERY_MODE: "fallback",
        CORS_ALLOW_ORIGINS: "http://127.0.0.1:3028",
        TRIP_ALLOWED_ORIGINS: "http://127.0.0.1:3028",
        TRIP_CAPABILITY_COOKIE_SECURE: "false",
        TRIP_STORE_MODE: "sqlite",
        TRIP_STORE_PATH: databasePath,
        IMPORT_ARTIFACT_ROOT: artifactRoot,
        IMPORT_URL_ENABLED: "false",
        LOG_LEVEL: "WARNING",
      },
      url: "http://127.0.0.1:8028/readiness",
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: "npm run start -- --hostname 127.0.0.1 --port 3028",
      cwd: ".",
      env: {
        NEXT_TELEMETRY_DISABLED: "1",
        TRIP_API_PROXY_TARGET: "http://127.0.0.1:8028",
      },
      url: "http://127.0.0.1:3028",
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
