import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const VISUAL_TRIP = "去杭州玩三天，节奏轻松一点，想去西湖、灵隐寺和龙井村。第二天下午两点到四点预约了中国茶叶博物馆，不能改。";
const SCREENSHOT_DIRECTORY = join(process.cwd(), "test-results", "round-ui-01");
const ROADBOOK_SCREENSHOT_DIRECTORY = join(process.cwd(), "test-results", "round-ui-02");

mkdirSync(SCREENSHOT_DIRECTORY, { recursive: true });
mkdirSync(ROADBOOK_SCREENSHOT_DIRECTORY, { recursive: true });

function installNetworkGate(page: import("@playwright/test").Page) {
  const failures: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 500) failures.push(`${response.status()} ${response.url()}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(`console.error: ${message.text()}`);
  });
  page.on("pageerror", (error) => failures.push(error.message));
  return () => expect(failures, failures.join("\n")).toEqual([]);
}

async function confirmVisiblePlaces(page: import("@playwright/test").Page) {
  const choices = page.locator(".tc-place-options button");
  while (await choices.count()) {
    const confirmed = page.waitForResponse((response) => response.url().includes("/preplan-intent/edits") && response.request().method() === "POST");
    await choices.first().click();
    expect((await confirmed).status()).toBe(201);
  }
  await expect(page.getByRole("button", { name: "生成我的路线" })).toBeEnabled();
}

async function verifyFixedArrangementProtection(page: import("@playwright/test").Page) {
  const dayButtons = page.locator(".roadbook__masthead nav button");
  expect(await dayButtons.count()).toBeGreaterThan(1);
  await dayButtons.nth(1).click();
  await expect(page.getByText("不会被随意移动")).toBeVisible();
  await expect(page.getByText("LOCKED")).toBeVisible();
  await dayButtons.first().click();
}

async function verifyMapEvidenceSettled(page: import("@playwright/test").Page) {
  await expect.poll(async () => {
    const markers = await page.locator(".amap-marker").count();
    const honestFallback = await page.getByText("地图暂未启用").count();
    return markers > 0 || honestFallback > 0;
  }).toBe(true);
}

test("Trip Compiler uses a Draft Intent revision before it creates a Planning Run", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await expect(page.getByRole("img", { name: "雨后上海街头的咖啡馆与自行车" })).toBeVisible();
  await page.screenshot({ path: join(SCREENSHOT_DIRECTORY, "desktop-home.png") });
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  const createdDraft = page.waitForResponse((response) => response.url().includes("/trips/drafts") && response.request().method() === "POST");
  const compiledIntent = page.waitForResponse((response) => response.url().includes("/preplan-intent/compile") && response.request().method() === "POST");
  await page.getByRole("button", { name: "开始编排行程" }).click();
  expect((await createdDraft).status()).toBe(201);
  expect((await compiledIntent).status()).toBe(201);
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  await expect(page.getByText("Draft", { exact: false })).toHaveCount(0);
  await expect(page.getByText("Revision", { exact: false })).toHaveCount(0);
  await page.screenshot({ path: join(SCREENSHOT_DIRECTORY, "desktop-confirm-intent.png") });
  await confirmVisiblePlaces(page);

  const createdRun = page.waitForResponse((response) => response.url().includes("/preplan-intent/planning-run") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成我的路线" }).click();
  expect((await createdRun).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "路线怎么不同，一眼就能看懂。" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(SCREENSHOT_DIRECTORY, "desktop-route-preview.png") });

  const selectedRoute = page.waitForResponse((response) => response.url().includes("/select") && response.request().method() === "POST");
  await page.getByRole("button", { name: "就选这条路线" }).click();
  expect((await selectedRoute).status()).toBe(201);
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  await expect(page.locator('[data-roadbook-layout="living"]')).toBeVisible();
  await expect(page.locator('[data-route-map-pane="true"]')).toBeVisible();
  await expect(page.getByRole("button", { name: /帮我松一点/ })).toBeVisible();
  await verifyFixedArrangementProtection(page);
  await verifyMapEvidenceSettled(page);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(ROADBOOK_SCREENSHOT_DIRECTORY, "desktop-roadbook.png") });
  const desktopStops = page.locator("[data-roadbook-stop]");
  expect(await desktopStops.count()).toBeGreaterThan(1);
  await desktopStops.nth(1).click();
  await expect(desktopStops.nth(1)).toHaveAttribute("aria-pressed", "true");
  const desktopDetail = page.locator("[data-roadbook-selected-place]");
  await expect(desktopDetail).toBeVisible();
  await desktopDetail.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(ROADBOOK_SCREENSHOT_DIRECTORY, "desktop-roadbook-selected-place.png") });
  await desktopDetail.getByRole("button", { name: /查看下一站/ }).click();
  await expect(desktopStops.nth(2)).toHaveAttribute("aria-pressed", "true");
  assertClean();
});

test("Trip Compiler keeps the Draft Intent to candidate flow usable on mobile", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/trip-compiler");
  await page.screenshot({ path: join(SCREENSHOT_DIRECTORY, "mobile-home.png") });
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  await page.screenshot({ path: join(SCREENSHOT_DIRECTORY, "mobile-confirm-intent.png") });
  await confirmVisiblePlaces(page);
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await expect(page.getByRole("heading", { name: "路线怎么不同，一眼就能看懂。" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(SCREENSHOT_DIRECTORY, "mobile-route-preview.png") });

  const selectedRoute = page.waitForResponse((response) => response.url().includes("/select") && response.request().method() === "POST");
  await page.getByRole("button", { name: "就选这条路线" }).click();
  expect((await selectedRoute).status()).toBe(201);
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  await expect(page.locator('[data-roadbook-layout="living"]')).toBeVisible();
  await expect(page.locator('[data-route-map-pane="true"]')).toBeVisible();
  await expect(page.getByRole("button", { name: /帮我松一点/ })).toBeVisible();
  await verifyFixedArrangementProtection(page);
  await verifyMapEvidenceSettled(page);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(ROADBOOK_SCREENSHOT_DIRECTORY, "mobile-roadbook.png") });
  const mobileStops = page.locator("[data-roadbook-stop]");
  expect(await mobileStops.count()).toBeGreaterThan(1);
  await mobileStops.nth(1).click();
  await expect(mobileStops.nth(1)).toHaveAttribute("aria-pressed", "true");
  const mobileDetail = page.locator("[data-roadbook-selected-place]");
  await expect(mobileDetail).toBeVisible();
  await mobileDetail.scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(ROADBOOK_SCREENSHOT_DIRECTORY, "mobile-roadbook-selected-place.png") });
  await mobileDetail.getByRole("button", { name: /查看下一站/ }).click();
  await expect(mobileStops.nth(2)).toHaveAttribute("aria-pressed", "true");
  assertClean();
});
