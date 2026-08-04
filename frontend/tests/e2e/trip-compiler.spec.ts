import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

const hangzhou = "周末去杭州玩两天，想去西湖和灵隐寺。朋友推荐龙井村，但不是必须。周六下午两点预约了中国茶叶博物馆。不想太赶，想吃本地小吃。周日晚上六点前要到杭州东站。";

function installGate(page: Page) {
  const errors: string[] = [];
  page.on("console", (message: { type(): string; text(): string }) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error: Error) => errors.push(error.message));
  page.on("requestfailed", (request: { url(): string; failure(): { errorText?: string } | null }) => {
    if (request.url().includes("/api/")) errors.push(`${request.url()} ${request.failure()?.errorText ?? "failed"}`);
  });
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 500) errors.push(`API ${response.status()}: ${response.url()}`);
  });
  return () => expect(errors, errors.join("\n")).toEqual([]);
}

function observeCandidateRequests(page: Page) {
  let count = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/trip-compiler/planning-runs")) count += 1;
  });
  return () => count;
}

function planningRunScreenshot(name: string): string {
  const runtimeDirectory = process.env.TRIP_COMPILER_E2E_RUNTIME_DIR;
  if (!runtimeDirectory) throw new Error("TRIP_COMPILER_E2E_RUNTIME_DIR is required for Planning Run screenshots.");
  return join(runtimeDirectory, name);
}

function tripCount(): number {
  const databasePath = process.env.TRIP_COMPILER_E2E_DATABASE_PATH;
  if (!databasePath) throw new Error("TRIP_COMPILER_E2E_DATABASE_PATH is required for SQLite assertions.");
  const program = "import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute('SELECT COUNT(*) FROM trips').fetchone()[0])";
  return Number(execFileSync(process.env.TRIP_E2E_PYTHON ?? ".venv/bin/python", ["-c", program, databasePath], {
    cwd: resolve(process.cwd(), "../backend"),
    encoding: "utf8",
  }).trim());
}

function expirePlanningRun(runId: string): void {
  const databasePath = process.env.TRIP_COMPILER_E2E_DATABASE_PATH;
  if (!databasePath) throw new Error("TRIP_COMPILER_E2E_DATABASE_PATH is required for SQLite assertions.");
  const program = "import sqlite3, sys; connection = sqlite3.connect(sys.argv[1]); connection.execute(\"UPDATE planning_runs SET status = 'expired' WHERE id = ?\", (sys.argv[2],)); connection.commit()";
  execFileSync(process.env.TRIP_E2E_PYTHON ?? ".venv/bin/python", ["-c", program, databasePath, runId], {
    cwd: resolve(process.cwd(), "../backend"),
    encoding: "utf8",
  });
}

function candidateSignature(body: { candidates: Array<{ id: string; candidate_hash: string }> }): Array<[string, string]> {
  return body.candidates.map((candidate) => [candidate.id, candidate.candidate_hash]);
}

async function availablePort(): Promise<number> {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("Unable to allocate a port."));
        return;
      }
      server.close((error) => error ? reject(error) : resolvePort(address.port));
    });
  });
}

async function waitForUrl(url: string): Promise<void> {
  const deadline = Date.now() + 20_000;
  let lastError: unknown;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = new Error(`${url} returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 100));
  }
  throw lastError ?? new Error(`Timed out waiting for ${url}`);
}

async function stopProcess(process: ChildProcess | undefined): Promise<void> {
  if (!process || process.exitCode !== null) return;
  process.kill("SIGTERM");
  await new Promise<void>((resolveExit) => {
    const timeout = setTimeout(() => {
      if (process.exitCode === null) process.kill("SIGKILL");
    }, 5_000);
    process.once("exit", () => {
      clearTimeout(timeout);
      resolveExit();
    });
  });
}

function startBackend(port: number, databasePath: string, allowedOrigin: string): ChildProcess {
  return spawn(process.env.TRIP_E2E_PYTHON ?? ".venv/bin/python", ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port)], {
    cwd: resolve(process.cwd(), "../backend"),
    env: {
      ...process.env,
      APP_ENV: "development",
      AMAP_API_KEY: "",
      OPENAI_API_KEY: "",
      POI_DISCOVERY_MODE: "fallback",
      CORS_ALLOW_ORIGINS: allowedOrigin,
      TRIP_ALLOWED_ORIGINS: allowedOrigin,
      TRIP_CAPABILITY_COOKIE_SECURE: "false",
      TRIP_STORE_MODE: "sqlite",
      TRIP_STORE_PATH: databasePath,
      IMPORT_ARTIFACT_ROOT: `${databasePath}.artifacts`,
      IMPORT_URL_ENABLED: "false",
      LOG_LEVEL: "WARNING",
    },
    stdio: "ignore",
  });
}

function startNext(port: number, apiPort: number): ChildProcess {
  return spawn(resolve(process.cwd(), "node_modules/.bin/next"), ["start", "--hostname", "127.0.0.1", "--port", String(port)], {
    cwd: process.cwd(),
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1", TRIP_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}` },
    stdio: "ignore",
  });
}

