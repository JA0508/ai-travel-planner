import { expect, test, type Page } from "@playwright/test";

function installErrorGate(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  page.on("requestfailed", (request) => { if (request.url().includes("/api/")) errors.push(`${request.url()}: ${request.failure()?.errorText}`); });
  return () => expect(errors).toEqual([]);
}

async function createAndSave(page: Page) {
  await page.goto("/product-reset-live");
  await page.getByRole("button", { name: "看看我理解得对不对" }).click();
  await expect(page.getByRole("heading", { name: "这次旅行，我这样理解。" })).toBeVisible();
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await expect(page.getByRole("region", { name: "可执行路线" })).toBeVisible();
}

test("live A: a real draft compiles, saves revision one, and renders route evidence", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const assertClean = installErrorGate(page);
  await createAndSave(page);
  await expect(page.getByText("DAY 1")).toBeVisible();
  await expect(page.getByText("顺路建议").first()).toBeVisible();
  await expect(page.getByText(/从 .* 出发/).first()).toBeVisible();
  expect(await page.evaluate(() => document.body.scrollWidth <= window.innerWidth)).toBe(true);
  assertClean();
});

test("live C: server-authored local repair shows before/after and saves revision two on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const assertClean = installErrorGate(page);
  await createAndSave(page);
  await page.getByRole("button", { name: "让这一天轻松一些" }).click();
  const review = page.getByRole("dialog", { name: "调整前后对比" });
  await expect(review).toContainText("固定安排和你明确想去的地点没有移动");
  await expect(review).toContainText("调整前");
  await page.getByRole("button", { name: "应用这次调整" }).click();
  await expect(page.getByText("已保存为新版本")).toBeVisible();
  expect(await page.evaluate(() => document.body.scrollWidth <= window.innerWidth)).toBe(true);
  assertClean();
});
