import { expect, test, type Page } from "@playwright/test";

function installErrorGate(page: Page) {
  const errors: string[] = [];
  const backendRequests: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("request", (request) => {
    const url = request.url();
    if (url.includes("/api/") || url.includes(":8000") || url.includes(":8018")) {
      backendRequests.push(url);
    }
  });
  return () => {
    expect(errors).toEqual([]);
    expect(backendRequests).toEqual([]);
  };
}

async function openRoute(page: Page) {
  await page.goto("/product-reset-preview");
  await page.getByRole("button", { name: "看看我理解得对不对" }).click();
  await page.getByRole("button", { name: "生成我的路线" }).click();
}

test("Scenario A: Hangzhou reaches a readable two-day route on desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const assertNoErrors = installErrorGate(page);
  await openRoute(page);
  await expect(page.getByRole("heading", { name: "杭州，2 天。" })).toBeVisible();
  await expect(page.getByText("西湖 · 苏堤与花港")).toBeVisible();
  await expect(page.getByRole("heading", { name: "灵隐寺" })).toBeVisible();
  await expect(page.getByText("下一段预计 12 分钟 · 850 米")).toBeVisible();
  await expect(page.getByText("为什么这样安排").first()).toBeVisible();
  await expect(page.getByText("revision", { exact: false })).toHaveCount(0);
  expect(await page.evaluate(() => document.body.scrollWidth <= window.innerWidth)).toBe(true);
  assertNoErrors();
});

test("Scenario B: Shanghai keeps the museum appointment visibly protected", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const assertNoErrors = installErrorGate(page);
  await page.goto("/product-reset-preview");
  await page.getByRole("button", { name: "上海固定预约" }).click();
  await page.getByRole("button", { name: "看看我理解得对不对" }).click();
  await expect(page.getByLabel("固定安排")).toHaveValue(/上海博物馆 · 14:00–16:00/);
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await expect(page.getByText("上海博物馆").last()).toBeVisible();
  await expect(page.getByText("已预约 · 不可随意移动")).toBeVisible();
  assertNoErrors();
});

test("Scenario C: a local repair only moves the system suggestion on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const assertNoErrors = installErrorGate(page);
  await page.goto("/product-reset-preview");
  await page.getByRole("button", { name: "西安到达日太赶" }).click();
  await page.getByRole("button", { name: "看看我理解得对不对" }).click();
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await expect(page.getByText("第 1 天有 5 个活动，移动约 95 分钟，下午会比较赶。")).toBeVisible();
  await page.getByRole("button", { name: "让这一天轻松一些" }).click();
  const review = page.getByRole("region", { name: "调整前后对比" });
  await expect(review).toContainText("不重新生成整趟旅行");
  await expect(review).toContainText("兵马俑、西安城墙、城墙夜骑");
  await page.getByRole("button", { name: "应用这次调整" }).click();
  await expect(page.getByText("Prototype only — no TripRevision is persisted in this round.")).toBeVisible();
  await expect(page.getByText("第 1 天值得调整一下")).toHaveCount(0);
  expect(await page.evaluate(() => document.body.scrollWidth <= window.innerWidth)).toBe(true);
  assertNoErrors();
});