test("Trip Compiler Scenario A: compares server candidates before saving one executable route", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const assertClean = installGate(page);
  const planRequestCount = observeCandidateRequests(page);
  await page.goto("/trip-compiler");
  await page.getByLabel("这趟旅行，你已经知道些什么？").fill(hangzhou);
  const compiled = page.waitForResponse((response) => response.url().includes("/trip-compiler/intents/compile"));
  await page.getByRole("button", { name: "整理我的旅行想法" }).click();
  expect((await compiled).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "这些是我从你的旅行想法里理解到的。" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "必去" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "想去，但可以调整" })).toBeVisible();
  await expect(page.getByText("西湖", { exact: true })).toBeVisible();
  await expect(page.getByText("龙井村", { exact: true })).toBeVisible();
  await expect(page.getByText("中国茶叶博物馆", { exact: true })).toBeVisible();
  const planned = page.waitForResponse((response) => response.url().includes("/trip-compiler/planning-runs") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成我的行程骨架" }).click();
  const generatedResponse = await planned;
  expect(generatedResponse.status()).toBe(200);
  const generated = await generatedResponse.json() as { planning_run_id: string; candidates: Array<{ id: string; candidate_hash: string }> };
  const generatedCandidates = candidateSignature(generated);
  expect(tripCount()).toBe(0);
  await expect(page.getByRole("heading", { name: "选一条更符合这次旅行的安排。" })).toBeVisible();
  await expect(page.getByRole("region", { name: "完整路线预览" })).toContainText("第 1 天");
  await expect.poll(() => page.locator(".tc-candidate-page .tc-confirm-footer").evaluate((element) => getComputedStyle(element).position)).toBe("static");
  await page.getByRole("button", { name: "查看规划记录" }).click();
  await expect(page.getByRole("heading", { name: "这次规划" })).toBeVisible();
  const requestCountBeforeRefresh = planRequestCount();
  const restoredResponse = page.waitForResponse((response) => response.url().includes(`/planning-runs/${generated.planning_run_id}`) && response.request().method() === "GET");
  await page.reload();
  const restored = await restoredResponse;
  expect(candidateSignature(await restored.json() as { candidates: Array<{ id: string; candidate_hash: string }> })).toEqual(generatedCandidates);
  expect(planRequestCount()).toBe(requestCountBeforeRefresh);
  expect(tripCount()).toBe(0);
  await expect(page.getByRole("heading", { name: "选一条更符合这次旅行的安排。" })).toBeVisible();
  await expect(page.getByRole("region", { name: "完整路线预览" })).toContainText("第 2 天");
  await expect(page.getByRole("button", { name: "确认并保存这条路线" })).toBeVisible();
  await page.screenshot({ path: planningRunScreenshot("desktop-restored.png"), fullPage: true });
  const selected = page.waitForResponse((response) => response.url().includes("/select") && response.request().method() === "POST");
  await page.getByRole("button", { name: "确认并保存这条路线" }).click();
  expect((await selected).status()).toBe(201);
  await expect(page.getByRole("heading", { name: /杭州 · 2 天/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "可执行路线预览" })).toBeVisible();
  await expect(page.getByText("必去", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("系统补充", { exact: false }).first()).toBeVisible();
  await page.goto(`/trip-compiler?planning_run=${encodeURIComponent(generated.planning_run_id)}`);
  await expect(page.getByRole("heading", { name: "这套路线已经保存。" })).toBeVisible();
  await expect(page.getByRole("button", { name: "打开已保存行程" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "确认并保存这条路线" })).toHaveCount(0);
  await page.screenshot({ path: planningRunScreenshot("desktop-selected.png"), fullPage: true });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  assertClean();
});

test("Trip Compiler Scenario E: mobile restores a persisted candidate comparison without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const assertClean = installGate(page);
  await page.goto("/trip-compiler");
  await page.getByLabel("这趟旅行，你已经知道些什么？").fill(hangzhou);
  await page.getByRole("button", { name: "整理我的旅行想法" }).click();
  await page.getByRole("button", { name: "生成我的行程骨架" }).click();
  await expect(page.getByRole("region", { name: "完整路线预览" })).toContainText("第 1 天");
  await expect.poll(() => page.locator(".tc-candidate-page .tc-confirm-footer").evaluate((element) => getComputedStyle(element).position)).toBe("static");
  await page.screenshot({ path: planningRunScreenshot("mobile-route.png"), fullPage: true });
  const alternatives = page.getByRole("button", { name: /保留更多想去地点|留出更多空白|少走一些路/ });
  if (await alternatives.count() > 1) {
    await alternatives.nth(1).click();
  }
  await page.reload();
  await expect(page.getByRole("region", { name: "完整路线预览" })).toContainText("第 2 天");
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  assertClean();
});

