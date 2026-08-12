import { expect, test } from "@playwright/test";

const SIMPLE_TRIP = "去杭州玩两天，节奏轻松一点。";

function installNetworkGate(page: import("@playwright/test").Page) {
  const failures: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 500) failures.push(`${response.status()} ${response.url()}`);
  });
  page.on("pageerror", (error) => failures.push(error.message));
  return () => expect(failures, failures.join("\n")).toEqual([]);
}

test("Trip Compiler uses a Draft Intent revision before it creates a Planning Run", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await expect(page.getByRole("img", { name: "雨后上海街头的咖啡馆与自行车" })).toBeVisible();
  await page.getByLabel("这一趟，你已经知道些什么？").fill(SIMPLE_TRIP);
  const createdDraft = page.waitForResponse((response) => response.url().includes("/trips/drafts") && response.request().method() === "POST");
  const compiledIntent = page.waitForResponse((response) => response.url().includes("/preplan-intent/compile") && response.request().method() === "POST");
  await page.getByRole("button", { name: "开始编排行程" }).click();
  expect((await createdDraft).status()).toBe(201);
  expect((await compiledIntent).status()).toBe(201);
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  await expect(page.getByText("Draft", { exact: false })).toHaveCount(0);
  await expect(page.getByText("Revision", { exact: false })).toHaveCount(0);

  const createdRun = page.waitForResponse((response) => response.url().includes("/preplan-intent/planning-run") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成我的路线" }).click();
  expect((await createdRun).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "选一条更符合这次旅行的安排。" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  assertClean();
});

test("Trip Compiler keeps the Draft Intent to candidate flow usable on mobile", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(SIMPLE_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await expect(page.getByRole("heading", { name: "选一条更符合这次旅行的安排。" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  assertClean();
});
