import { expect, test, type Page, type Response } from "@playwright/test";

test("Import release gate completes available forms and fails closed for unavailable binary forms", async ({ page }) => {
  const errors = installBrowserErrorGate(page);
  const tripId = await createDraftWithImportWorkspace(page);
  const workspace = page.locator("[data-import-workspace]");
  const revisionsBefore = await listTripRevisions(page, tripId);

  await expect(workspace.locator("[data-import-capability-form=text]")).toContainText("Available");
  await expect(workspace.locator("[data-import-capability-form=url]")).toContainText("Available");
  await expect(workspace.locator("[data-import-capability-form=image]")).toContainText("Unavailable");
  await expect(workspace.locator("[data-import-capability-form=pdf]")).toContainText("Unavailable");
  await expect(workspace.getByText("Binary inspection is unavailable, so uploads cannot be accepted safely.")).toHaveCount(2);
  await expect(workspace.getByRole("button", { name: "Image / PDF" })).toBeDisabled();

  const textArtifact = page.waitForResponse((response) => response.url().includes("/imports/") && response.url().endsWith("/artifact"));
  const textImport = page.waitForResponse((response) => isImportResponse(response, "/imports/text"));
  await workspace.getByPlaceholder("Paste a guide, note, or group-chat excerpt.").fill("景点：豫园");
  await workspace.getByRole("button", { name: "Import text" }).click();
  expect((await textImport).status()).toBe(201);
  await expectPrivateTextResponse(await textArtifact);
  await confirmAndCommit(workspace, page);

  await workspace.getByRole("button", { name: "URL" }).click();
  const urlArtifact = page.waitForResponse((response) => response.url().includes("/imports/") && response.url().endsWith("/artifact"));
  const urlImport = page.waitForResponse((response) => isImportResponse(response, "/imports/url"));
  await workspace.getByPlaceholder("https://example.com/travel-guide").fill("https://fixture.invalid/guide");
  await workspace.getByRole("button", { name: "Import URL" }).click();
  expect((await urlImport).status()).toBe(201);
  await expectPrivateTextResponse(await urlArtifact);
  await expect(workspace.locator("[data-url-provenance]")).toContainText("allowed");
  await expect(workspace.locator("pre")).not.toContainText("<html");
  await confirmAndCommit(workspace, page);

  await expect(workspace).not.toContainText("%PDF");
  expect(await listTripRevisions(page, tripId)).toEqual(revisionsBefore);
  errors.assertClean();
});

async function createDraftWithImportWorkspace(page: Page): Promise<string> {
  await page.addInitScript(() => window.localStorage.clear());
  await page.goto("/");
  await page.getByLabel("旅行需求").fill("去上海玩一天，想看历史文化。");
  const created = page.waitForResponse((response) => response.url().includes("/api/trips/drafts") && response.request().method() === "POST");
  await page.getByRole("button", { name: /生成旅行骨架/ }).click();
  const response = await created;
  expect(response.status()).toBe(201);
  const tripId = (await response.json() as { trip: { id: string } }).trip.id;
  await expect(page.getByRole("heading", { name: "确认行程信息" })).toBeVisible();
  const sourceDetails = page.locator("details.uc-intent-details").filter({ hasText: "查看依据" });
  await expect(sourceDetails).toBeVisible();
  await sourceDetails.locator(":scope > summary").click();
  await page.getByText("添加或审核导入资料", { exact: true }).click();
  await expect(page.locator("[data-import-workspace]")).toBeVisible();
  return tripId;
}

async function confirmAndCommit(workspace: ReturnType<Page["locator"]>, page: Page) {
  const confirm = workspace.getByText("Confirm", { exact: true }).first();
  await expect(confirm).toBeVisible();
  const decision = page.waitForResponse((response) => response.url().includes("/decisions") && response.request().method() === "POST");
  await confirm.click();
  expect((await decision).status()).toBe(200);
  const commit = page.waitForResponse((response) => response.url().endsWith("/commit") && response.request().method() === "POST");
  await workspace.getByRole("button", { name: "Add confirmed places to candidate pool" }).click();
  expect((await commit).status()).toBe(200);
  await expect(workspace.getByText(/Added \d+ new candidate\(s\), reused \d+\./)).toBeVisible();
}

async function listTripRevisions(page: Page, tripId: string) {
  const response = await page.request.get(`/api/trips/${tripId}/revisions`);
  expect(response.status()).toBe(200);
  return (await response.json() as { revisions: Array<{ id: string }> }).revisions;
}

function isImportResponse(response: Response, suffix: string) {
  return response.url().includes(suffix) && response.request().method() === "POST";
}

async function expectPrivateTextResponse(response: Response) {
  expect(response.status()).toBe(200);
  expect(response.headers()["cache-control"]).toContain("private");
  expect(response.headers()["cache-control"]).toContain("no-store");
  expect(response.headers()["x-content-type-options"]).toBe("nosniff");
}

function installBrowserErrorGate(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    const expectedInitialIntentAbsence = message.text().includes("status of 422");
    if (message.type() === "error" && !expectedInitialIntentAbsence) errors.push(`console.error: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("requestfailed", (request) => {
    if (request.url().includes("/api/")) errors.push(`failed API request: ${request.url()} ${request.failure()?.errorText ?? "unknown"}`);
  });
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 500) errors.push(`API ${response.status()}: ${response.url()}`);
  });
  return { assertClean: () => expect(errors, errors.join("\n")).toEqual([]) };
}