test("Trip Compiler Scenario F: expired and saved planning states have one clear desktop action", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const assertClean = installGate(page);
  await page.goto("/trip-compiler");
  await page.getByLabel("这趟旅行，你已经知道些什么？").fill(hangzhou);
  await page.getByRole("button", { name: "整理我的旅行想法" }).click();
  const created = page.waitForResponse((response) => response.url().includes("/trip-compiler/planning-runs") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成我的行程骨架" }).click();
  const run = await (await created).json() as { planning_run_id: string };
  expirePlanningRun(run.planning_run_id);
  await page.reload();
  await expect(page.getByRole("heading", { name: "这批路线方案已经过期。" })).toBeVisible();
  await expect(page.getByText("为了避免使用旧数据，请重新生成。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新生成路线方案" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "确认并保存这条路线" })).toHaveCount(0);
  await page.screenshot({ path: planningRunScreenshot("desktop-expired.png"), fullPage: true });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  assertClean();
});

test("Trip Compiler Scenario G: mobile recovery keeps route, expired, and saved states usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const assertClean = installGate(page);
  await page.goto("/trip-compiler");
  await page.getByLabel("这趟旅行，你已经知道些什么？").fill(hangzhou);
  await page.getByRole("button", { name: "整理我的旅行想法" }).click();
  const created = page.waitForResponse((response) => response.url().includes("/trip-compiler/planning-runs") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成我的行程骨架" }).click();
  const run = await (await created).json() as { planning_run_id: string };
  await expect(page.getByRole("region", { name: "完整路线预览" })).toContainText("第 1 天");
  const selected = page.waitForResponse((response) => response.url().includes("/select") && response.request().method() === "POST");
  await page.getByRole("button", { name: "确认并保存这条路线" }).click();
  expect((await selected).status()).toBe(201);
  await page.goto(`/trip-compiler?planning_run=${encodeURIComponent(run.planning_run_id)}`);
  await expect(page.getByRole("heading", { name: "这套路线已经保存。" })).toBeVisible();
  await expect(page.getByRole("button", { name: "打开已保存行程" })).toHaveCount(1);
  await page.screenshot({ path: planningRunScreenshot("mobile-selected.png"), fullPage: true });
  await page.goto("/trip-compiler");
  await page.getByLabel("这趟旅行，你已经知道些什么？").fill(hangzhou);
  await page.getByRole("button", { name: "整理我的旅行想法" }).click();
  const expiringRun = page.waitForResponse((response) => response.url().includes("/trip-compiler/planning-runs") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成我的行程骨架" }).click();
  const expired = await (await expiringRun).json() as { planning_run_id: string };
  expirePlanningRun(expired.planning_run_id);
  await page.reload();
  await expect(page.getByRole("heading", { name: "这批路线方案已经过期。" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新生成路线方案" })).toHaveCount(1);
  await page.screenshot({ path: planningRunScreenshot("mobile-expired.png"), fullPage: true });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  assertClean();
});

test("Trip Compiler Scenario H: Chromium restores one candidate set after a real FastAPI restart", async ({ page }) => {
  test.setTimeout(90_000);
  const assertClean = installGate(page);
  const runtimeDirectory = mkdtempSync(join(tmpdir(), "trip-compiler-restart-e2e-"));
  const databasePath = join(runtimeDirectory, "restart.sqlite3");
  const apiPort = await availablePort();
  const webPort = await availablePort();
  const allowedOrigin = `http://127.0.0.1:${webPort}`;
  let backend = startBackend(apiPort, databasePath, allowedOrigin);
  let web: ChildProcess | undefined;
  try {
    await waitForUrl(`http://127.0.0.1:${apiPort}/readiness`);
    web = startNext(webPort, apiPort);
    await waitForUrl(`http://127.0.0.1:${webPort}/trip-compiler`);
    await page.goto(`http://127.0.0.1:${webPort}/trip-compiler`);
    await page.getByLabel("这趟旅行，你已经知道些什么？").fill(hangzhou);
    await page.getByRole("button", { name: "整理我的旅行想法" }).click();
    const created = page.waitForResponse((response) => response.url().includes("/trip-compiler/planning-runs") && response.request().method() === "POST");
    await page.getByRole("button", { name: "生成我的行程骨架" }).click();
    const initial = await (await created).json() as { planning_run_id: string; candidates: Array<{ id: string; candidate_hash: string }> };
    await stopProcess(backend);
    backend = startBackend(apiPort, databasePath, allowedOrigin);
    await waitForUrl(`http://127.0.0.1:${apiPort}/readiness`);
    const restored = page.waitForResponse((response) => response.url().includes(`/planning-runs/${initial.planning_run_id}`) && response.request().method() === "GET");
    await page.reload();
    expect(candidateSignature(await (await restored).json() as { candidates: Array<{ id: string; candidate_hash: string }> })).toEqual(candidateSignature(initial));
    await expect(page.getByRole("heading", { name: "选一条更符合这次旅行的安排。" })).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    assertClean();
  } finally {
    await stopProcess(web);
    await stopProcess(backend);
    rmSync(runtimeDirectory, { recursive: true, force: true });
  }
});

test("Trip Compiler Scenario B: missing travel length stays visible instead of silently planning", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const assertClean = installGate(page);
  const planRequestCount = observeCandidateRequests(page);
  await page.goto("/trip-compiler");
  await page.getByLabel("这趟旅行，你已经知道些什么？").fill("周末想去苏州，想看看园林，别太累。");
  await page.getByRole("button", { name: "整理我的旅行想法" }).click();
  await expect(page.getByRole("heading", { name: "还需要你确认" })).toBeVisible();
  await expect(page.getByText("准备玩几天？")).toBeVisible();
  await expect(page.getByRole("button", { name: "生成我的行程骨架" })).toBeDisabled();
  expect(planRequestCount()).toBe(0);

  await page.goto("/trip-compiler");
  await page.getByLabel("这趟旅行，你已经知道些什么？").fill("去杭州玩四天，想去西湖和灵隐寺，节奏轻松一些。");
  const overLimitCompile = page.waitForResponse((response) => response.url().includes("/trip-compiler/intents/compile"));
  await page.getByRole("button", { name: "整理我的旅行想法" }).click();
  expect((await overLimitCompile).status()).toBe(200);
  await expect(page.getByText("当前版本先支持 1 到 3 天的行程，请调整旅行天数后再继续。")).toBeVisible();
  await expect(page.getByRole("button", { name: "生成我的行程骨架" })).toBeDisabled();
  expect(planRequestCount()).toBe(0);
  assertClean();
});

test("Trip Compiler Scenario C: an arrival-after-reservation conflict never creates a route", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const assertClean = installGate(page);
  const planRequestCount = observeCandidateRequests(page);
  await page.goto("/trip-compiler");
  await page.getByLabel("这趟旅行，你已经知道些什么？").fill("下午三点到上海，下午两点到四点预约了上海博物馆。");
  await page.getByRole("button", { name: "整理我的旅行想法" }).click();
  await expect(page.locator(".tc-conflict[role=alert]")).toContainText("当前安排存在冲突");
  await expect(page.getByText("第 1 天到达时间晚于固定安排“上海博物馆”的开始时间，无法同时满足。")).toBeVisible();
  await expect(page.getByRole("region", { name: "可执行路线预览" })).toHaveCount(0);
  expect(planRequestCount()).toBe(0);
  assertClean();
});

test("Trip Compiler Scenario D: a rushed day receives one server-authoritative local repair", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const assertClean = installGate(page);
  await page.goto("/trip-compiler");
  await page.getByLabel("这趟旅行，你已经知道些什么？").fill(hangzhou);
  await page.getByRole("button", { name: "整理我的旅行想法" }).click();
  await page.getByRole("button", { name: "生成我的行程骨架" }).click();
  await page.getByRole("button", { name: "确认并保存这条路线" }).click();
  await expect(page.getByRole("region", { name: "可执行路线预览" })).toBeVisible();

  const previewed = page.waitForResponse((response) => response.url().includes("/local-repairs/relax-day/preview"));
  await page.getByRole("button", { name: "让这一天轻松一些" }).first().click();
  const preview = await previewed;
  expect(preview.status()).toBe(200);
  const previewBody = preview.request().postDataJSON() as Record<string, unknown>;
  expect(previewBody).toMatchObject({ target_day: 1, goal: "relax_day" });
  expect(JSON.stringify(previewBody)).not.toMatch(/move_stop|stable_id|to_day/);
  await expect(page.getByRole("dialog", { name: "调整预览" })).toBeVisible();
  await expect(page.getByText("固定安排没有移动；你明确想去的地点没有删除；没有重新生成全部行程。")).toBeVisible();

  const applied = page.waitForResponse((response) => response.url().includes("/mutation-proposals/") && response.url().endsWith("/apply"));
  await page.getByRole("button", { name: "应用这次调整" }).click();
  expect((await applied).status()).toBe(200);
  await expect(page.getByRole("dialog", { name: "调整预览" })).toHaveCount(0);
  assertClean();
});
