import { mkdtempSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

const runtimeDirectory = process.env.TRIP_E2E_RUNTIME_DIR
  ?? mkdtempSync(join(tmpdir(), "ai-travel-intent-e2e-"));
const databasePath = join(runtimeDirectory, "trips.sqlite3");
const artifactRoot = join(runtimeDirectory, "artifacts");
const logDirectory = join(runtimeDirectory, "logs");

mkdirSync(artifactRoot, { recursive: true });
mkdirSync(logDirectory, { recursive: true });
process.env.TRIP_E2E_RUNTIME_DIR = runtimeDirectory;
process.env.TRIP_E2E_DATABASE_PATH = databasePath;
process.env.TRIP_E2E_PYTHON ??= ".venv/bin/python";

const backendEnvironment = {
  APP_ENV: "development",
  AMAP_API_KEY: "",
  OPENAI_API_KEY: "",
  POI_DISCOVERY_MODE: "fallback",
  CORS_ALLOW_ORIGINS: "http://127.0.0.1:3018",
  TRIP_ALLOWED_ORIGINS: "http://127.0.0.1:3018",
  TRIP_CAPABILITY_COOKIE_SECURE: "false",
  TRIP_STORE_MODE: "sqlite",
  TRIP_STORE_PATH: databasePath,
  IMPORT_ARTIFACT_ROOT: artifactRoot,
  IMPORT_URL_ENABLED: "false",
  LOG_LEVEL: "WARNING",
};

export default defineConfig({
  testDir: "tests/e2e",
  testMatch: "draft-intent-confirmation.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  outputDir: "test-results/intent",
  use: {
    baseURL: "http://127.0.0.1:3018",
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: `${process.env.TRIP_E2E_PYTHON} -m uvicorn tests.e2e_fixture_app:app --host 127.0.0.1 --port 8018`,
      cwd: "../backend",
      env: backendEnvironment,
      url: "http://127.0.0.1:8018/readiness",
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: "npm run start -- --hostname 127.0.0.1 --port 3018",
      cwd: ".",
      env: {
        NEXT_TELEMETRY_DISABLED: "1",
        TRIP_API_PROXY_TARGET: "http://127.0.0.1:8018",
      },
      url: "http://127.0.0.1:3018",
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
