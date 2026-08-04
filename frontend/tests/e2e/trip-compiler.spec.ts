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
  return () => expect(errors, errors.join("\n")).toEqual([]);
}

function observeCandidateRequests(page: Page) {
  let count = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/trip-compiler/planning-runs")) count += 1;
  });
  return () => count;
}

test("Trip Compiler Scenario A: compares server candidates before saving one executable route", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const assertClean = installGate(page);
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
  expect((await planned).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "选一条更符合这次旅行的安排。" })).toBeVisible();
  await expect(page.getByRole("region", { name: "完整路线预览" })).toContainText("第 1 天");
  await page.getByRole("button", { name: "查看规划记录" }).click();
  await expect(page.getByRole("heading", { name: "这次规划" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "选一条更符合这次旅行的安排。" })).toBeVisible();
  await expect(page.getByRole("region", { name: "完整路线预览" })).toContainText("第 2 天");
  await expect(page.getByRole("button", { name: "确认并保存这条路线" })).toBeVisible();
  const selected = page.waitForResponse((response) => response.url().includes("/select") && response.request().method() === "POST");
  await page.getByRole("button", { name: "确认并保存这条路线" }).click();
  expect((await selected).status()).toBe(201);
  await expect(page.getByRole("heading", { name: /杭州 · 2 天/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "可执行路线预览" })).toBeVisible();
  await expect(page.getByText("必去", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("系统补充", { exact: false }).first()).toBeVisible();
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
  const alternatives = page.getByRole("button", { name: /保留更多想去地点|留出更多空白|少走一些路/ });
  if (await alternatives.count() > 1) {
    await alternatives.nth(1).click();
  }
  await page.reload();
  await expect(page.getByRole("region", { name: "完整路线预览" })).toContainText("第 2 天");
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  assertClean();
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
