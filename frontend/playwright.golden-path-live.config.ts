import { mkdtempSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

const runtime = mkdtempSync(join(tmpdir(), "golden-path-live-"));
const artifacts = join(runtime, "artifacts");
mkdirSync(artifacts, { recursive: true });

export default defineConfig({
  testDir: "tests/e2e-golden-path-live",
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 12_000 },
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:3026", browserName: "chromium", headless: true, trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: [
    {
      command: `${process.env.TRIP_E2E_PYTHON ?? ".venv/bin/python"} -m uvicorn app.main:app --host 127.0.0.1 --port 8026`,
      cwd: "../backend",
      env: { APP_ENV: "development", OPENAI_API_KEY: "", AMAP_API_KEY: "", POI_DISCOVERY_MODE: "fallback", TRIP_STORE_MODE: "sqlite", TRIP_STORE_PATH: join(runtime, "trips.sqlite3"), IMPORT_ARTIFACT_ROOT: artifacts, TRIP_ALLOWED_ORIGINS: "http://127.0.0.1:3026", CORS_ALLOW_ORIGINS: "http://127.0.0.1:3026", TRIP_CAPABILITY_COOKIE_SECURE: "false", LOG_LEVEL: "WARNING" },
      url: "http://127.0.0.1:8026/readiness", timeout: 120_000, reuseExistingServer: false,
    },
    {
      command: "npm run start -- --hostname 127.0.0.1 --port 3026",
      cwd: ".", env: { NEXT_TELEMETRY_DISABLED: "1", TRIP_API_PROXY_TARGET: "http://127.0.0.1:8026" },
      url: "http://127.0.0.1:3026/product-reset-live", timeout: 120_000, reuseExistingServer: false,
    },
  ],
});
