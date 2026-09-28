import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { shouldDisplayTravelLeg } from "../../src/features/executable-route-preview/routePreviewModel";
import type { PlanCandidateResponse } from "../../src/features/trip-compiler/PlanCandidateComparison";

const VISUAL_TRIP = "去杭州玩三天，节奏轻松一点，想去西湖、灵隐寺和龙井村。第二天下午两点到四点预约了中国茶叶博物馆，不能改。";
const MEAL_GAP_TRIP = "去杭州玩两天，节奏轻松一点，想去西湖、灵隐寺和龙井村。第一天下午一点到三点预约了中国茶叶博物馆，不能改。";
const SCREENSHOT_DIRECTORY = join(process.cwd(), "test-results", "round-ui-01");
const ROADBOOK_SCREENSHOT_DIRECTORY = join(process.cwd(), "test-results", "round-ui-02");
const REPAIR_SCREENSHOT_DIRECTORY = join(process.cwd(), "test-results", "round-27");
const REPLACE_SCREENSHOT_DIRECTORY = join(process.cwd(), "test-results", "round-28");
const REPLACE_QUALITY_SCREENSHOT_DIRECTORY = join(process.cwd(), "test-results", "round-28-1");
const MEAL_SCREENSHOT_DIRECTORY = join(process.cwd(), "test-results", "round-29");

mkdirSync(SCREENSHOT_DIRECTORY, { recursive: true });
mkdirSync(ROADBOOK_SCREENSHOT_DIRECTORY, { recursive: true });
mkdirSync(REPAIR_SCREENSHOT_DIRECTORY, { recursive: true });
mkdirSync(REPLACE_SCREENSHOT_DIRECTORY, { recursive: true });
mkdirSync(REPLACE_QUALITY_SCREENSHOT_DIRECTORY, { recursive: true });
mkdirSync(MEAL_SCREENSHOT_DIRECTORY, { recursive: true });

type SavedRoadbookPayload = {
  trip: { id: string };
  current_revision: { id: string; revision_number: number };
  itinerary: import("../../src/features/executable-route-preview/routePreviewModel").RoutePreviewItinerary;
};

function installNetworkGate(
  page: import("@playwright/test").Page,
  options: { ignoreConsoleError?: (message: string) => boolean } = {},
) {
  const failures: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 500) failures.push(`${response.status()} ${response.url()}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error" && !options.ignoreConsoleError?.(message.text())) failures.push(`console.error: ${message.text()}`);
  });
  page.on("pageerror", (error) => failures.push(error.message));
  return () => expect(failures, failures.join("\n")).toEqual([]);
}

function isExpectedStaleConflictConsole(message: string) {
  return message === "Failed to load resource: the server responded with a status of 409 (Conflict)";
}

async function confirmVisiblePlaces(page: import("@playwright/test").Page) {
  const choices = page.locator(".tc-place-options button");
  await expect(choices.first()).toBeVisible();
  while (await choices.count()) {
    const choiceCount = await choices.count();
    const choice = choices.first();
    const confirmed = page.waitForResponse((response) => response.url().includes("/preplan-intent/edits") && response.request().method() === "POST");
    await choice.click();
    await expect(page.locator(".tc-confirm-page")).toBeHidden();
    expect((await confirmed).status()).toBe(201);
    await expect(page.locator(".tc-confirm-page")).toBeVisible();
    expect(await choices.count()).toBeLessThan(choiceCount);
    if (await choices.count()) {
      await expect(choices.first()).toBeFocused();
    } else {
      await expect(page.getByRole("button", { name: "生成我的路线" })).toBeFocused();
    }
  }
  await expect(page.getByRole("button", { name: "生成我的路线" })).toBeEnabled();
}

test("Retrying a lost place confirmation replays the same verified place", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();

  const confirmationPattern = "**/api/trips/*/preplan-intent/edits";
  const idempotencyKeys: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/preplan-intent/") && request.url().endsWith("/edits")) {
      idempotencyKeys.push(request.headers()["x-idempotency-key"] ?? "");
    }
  });
  let dropFirstResponse = true;
  await page.route(confirmationPattern, async (route) => {
    if (!dropFirstResponse) {
      await route.continue();
      return;
    }
    dropFirstResponse = false;
    await route.fetch();
    await route.abort("connectionreset");
  });

  await page.locator(".tc-place-options button").first().click();
  await expect(page.getByText("暂时无法确认这次地点选择是否已保存。可重试这个地点；系统会核对这次确认，不会重复更新旅行信息。")).toBeVisible();
  await expect(page.locator(".tc-place-options button").first()).toBeDisabled();

  const replayResponse = page.waitForResponse((response) => (
    response.url().includes("/preplan-intent/")
    && response.url().endsWith("/edits")
    && response.request().method() === "POST"
    && idempotencyKeys.length === 2
  ));
  await page.getByRole("button", { name: /重试确认/ }).click();
  const replay = await replayResponse;
  expect(replay.status()).toBe(201);
  expect((await replay.json() as { idempotent_replay: boolean }).idempotent_replay).toBe(true);
  expect(idempotencyKeys).toHaveLength(2);
  expect([...new Set(idempotencyKeys)]).toEqual([idempotencyKeys[0]]);
  await expect(page.getByText("地点已确认。")).toBeVisible();
});

test("A rejected place confirmation does not claim that the result is unknown", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  await page.route("**/api/trips/*/preplan-intent/edits", (route) => route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: "这个地点暂时不能确认。" }),
  }));

  await page.locator(".tc-place-options button").first().click();

  await expect(page.getByText("这个地点暂时不能确认。")).toBeVisible();
  await expect(page.getByRole("button", { name: /重试确认/ })).toHaveCount(0);
  await expect(page.getByText("暂时无法确认这次地点选择是否已保存。可重试这个地点；系统会核对这次确认，不会重复更新旅行信息。")).toHaveCount(0);
});

test("A failed place-confirmation response keeps the safe idempotent retry", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  await page.route("**/api/trips/*/preplan-intent/edits", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "服务暂时不可用。" }),
  }));

  await page.locator(".tc-place-options button").first().click();

  await expect(page.getByText("暂时无法确认这次地点选择是否已保存。可重试这个地点；系统会核对这次确认，不会重复更新旅行信息。")).toBeVisible();
  await expect(page.getByRole("button", { name: /重试确认/ })).toBeVisible();
});

test("Reloading after a lost place confirmation restores the latest verified place", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  await expect(page).toHaveURL(/\/trip-compiler\?draft=/);

  let confirmationRequests = 0;
  let dropFirstResponse = true;
  await page.route("**/api/trips/*/preplan-intent/edits", async (route) => {
    confirmationRequests += 1;
    if (!dropFirstResponse) {
      await route.continue();
      return;
    }
    dropFirstResponse = false;
    await route.fetch();
    await route.abort("connectionreset");
  });

  await page.locator(".tc-place-options button").first().click();
  await expect(page.getByText("暂时无法确认这次地点选择是否已保存。可重试这个地点；系统会核对这次确认，不会重复更新旅行信息。")).toBeVisible();

  await page.reload();

  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  await expect(page.getByText("已确认")).toBeVisible();
  await expect(page.getByText("暂时无法确认这次地点选择是否已保存。可重试这个地点；系统会核对这次确认，不会重复更新旅行信息。")).toBeHidden();
  expect(confirmationRequests).toBe(1);
});

test("Starting a new idea clears the recoverable draft link", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  await expect(page).toHaveURL(/\/trip-compiler\?draft=/);

  await page.getByRole("button", { name: /重新描述/ }).click();

  await expect(page.getByLabel("这一趟，你已经知道些什么？")).toBeVisible();
  await expect(page).toHaveURL(/\/trip-compiler$/);
});

test("Retrying a lost draft compilation replays the same confirmation", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  const idempotencyKeys: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/preplan-intent/compile")) {
      idempotencyKeys.push(request.headers()["x-idempotency-key"] ?? "");
    }
  });
  let dropFirstResponse = true;
  await page.route("**/api/trips/*/preplan-intent/compile", async (route) => {
    if (!dropFirstResponse) {
      await route.continue();
      return;
    }
    dropFirstResponse = false;
    await route.fetch();
    await route.abort("connectionreset");
  });

  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();

  await expect(page.getByText("暂时无法确认这次旅行信息是否已整理完成。可重试整理；系统会核对这次操作，不会重复创建确认版本。")).toBeVisible();
  await expect(page).toHaveURL(/\/trip-compiler\?draft=/);
  const replayResponse = page.waitForResponse((response) => (
    response.url().includes("/preplan-intent/compile")
    && response.request().method() === "POST"
    && idempotencyKeys.length === 2
  ));
  await page.getByRole("button", { name: "重试整理这趟旅行" }).click();
  const replay = await replayResponse;

  expect(replay.status()).toBe(201);
  expect((await replay.json() as { idempotent_replay: boolean }).idempotent_replay).toBe(true);
  expect(idempotencyKeys).toHaveLength(2);
  expect([...new Set(idempotencyKeys)]).toEqual([idempotencyKeys[0]]);
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
});

test("A rejected draft compilation does not claim that the result is unknown", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.route("**/api/trips/*/preplan-intent/compile", (route) => route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: "这份旅行想法暂时无法整理。" }),
  }));

  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();

  await expect(page.getByText("这份旅行想法暂时无法整理。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试整理这趟旅行" })).toHaveCount(0);
  await expect(page.getByText("暂时无法确认这次旅行信息是否已整理完成。可重试整理；系统会核对这次操作，不会重复创建确认版本。")).toHaveCount(0);
});

test("Retrying a lost draft creation reuses the same travel idea", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  const idempotencyKeys: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/trips/drafts")) {
      idempotencyKeys.push(request.headers()["x-idempotency-key"] ?? "");
    }
  });
  let dropFirstResponse = true;
  await page.route("**/api/trips/drafts", async (route) => {
    if (!dropFirstResponse) {
      await route.continue();
      return;
    }
    dropFirstResponse = false;
    await route.fetch();
    await route.abort("connectionreset");
  });

  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();

  await expect(page.getByText("暂时无法确认这次旅行想法是否已保存。可重试开始；系统会核对这次操作，不会重复创建草稿。")).toBeVisible();
  const replayResponse = page.waitForResponse((response) => (
    response.url().endsWith("/api/trips/drafts")
    && response.request().method() === "POST"
    && idempotencyKeys.length === 2
  ));
  await page.getByRole("button", { name: "重试开始这趟旅行" }).click();
  const replay = await replayResponse;

  expect(replay.status()).toBe(201);
  expect((await replay.json() as { persistence: { idempotent_replay: boolean } }).persistence.idempotent_replay).toBe(true);
  expect(idempotencyKeys).toHaveLength(2);
  expect([...new Set(idempotencyKeys)]).toEqual([idempotencyKeys[0]]);
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
});

test("Reloading after a lost draft creation recovers without persisting travel text", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  let draftCreationRequests = 0;
  let draftRecoveryRequests = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/trips/drafts")) draftCreationRequests += 1;
    if (request.url().endsWith("/trips/drafts/recover")) draftRecoveryRequests += 1;
  });
  let dropFirstResponse = true;
  await page.route("**/api/trips/drafts", async (route) => {
    if (!dropFirstResponse) {
      await route.continue();
      return;
    }
    dropFirstResponse = false;
    await route.fetch();
    await route.abort("connectionreset");
  });

  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();

  await expect(page.getByText("暂时无法确认这次旅行想法是否已保存。可重试开始；系统会核对这次操作，不会重复创建草稿。")).toBeVisible();
  await expect.poll(() => page.evaluate(() => Object.values(sessionStorage).some((value) => value.includes("兵马俑")))).toBe(false);

  await page.reload();

  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  expect(draftCreationRequests).toBe(1);
  expect(draftRecoveryRequests).toBe(1);
});

test("A rejected draft creation does not claim that the result is unknown", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.route("**/api/trips/drafts", (route) => route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: "旅行想法暂时无法使用。" }),
  }));

  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();

  await expect(page.getByText("旅行想法暂时无法使用。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试开始这趟旅行" })).toHaveCount(0);
  await expect(page.getByText("暂时无法确认这次旅行想法是否已保存。可重试开始；系统会核对这次操作，不会重复创建草稿。")).toHaveCount(0);
});

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

async function previewRushedDayRepair(page: import("@playwright/test").Page) {
  const dayButtons = page.locator(".roadbook__masthead nav button");
  const trigger = page.getByRole("button", { name: /让第 \d+ 天轻松一些/ });
  for (let index = 0; index < await dayButtons.count() && await trigger.count() === 0; index += 1) {
    await dayButtons.nth(index).click();
  }
  await expect(trigger).toHaveCount(1);
  let applyRequests = 0;
  const countApply = (request: import("@playwright/test").Request) => {
    if (request.url().includes("/mutation-proposals/") && request.url().endsWith("/apply")) applyRequests += 1;
  };
  page.on("request", countApply);
  const responsePromise = page.waitForResponse((response) => response.url().includes("/local-repairs/relax-day/preview") && response.request().method() === "POST");
  await trigger.scrollIntoViewIfNeeded();
  await trigger.click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const payload = await response.json() as {
    proposal: { id: string; proposal_digest: string };
    current_revision: { id: string; revision_number: number };
    impact_summary: { local_repair: { stop_name: string; from_day: number; to_day: number } };
  };
  const proof = page.locator("[data-repair-preview=true]");
  await expect(proof).toBeVisible();
  await expect(proof).toBeFocused();
  await expect(proof.getByRole("heading", { name: "我们建议只调整这一段" })).toBeVisible();
  await expect(proof.getByText("调整前", { exact: true })).toBeVisible();
  await expect(proof.getByText("调整后", { exact: true })).toBeVisible();
  await expect(proof.getByText("保持不变", { exact: true })).toBeVisible();
  await expect(proof.locator(".repair-proof__protected").getByText("中国茶叶博物馆", { exact: false })).toBeVisible();
  await expect(proof.locator(".repair-proof__protected").getByText("灵隐寺", { exact: false })).toBeVisible();
  expect(applyRequests).toBe(0);
  page.off("request", countApply);
  return { payload, proof };
}

async function applyPreviewedRepair(page: import("@playwright/test").Page, proposalId: string) {
  const responsePromise = page.waitForResponse((response) => response.url().includes(`/mutation-proposals/${proposalId}/apply`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "应用这次调整" }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  return await response.json() as {
    current_revision: { id: string; revision_number: number; parent_revision_id: string | null; source_type: string };
  };
}

async function createSavedRoadbook(
  page: import("@playwright/test").Page,
  tripText = VISUAL_TRIP,
) {
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(tripText);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  await confirmVisiblePlaces(page);
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await expect(page.getByRole("heading", { name: "路线怎么不同，一眼就能看懂。" })).toBeVisible();
  const selected = page.waitForResponse((response) => response.url().includes("/select") && response.request().method() === "POST");
  await page.getByRole("button", { name: "就选这条路线" }).click();
  const response = await selected;
  expect(response.status()).toBe(201);
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  return await response.json() as SavedRoadbookPayload;
}

function allRouteItems(itinerary: SavedRoadbookPayload["itinerary"]) {
  return itinerary.days.flatMap((day) => day.blocks.flatMap((block) => block.items));
}

function assertVerifiedMealCompletion(saved: SavedRoadbookPayload) {
  const applicableSlots = saved.itinerary.meal_rhythm?.days
    .flatMap((day) => day.slots)
    .filter((slot) => slot.status !== "not_applicable") ?? [];
  expect(applicableSlots.length).toBeGreaterThan(0);

  const meals = allRouteItems(saved.itinerary).filter((item) => item.meal_role != null);
  const autoCompletedSlots = applicableSlots.filter((slot) => slot.status === "auto_completed");
  expect(meals.length).toBeGreaterThan(0);
  expect(meals).toHaveLength(autoCompletedSlots.length);
  expect(meals.every((item) => item.source_type === "auto_seeded_meal")).toBe(true);
  expect(meals.every((item) => item.verified_place?.provider === "amap" && Boolean(item.verified_place.provider_place_id))).toBe(true);
  expect(meals.every((item) => (
    (item.meal_route_evidence?.inbound.distance_m ?? 0) > 0
    && (item.meal_route_evidence?.inbound.duration_s ?? 0) > 0
    && (item.meal_route_evidence?.outbound.distance_m ?? 0) > 0
    && (item.meal_route_evidence?.outbound.duration_s ?? 0) > 0
  ))).toBe(true);
  const canonicalIds = allRouteItems(saved.itinerary).map((item) => item.canonical_place_id).filter(Boolean);
  expect(new Set(canonicalIds).size).toBe(canonicalIds.length);
}

async function showDayWithMealLabel(page: import("@playwright/test").Page) {
  const dayButtons = page.locator(".roadbook__masthead nav button");
  const mealLabel = page.getByText(/^(LUNCH \/ 午饭|DINNER \/ 晚饭)$/);
  for (let index = 0; index < await dayButtons.count() && await mealLabel.count() === 0; index += 1) {
    await dayButtons.nth(index).click();
  }
  await expect(mealLabel.first()).toBeVisible();
}

async function openSafeReplaceCandidates(
  page: import("@playwright/test").Page,
  targetName = "青芝坞餐厅",
  expectedCount?: number,
) {
  const dayButtons = page.locator(".roadbook__masthead nav button");
  const findTarget = () => page.locator("[data-roadbook-stop]:visible").filter({
    has: page.locator(".roadbook-stop__copy > strong").getByText(targetName, { exact: true }),
  });
  let target = findTarget();
  for (let index = 0; index < await dayButtons.count() && await target.count() === 0; index += 1) {
    await dayButtons.nth(index).click();
    target = findTarget();
  }
  await expect(target).toHaveCount(1);
  await target.click();
  await expect(target).toHaveAttribute("aria-pressed", "true");
  const candidateResponse = page.waitForResponse((response) => response.url().includes("/preview-completion-task-candidates") && response.request().method() === "POST");
  await page.getByRole("button", { name: "换一个" }).click();
  const response = await candidateResponse;
  expect(response.status()).toBe(200);
  const candidatePanel = page.getByRole("region", { name: `替换 ${targetName}` });
  await expect(candidatePanel).toBeVisible();
  await expect(candidatePanel).toBeFocused();
  await expect(candidatePanel.getByRole("heading", { name: "换一个更适合你的地点" })).toBeVisible();
  const payload = await response.json() as {
    options: Array<{ name: string; verified_place: { provider_place_id: string }; route_impact: { safe_to_apply: boolean } }>;
  };
  if (expectedCount == null) expect(payload.options.length).toBeGreaterThanOrEqual(1);
  else expect(payload.options).toHaveLength(expectedCount);
  expect(payload.options.length).toBeLessThanOrEqual(3);
  expect(payload.options.every((option) => Boolean(option.verified_place.provider_place_id))).toBe(true);
  expect(payload.options.every((option) => option.route_impact.safe_to_apply)).toBe(true);
  expect(payload.options.some((option) => option.name === targetName)).toBe(false);
  if (payload.options.length) {
    await expect(page.getByText(`找到 ${payload.options.length} 个可以安全换进去的地点`)).toBeVisible();
  } else {
    await expect(page.getByText("附近暂时没有找到一个真正适合换进去的地点。")).toBeVisible();
  }
  return payload;
}

async function selectReplacementCandidate(page: import("@playwright/test").Page, name: string) {
  const card = page.locator(".safe-replace-candidate").filter({ hasText: name });
  await expect(card).toHaveCount(1);
  await card.getByRole("button", { name: /看看换成这里/ }).click();
}

async function currentRevision(page: import("@playwright/test").Page, tripId: string) {
  const response = await page.request.get(`/api/trips/${tripId}`);
  expect(response.status()).toBe(200);
  return (await response.json() as { current_revision: { id: string; revision_number: number } }).current_revision;
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
  await expect(page.getByText("你提到的地点 · 尚未作为路线地点保存", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/提供商候选（系统推荐）：请选择具体地点；确认前不会加入路线。/).first()).toBeVisible();
  await confirmVisiblePlaces(page);

  await page.route("**/api/trips/*/preplan-intent/planning-run", async (route) => {
    const response = await route.fetch();
    const planningRun = await response.json() as PlanCandidateResponse;
    planningRun.candidates[0].metrics.travel_data_completeness = "missing";
    planningRun.candidates[0].metrics.missing_travel_data = true;
    planningRun.candidates[0].metrics.total_travel_minutes = null;
    planningRun.candidates[0].strategy = "relaxed";
    planningRun.candidates[0].title = "留出更多空白";
    planningRun.candidates[0].tradeoff_summary = "最少每天预留 75 分钟弹性时间。";
    const systemStop = planningRun.candidates[0].itinerary.days
      .flatMap((day) => day.blocks)
      .flatMap((block) => block.items)
      .find((item) => !item.is_fixed);
    if (!systemStop) throw new Error("Expected a flexible candidate stop for recommendation rationale coverage.");
    systemStop.source_type = "auto_seeded_meal";
    systemStop.source_label = "系统补充";
    systemStop.source_reason = "系统为这一天补上的午饭，避开了下午的固定安排。";
    const firstComparison = planningRun.comparison.find((item) => item.candidate_id === planningRun.candidates[0].id);
    if (firstComparison) firstComparison.highlights = ["最少每天预留 75 分钟"];
    await route.fulfill({ response, json: planningRun });
  });
  const createdRun = page.waitForResponse((response) => response.url().includes("/preplan-intent/planning-run") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成我的路线" }).click();
  expect((await createdRun).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "路线怎么不同，一眼就能看懂。" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "路线方案" })).toBeVisible();
  await expect(page.getByText("固定安排和必去地点已保留；路程仍待确认。", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("留白更多", { exact: true })).toHaveCount(0);
  await expect(page.getByText("最少每天预留 75 分钟弹性时间。", { exact: true })).toHaveCount(0);
  await expect(page.locator(".tc-route-proof").getByText("路程待确认", { exact: true })).toBeVisible();
  await expect(page.locator(".tc-route-facts div").filter({ hasText: "每天至少留白" }).getByText("待确认", { exact: true })).toBeVisible();
  await expect(page.locator(".tc-route-stop-reason").filter({ hasText: "系统为这一天补上的午饭，避开了下午的固定安排。" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(SCREENSHOT_DIRECTORY, "desktop-route-preview.png") });

  await page.route("**/api/trip-compiler/planning-runs/*/candidates/*/select", async (route) => {
    const response = await route.fetch();
    const selected = await response.json() as SavedRoadbookPayload;
    const visibleLegs = allRouteItems(selected.itinerary)
      .filter((item) => shouldDisplayTravelLeg(selected.itinerary, item));
    for (const item of visibleLegs) {
      item.travel_data_status = "confirmed";
      item.travel_duration_s ??= 600;
      item.travel_distance_m ??= 1_000;
    }
    const pendingLeg = visibleLegs[0];
    if (!pendingLeg) throw new Error("Expected saved route to contain a visible travel leg.");
    pendingLeg.travel_data_status = "unavailable";
    pendingLeg.travel_duration_s = null;
    pendingLeg.travel_distance_m = null;
    await route.fulfill({ response, json: selected });
  });
  const selectedRoute = page.waitForResponse((response) => response.url().includes("/select") && response.request().method() === "POST");
  await page.getByRole("button", { name: "就选这条路线" }).click();
  const selectedRouteResponse = await selectedRoute;
  expect(selectedRouteResponse.status()).toBe(201);
  const savedRoadbook = await selectedRouteResponse.json() as SavedRoadbookPayload;
  assertVerifiedMealCompletion(savedRoadbook);
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  const verificationNote = page.locator('[aria-label="路线核验提示"]');
  await expect(verificationNote).toContainText("有 1 段相邻路线待确认");
  await expect(verificationNote).toContainText("不会按零分钟处理，请在出发前核验。");
  await expect(page.locator('[data-roadbook-layout="living"]')).toBeVisible();
  await expect(page.locator('[data-route-map-pane="true"]')).toBeVisible();
  await expect(page.getByText(/路线中心/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: /帮我松一点/ })).toHaveCount(0);
  await page.route("**/api/preview-poi-detail", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        found: true,
        name: "西湖",
        address: "杭州市西湖区",
        category: "风景名胜",
        business_area: null,
        rating: null,
        cost: null,
        tel: null,
        website: null,
        open_time: null,
        photo_url: null,
        latitude: 30.25,
        longitude: 120.14,
        source: "amap_place_detail",
        observed_at: "2026-09-26T12:00:00Z",
        failure_reason: null,
      }),
    });
  });
  await verifyFixedArrangementProtection(page);
  await verifyMapEvidenceSettled(page);
  await showDayWithMealLabel(page);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(MEAL_SCREENSHOT_DIRECTORY, "desktop-meal-completed.png") });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(ROADBOOK_SCREENSHOT_DIRECTORY, "desktop-roadbook.png") });
  await page.screenshot({ path: join(REPAIR_SCREENSHOT_DIRECTORY, "desktop-repair-before.png") });
  const desktopStops = page.locator("[data-roadbook-stop]");
  expect(await desktopStops.count()).toBeGreaterThan(1);
  await desktopStops.nth(1).click();
  await expect(desktopStops.nth(1)).toHaveAttribute("aria-pressed", "true");
  const desktopDetail = page.locator("[data-roadbook-selected-place]");
  await expect(desktopDetail).toBeVisible();
  await expect(desktopDetail.getByText("核验状态", { exact: true })).toBeVisible();
  await expect(desktopDetail.getByText(/地点详情查询于/)).toBeVisible();
  await expect(desktopDetail.getByText("地点详情（如营业时间）待验证；当前安排只是时间骨架，不能确认该地点在此时开放。", { exact: true })).toBeVisible();
  await desktopDetail.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(ROADBOOK_SCREENSHOT_DIRECTORY, "desktop-roadbook-selected-place.png") });
  await desktopDetail.getByRole("button", { name: /查看下一站/ }).click();
  await expect(desktopStops.nth(2)).toHaveAttribute("aria-pressed", "true");

  const { payload: repairPreview, proof } = await previewRushedDayRepair(page);
  await expect(page.locator(".roadbook__timeline").getByText(repairPreview.impact_summary.local_repair.stop_name, { exact: true })).toBeVisible();
  await proof.evaluate((element) => element.scrollIntoView({ block: "start" }));
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(REPAIR_SCREENSHOT_DIRECTORY, "desktop-repair-preview.png") });
  await page.route("**/api/trips/*/mutation-proposals/*/apply", async (route) => {
    const response = await route.fetch();
    const applied = await response.json() as SavedRoadbookPayload;
    for (const item of allRouteItems(applied.itinerary).filter((candidate) => shouldDisplayTravelLeg(applied.itinerary, candidate))) {
      item.travel_data_status = "confirmed";
      item.travel_duration_s ??= 600;
      item.travel_distance_m ??= 1_000;
    }
    await route.fulfill({ response, json: applied });
  });
  const applied = await applyPreviewedRepair(page, repairPreview.proposal.id);
  expect(applied.current_revision.revision_number).toBe(repairPreview.current_revision.revision_number + 1);
  expect(applied.current_revision.parent_revision_id).toBe(repairPreview.current_revision.id);
  expect(applied.current_revision.source_type).toBe("route_edit");
  const savedRepairMessage = `这段路线已经松了一点，调整已保存为版本 ${applied.current_revision.revision_number}。`;
  await expect(page.getByText(savedRepairMessage)).toBeVisible();
  await expect(
    page
      .locator(".erp-repair-feedback")
      .filter({ hasText: savedRepairMessage }),
  ).toBeFocused();
  await expect(page.getByRole("button", { name: "撤销刚才的调整" })).toBeVisible();
  await expect(page.locator(".roadbook__timeline").getByText(repairPreview.impact_summary.local_repair.stop_name, { exact: true })).toHaveCount(0);
  await expect(page.locator('[aria-label="路线核验提示"]')).toHaveCount(0);
  await page.locator(".erp-repair-feedback").scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(REPAIR_SCREENSHOT_DIRECTORY, "desktop-repair-applied.png") });
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  await page.getByRole("button", { name: "关闭候选地点" }).click();
  await page.reload();
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  await expect(page.locator(".roadbook__timeline").getByText(repairPreview.impact_summary.local_repair.stop_name, { exact: true })).toHaveCount(0);
  await page.locator(".roadbook__masthead nav button").nth(repairPreview.impact_summary.local_repair.to_day - 1).click();
  await expect(page.locator(".roadbook__timeline").getByText(repairPreview.impact_summary.local_repair.stop_name, { exact: true })).toBeVisible();
  assertClean();
});

test("Saved roadbook keeps provider opening hours visible without claiming a booking", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await createSavedRoadbook(page);
  await page.route("**/api/preview-poi-detail", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        found: true,
        name: "行程地点",
        address: "杭州市西湖区",
        category: "地点",
        business_area: null,
        rating: null,
        cost: null,
        tel: null,
        website: null,
        open_time: "09:00-17:00",
        open_time_coverage: "covers_scheduled_window",
        photo_url: null,
        latitude: 30.25,
        longitude: 120.14,
        source: "amap_place_detail",
        observed_at: "2026-09-26T12:00:00Z",
        failure_reason: null,
      }),
    });
  });

  const stops = page.locator("[data-roadbook-stop]");
  await stops.last().click();
  const detail = page.locator("[data-roadbook-selected-place]");
  await expect(detail).toBeVisible();
  await expect(detail.getByText("营业时间快照", { exact: true })).toBeVisible();
  await expect(detail.getByText("09:00-17:00 · 高德地点详情 · 查询于 2026-09-26T12:00:00Z", { exact: true })).toBeVisible();
  await expect(detail.getByText(/提供方的单段日常营业时间覆盖当前安排钟点/)).toBeVisible();
  await expect(detail.getByText(/具体日期、临时闭馆和预约规则仍待核验/)).toBeVisible();
  assertClean();
});

test("Saved roadbook distinguishes a protected fixed arrangement from a verified reservation", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await createSavedRoadbook(page);
  await page.locator(".roadbook__masthead nav button").nth(1).click();
  const fixedStop = page.locator("[data-roadbook-stop]").filter({ hasText: "LOCKED" }).first();
  await expect(fixedStop).toBeVisible();
  await fixedStop.click();
  const detail = page.locator("[data-roadbook-selected-place]");
  await expect(detail).toBeVisible();
  await expect(detail.getByText(/这个固定安排会按你的输入保护/)).toBeVisible();
  await expect(detail.getByText(/尚未核验订单、入场资格或预约状态/)).toBeVisible();
  assertClean();
});

test("Trip Compiler gives mobile users a direct path to an unresolved fixed place", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();

  const confirmation = page.waitForResponse((response) => response.url().includes("/preplan-intent/edits") && response.request().method() === "POST");
  await page.locator(".tc-place-options button").first().click();
  expect((await confirmation).status()).toBe(201);
  await expect(page.getByText("地点已确认。固定安排地点仍待确认，确认后才能生成路线。")).toBeVisible();
  await page.getByRole("button", { name: "查看待确认的固定地点" }).click();
  const fixedPlace = page.locator(".tc-place").filter({ hasText: "中国茶叶博物馆" });
  await expect(fixedPlace).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
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
  const selectedRouteResponse = await selectedRoute;
  expect(selectedRouteResponse.status()).toBe(201);
  const savedRoadbook = await selectedRouteResponse.json() as SavedRoadbookPayload;
  assertVerifiedMealCompletion(savedRoadbook);
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  await expect(page.locator('[data-roadbook-layout="living"]')).toBeVisible();
  await expect(page.locator('[data-route-map-pane="true"]')).toBeVisible();
  await expect(page.getByRole("button", { name: /帮我松一点/ })).toHaveCount(0);
  await verifyFixedArrangementProtection(page);
  await verifyMapEvidenceSettled(page);
  await showDayWithMealLabel(page);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(MEAL_SCREENSHOT_DIRECTORY, "mobile-meal-completed.png") });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(ROADBOOK_SCREENSHOT_DIRECTORY, "mobile-roadbook.png") });
  const mobileStops = page.locator("[data-roadbook-stop]");
  expect(await mobileStops.count()).toBeGreaterThan(1);
  const firstMobileStop = await mobileStops.first().boundingBox();
  expect((firstMobileStop?.y ?? Number.POSITIVE_INFINITY) + (firstMobileStop?.height ?? 0)).toBeLessThanOrEqual(844);
  await mobileStops.nth(1).click();
  await expect(mobileStops.nth(1)).toHaveAttribute("aria-pressed", "true");
  const mobileDetail = page.locator("[data-roadbook-selected-place]");
  await expect(mobileDetail).toBeVisible();
  await mobileDetail.scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(ROADBOOK_SCREENSHOT_DIRECTORY, "mobile-roadbook-selected-place.png") });
  await mobileDetail.getByRole("button", { name: /查看下一站/ }).click();
  await expect(mobileStops.nth(2)).toHaveAttribute("aria-pressed", "true");

  const { payload: repairPreview, proof } = await previewRushedDayRepair(page);
  await proof.evaluate((element) => element.scrollIntoView({ block: "start" }));
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(REPAIR_SCREENSHOT_DIRECTORY, "mobile-repair-preview.png") });
  const applied = await applyPreviewedRepair(page, repairPreview.proposal.id);
  await expect(page.getByText(`这段路线已经松了一点，调整已保存为版本 ${applied.current_revision.revision_number}。`)).toBeVisible();
  await page.locator(".erp-repair-feedback").scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(REPAIR_SCREENSHOT_DIRECTORY, "mobile-repair-applied.png") });
  const undoResponsePromise = page.waitForResponse((response) => response.url().includes(`/revisions/${applied.current_revision.id}/undo`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "撤销刚才的调整" }).click();
  const undoResponse = await undoResponsePromise;
  expect(undoResponse.status()).toBe(200);
  const undone = await undoResponse.json() as { current_revision: { revision_number: number; source_type: string; restored_from_revision_id: string | null } };
  expect(undone.current_revision.revision_number).toBe(applied.current_revision.revision_number + 1);
  expect(undone.current_revision.source_type).toBe("mutation_undo");
  expect(undone.current_revision.restored_from_revision_id).toBe(repairPreview.current_revision.id);
  const undoRepairReceipt = `已撤销这次调整，并保存为新版本 ${undone.current_revision.revision_number}。调整前的路线已恢复。`;
  await expect(page.getByText(undoRepairReceipt)).toBeVisible();
  await expect(
    page
      .locator(".erp-repair-feedback")
      .filter({ hasText: undoRepairReceipt }),
  ).toBeFocused();
  await expect(
    page
      .locator(".erp-repair-feedback")
      .filter({ hasText: undoRepairReceipt }),
  ).toContainText("ROUTE RESTORED");
  await expect(page.locator(".roadbook__timeline").getByText(repairPreview.impact_summary.local_repair.stop_name, { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  await page.locator(".roadbook__masthead nav button").nth(repairPreview.impact_summary.local_repair.from_day - 1).click();
  await expect(page.locator(".roadbook__timeline").getByText(repairPreview.impact_summary.local_repair.stop_name, { exact: true })).toBeVisible();
  assertClean();
});

test("A stale route candidate returns to confirmed inputs without saving", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  await confirmVisiblePlaces(page);
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await expect(page.getByRole("heading", { name: "路线怎么不同，一眼就能看懂。" })).toBeVisible();

  await page.route("**/api/trip-compiler/planning-runs/*/candidates/*/select", (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "candidate_stale", message: "This candidate is stale." } }),
  }));
  await page.getByRole("button", { name: "就选这条路线" }).click();

  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  await expect(page.getByText("这批路线候选已过期，没有保存任何行程。请基于当前确认信息重新生成路线。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "生成我的路线" })).toBeFocused();
});

test("Retrying a failed route save keeps the same idempotency key", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await confirmVisiblePlaces(page);
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await expect(page.getByRole("heading", { name: "路线怎么不同，一眼就能看懂。" })).toBeVisible();

  const selectionPattern = "**/api/trip-compiler/planning-runs/*/candidates/*/select";
  const keys: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/trip-compiler/planning-runs/") && request.url().includes("/candidates/") && request.url().endsWith("/select")) {
      keys.push(request.headers()["x-idempotency-key"] ?? "");
    }
  });
  await page.route(selectionPattern, (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "service_unavailable", message: "Temporary service issue." } }),
  }));
  await page.getByRole("button", { name: "就选这条路线" }).click();
  await expect(page.locator(".tc-candidate-error")).toHaveText("暂时未能确认保存结果。请重试同一条路线；系统会继续这次保存，不会重复创建行程。");
  await page.unroute(selectionPattern);

  await page.getByRole("button", { name: "就选这条路线" }).click();
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[1]).toBe(keys[0]);
});

test("A rejected route save does not claim that its result is unknown", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await confirmVisiblePlaces(page);
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await expect(page.getByRole("heading", { name: "路线怎么不同，一眼就能看懂。" })).toBeVisible();

  await page.route("**/api/trip-compiler/planning-runs/*/candidates/*/select", (route) => route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: "这条路线已不符合当前旅行信息。" }),
  }));
  await page.getByRole("button", { name: "就选这条路线" }).click();

  await expect(page.locator(".tc-candidate-error")).toHaveText("这条路线已不符合当前旅行信息。");
  await expect(page.getByText("暂时未能确认保存结果。请重试同一条路线；系统会继续这次保存，不会重复创建行程。")).toHaveCount(0);
});

test("Reloading after a lost route-save response recovers the saved route without replaying the save", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await confirmVisiblePlaces(page);
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await expect(page.getByRole("heading", { name: "路线怎么不同，一眼就能看懂。" })).toBeVisible();

  const selectionPattern = "**/api/trip-compiler/planning-runs/*/candidates/*/select";
  let selectionRequests = 0;
  await page.route(selectionPattern, async (route) => {
    selectionRequests += 1;
    if (selectionRequests === 1) {
      await route.fetch();
      await route.abort("connectionreset");
      return;
    }
    await route.continue();
  });
  await page.getByRole("button", { name: "就选这条路线" }).click();
  await expect(page.locator(".tc-candidate-error")).toHaveText("暂时未能确认保存结果。请重试同一条路线；系统会继续这次保存，不会重复创建行程。");

  await page.reload();
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  expect(selectionRequests).toBe(1);
});

test("Unavailable session recovery storage does not block saving a route", async ({ page }) => {
  await page.addInitScript(() => {
    const storage = Storage.prototype;
    const originalSetItem = storage.setItem;
    const originalRemoveItem = storage.removeItem;
    storage.setItem = function(key, value) {
      if (key.startsWith("trip-candidate-selection:")) throw new DOMException("Storage unavailable.", "SecurityError");
      return originalSetItem.call(this, key, value);
    };
    storage.removeItem = function(key) {
      if (key.startsWith("trip-candidate-selection:")) throw new DOMException("Storage unavailable.", "SecurityError");
      return originalRemoveItem.call(this, key);
    };
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await confirmVisiblePlaces(page);
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await page.getByRole("button", { name: "就选这条路线" }).click();

  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
});

test("Reloading after a lost route-save response recovers without session storage", async ({ page }) => {
  await page.addInitScript(() => {
    const storage = Storage.prototype;
    const originalSetItem = storage.setItem;
    storage.setItem = function(key, value) {
      if (key.startsWith("trip-candidate-selection:")) throw new DOMException("Storage unavailable.", "SecurityError");
      return originalSetItem.call(this, key, value);
    };
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await confirmVisiblePlaces(page);
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await expect(page.getByRole("heading", { name: "路线怎么不同，一眼就能看懂。" })).toBeVisible();

  const selectionPattern = "**/api/trip-compiler/planning-runs/*/candidates/*/select";
  let selectionRequests = 0;
  await page.route(selectionPattern, async (route) => {
    selectionRequests += 1;
    await route.fetch();
    await route.abort("connectionreset");
  });
  await page.getByRole("button", { name: "就选这条路线" }).click();
  await expect(page.locator(".tc-candidate-error")).toHaveText("暂时未能确认保存结果。请重试同一条路线；系统会继续这次保存，不会重复创建行程。");

  await page.reload();
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  expect(selectionRequests).toBe(1);
});

test("Choosing another route after a failed save starts a new idempotency operation", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(VISUAL_TRIP);
  await page.getByRole("button", { name: "开始编排行程" }).click();
  await confirmVisiblePlaces(page);
  await page.getByRole("button", { name: "生成我的路线" }).click();
  await expect(page.getByRole("heading", { name: "路线怎么不同，一眼就能看懂。" })).toBeVisible();

  const selectionPattern = "**/api/trip-compiler/planning-runs/*/candidates/*/select";
  const selections: Array<{ key: string; url: string }> = [];
  page.on("request", (request) => {
    if (request.url().includes("/trip-compiler/planning-runs/") && request.url().includes("/candidates/") && request.url().endsWith("/select")) {
      selections.push({ key: request.headers()["x-idempotency-key"] ?? "", url: request.url() });
    }
  });
  await page.route(selectionPattern, (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "service_unavailable", message: "Temporary service issue." } }),
  }));
  await page.getByRole("button", { name: "就选这条路线" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("navigation", { name: "路线方案目录" }).getByRole("button").nth(1).click();
  await page.unroute(selectionPattern);

  await page.getByRole("button", { name: "就选这条路线" }).click();
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  expect(selections).toHaveLength(2);
  expect(selections[1].url).not.toBe(selections[0].url);
  expect(selections[1].key).not.toBe(selections[0].key);
});

test("Saved Roadbook safely replaces one stop and preserves the result on desktop", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const saved = await createSavedRoadbook(page);
  const candidates = await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  expect(candidates.options.some((option) => option.name === "茶人村" && option.route_impact.safe_to_apply)).toBe(true);
  expect(candidates.options.some((option) => option.name === "桂语山房" && option.route_impact.safe_to_apply)).toBe(true);
  expect(candidates.options.some((option) => option.name === "远山宴")).toBe(false);
  await expect(page.getByText("远山宴", { exact: true })).toHaveCount(0);
  await page.locator(".safe-replace--candidates").scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(REPLACE_QUALITY_SCREENSHOT_DIRECTORY, "desktop-replace-quality-candidates.png") });

  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  expect(preview.status()).toBe(200);
  const previewPayload = await preview.json() as {
    proposal: { id: string };
    current_revision: { id: string; revision_number: number };
  };
  await expect(page.getByRole("heading", { name: "换成这里以后，这一段会这样走" })).toBeVisible();
  await expect(page.getByText("保持不变", { exact: true })).toBeVisible();
  await expect(page.getByText("中国茶叶博物馆", { exact: false })).toBeVisible();
  await page.locator(".safe-replace--preview").scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(REPLACE_SCREENSHOT_DIRECTORY, "desktop-replace-preview.png") });

  const applyResponse = page.waitForResponse((response) => response.url().includes(`/mutation-proposals/${previewPayload.proposal.id}/apply`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "换成这个地点" }).click();
  const appliedResponse = await applyResponse;
  expect(appliedResponse.status()).toBe(200);
  const applied = await appliedResponse.json() as { current_revision: { id: string; revision_number: number; parent_revision_id: string | null } };
  expect(applied.current_revision.revision_number).toBe(previewPayload.current_revision.revision_number + 1);
  expect(applied.current_revision.parent_revision_id).toBe(previewPayload.current_revision.id);
  await expect(page.getByText(`这个地点已经从湖畔小馆换成茶人村，并保存为版本 ${applied.current_revision.revision_number}。其他已经确认的安排没有被改动。`)).toBeVisible();
  await expect(page.locator("[data-roadbook-selected-place]").getByText("茶人村", { exact: true })).toBeVisible();
  await expect(page.locator('[data-route-map-pane="true"]')).toBeVisible();
  await page.locator(".erp-repair-feedback").scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(REPLACE_SCREENSHOT_DIRECTORY, "desktop-replace-applied.png") });
  await page.reload();
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  await expect(page.getByText("茶人村", { exact: true }).first()).toBeVisible();
  expect((await currentRevision(page, saved.trip.id)).id).toBe(applied.current_revision.id);

  const beforeEmpty = await currentRevision(page, saved.trip.id);
  await openSafeReplaceCandidates(page, "青芝坞餐厅", 0);
  await page.locator(".safe-replace--candidates").scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(REPLACE_QUALITY_SCREENSHOT_DIRECTORY, "desktop-replace-quality-empty.png") });
  await page.getByRole("button", { name: "保留原地点" }).click();
  expect((await currentRevision(page, saved.trip.id)).id).toBe(beforeEmpty.id);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  assertClean();
});

test("Safe replacement shows one useful candidate without padding", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const saved = await createSavedRoadbook(page);
  const before = await currentRevision(page, saved.trip.id);
  const originalStop = page.locator("[data-roadbook-stop]").filter({
    has: page.locator(".roadbook-stop__copy > strong").getByText("龙井草堂", { exact: true }),
  });
  const candidates = await openSafeReplaceCandidates(page, "龙井草堂", 1);
  expect(candidates.options.map((option) => option.name)).toEqual(["茶人村"]);
  await expect(page.locator(".safe-replace-candidate")).toHaveCount(1);
  await page.getByRole("button", { name: "关闭候选地点" }).click();
  await expect(originalStop).toBeFocused();
  expect((await currentRevision(page, saved.trip.id)).id).toBe(before.id);
  assertClean();
});

test("Stale saved replacement lets the traveler load the latest route without retrying the old proposal", async ({ page }) => {
  const assertClean = installNetworkGate(page, { ignoreConsoleError: isExpectedStaleConflictConsole });
  await page.setViewportSize({ width: 1440, height: 900 });
  const saved = await createSavedRoadbook(page);
  const preview = await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  await selectReplacementCandidate(page, "茶人村");
  await expect(page.getByRole("heading", { name: "换成这里以后，这一段会这样走" })).toBeVisible();

  let applyRequests = 0;
  let latestRouteReads = 0;
  page.on("request", (request) => {
    if (request.url().includes("/mutation-proposals/") && request.url().endsWith("/apply")) applyRequests += 1;
    if (request.url().endsWith(`/api/trips/${saved.trip.id}`) && request.method() === "GET") latestRouteReads += 1;
  });
  await page.route("**/api/trips/*/mutation-proposals/*/apply", (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "stale_mutation_proposal", message: "The mutation proposal is based on a stale revision." } }),
  }));

  await page.getByRole("button", { name: "换成这个地点" }).click();
  await expect(page.getByText("这次替换没有保存，原路线保持不变。", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "载入最新路线" }).click();

  const latestRouteReceipt = `已载入最新保存版本 ${saved.current_revision.revision_number}；没有应用刚才的替换。请基于这版路线重新选择地点。`;
  await expect(page.getByText(latestRouteReceipt)).toBeVisible();
  await expect(
    page
      .locator(".erp-repair-feedback")
      .filter({ hasText: latestRouteReceipt }),
  ).toBeFocused();
  expect(latestRouteReads).toBe(1);
  expect(applyRequests).toBe(1);
  assertClean();
});

test("Retrying a replacement after a lost save response replays the same replacement", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  const proposal = await preview.json() as { proposal: { id: string } };
  const idempotencyKeys: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes(`/mutation-proposals/${proposal.proposal.id}/apply`)) {
      idempotencyKeys.push(request.headers()["x-idempotency-key"] ?? "");
    }
  });

  let dropFirstResponse = true;
  await page.route(`**/api/trips/*/mutation-proposals/${proposal.proposal.id}/apply`, async (route) => {
    if (!dropFirstResponse) {
      await route.continue();
      return;
    }
    dropFirstResponse = false;
    await route.fetch();
    await route.abort("connectionreset");
  });

  await page.getByRole("button", { name: "换成这个地点" }).click();
  await expect(page.getByText("暂时无法确认这次替换是否已保存。可重试同一项替换；系统会核对这次操作，不会重复创建版本。")).toBeVisible();
  const replayResponse = page.waitForResponse((response) => (
    response.url().includes(`/mutation-proposals/${proposal.proposal.id}/apply`)
    && response.request().method() === "POST"
    && idempotencyKeys.length === 2
  ));
  await page.getByRole("button", { name: "重试这次替换" }).click();
  const replay = await replayResponse;
  expect(replay.status()).toBe(200);
  expect((await replay.json() as { persistence: { idempotent_replay: boolean } }).persistence.idempotent_replay).toBe(true);
  expect(idempotencyKeys).toHaveLength(2);
  expect([...new Set(idempotencyKeys)]).toEqual([idempotencyKeys[0]]);
  await expect(page.getByText("这个地点已经从湖畔小馆换成茶人村，并保存为版本 2。其他已经确认的安排没有被改动。")).toBeVisible();
});

test("A rejected replacement does not present an uncertain-save retry", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  const proposal = await preview.json() as { proposal: { id: string } };
  await page.route(`**/api/trips/*/mutation-proposals/${proposal.proposal.id}/apply`, (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "proposal_digest_mismatch", message: "The proposal does not match its digest." } }),
  }));

  await page.getByRole("button", { name: "换成这个地点" }).click();
  await expect(page.getByText("这次替换没有保存。原来的地点仍然保留。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试这次替换" })).toHaveCount(0);
});

test("A 422 replacement rejection without a business code does not claim an uncertain save", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  const previewPayload = await preview.json() as { proposal: { id: string } };
  await page.route(`**/api/trips/*/mutation-proposals/${previewPayload.proposal.id}/apply`, (route) => route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: "这个替换暂时不能应用。" }),
  }));

  await page.getByRole("button", { name: "换成这个地点" }).click();

  await expect(page.getByText("这次替换没有保存。原来的地点仍然保留。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试这次替换" })).toHaveCount(0);
  await expect(page.getByText("暂时无法确认这次替换是否已保存。可重试同一项替换；系统会核对这次操作，不会重复创建版本。")).toHaveCount(0);
});

test("A 503 replacement response keeps the safe idempotent retry", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  const previewPayload = await preview.json() as { proposal: { id: string } };
  await page.route(`**/api/trips/*/mutation-proposals/${previewPayload.proposal.id}/apply`, (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "service_unavailable", message: "Temporary service issue." } }),
  }));

  await page.getByRole("button", { name: "换成这个地点" }).click();

  await expect(page.getByText("暂时无法确认这次替换是否已保存。可重试同一项替换；系统会核对这次操作，不会重复创建版本。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试这次替换" })).toBeVisible();
});

test("Retrying a replacement undo after a lost response replays the same undo", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  const proposal = await preview.json() as { proposal: { id: string } };
  const applyResponse = page.waitForResponse((response) => response.url().includes(`/mutation-proposals/${proposal.proposal.id}/apply`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "换成这个地点" }).click();
  const applied = await (await applyResponse).json() as { current_revision: { id: string } };
  const idempotencyKeys: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes(`/revisions/${applied.current_revision.id}/undo`)) {
      idempotencyKeys.push(request.headers()["x-idempotency-key"] ?? "");
    }
  });

  let dropFirstResponse = true;
  await page.route(`**/api/trips/*/revisions/${applied.current_revision.id}/undo`, async (route) => {
    if (!dropFirstResponse) {
      await route.continue();
      return;
    }
    dropFirstResponse = false;
    await route.fetch();
    await route.abort("connectionreset");
  });

  await page.getByRole("button", { name: "撤销刚才的替换" }).click();
  await expect(page.getByText("暂时无法确认这次撤销是否已保存。可重试撤销；系统会核对这次操作，不会重复创建版本。")).toBeVisible();
  const replayResponse = page.waitForResponse((response) => (
    response.url().includes(`/revisions/${applied.current_revision.id}/undo`)
    && response.request().method() === "POST"
    && idempotencyKeys.length === 2
  ));
  await page.getByRole("button", { name: "重试撤销" }).click();
  const replay = await replayResponse;
  expect(replay.status()).toBe(200);
  expect((await replay.json() as { persistence: { idempotent_replay: boolean } }).persistence.idempotent_replay).toBe(true);
  expect(idempotencyKeys).toHaveLength(2);
  expect([...new Set(idempotencyKeys)]).toEqual([idempotencyKeys[0]]);
  await expect(page.getByText("已撤销这次替换，并保存为新版本 3。原来的地点和相邻路线已恢复。")).toBeVisible();
});

test("A rejected replacement undo does not claim an uncertain result", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  const proposal = await preview.json() as { proposal: { id: string } };
  const applyResponse = page.waitForResponse((response) => response.url().includes(`/mutation-proposals/${proposal.proposal.id}/apply`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "换成这个地点" }).click();
  const applied = await (await applyResponse).json() as { current_revision: { id: string } };
  await page.route(`**/api/trips/*/revisions/${applied.current_revision.id}/undo`, (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "idempotency_conflict", message: "The operation key conflicts with a different request." } }),
  }));

  await page.getByRole("button", { name: "撤销刚才的替换" }).click();
  await expect(page.getByText("这次撤销没有保存。当前路线仍然保留。")).toBeVisible();
  await expect(page.getByText("暂时无法确认这次撤销是否已保存。可重试撤销；系统会核对这次操作，不会重复创建版本。")).toHaveCount(0);
});

test("A 422 replacement undo rejection without a business code does not claim an uncertain result", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  const proposal = await preview.json() as { proposal: { id: string } };
  const applyResponse = page.waitForResponse((response) => response.url().includes(`/mutation-proposals/${proposal.proposal.id}/apply`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "换成这个地点" }).click();
  const applied = await (await applyResponse).json() as { current_revision: { id: string } };
  await page.route(`**/api/trips/*/revisions/${applied.current_revision.id}/undo`, (route) => route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: "这次替换暂时不能撤销。" }),
  }));

  await page.getByRole("button", { name: "撤销刚才的替换" }).click();

  await expect(page.getByText("这次撤销没有保存。当前路线仍然保留。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试撤销" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "撤销刚才的替换" })).toBeVisible();
  await expect(page.getByText("暂时无法确认这次撤销是否已保存。可重试撤销；系统会核对这次操作，不会重复创建版本。")).toHaveCount(0);
});

test("A 503 replacement undo response keeps the safe idempotent retry", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  const proposal = await preview.json() as { proposal: { id: string } };
  const applyResponse = page.waitForResponse((response) => response.url().includes(`/mutation-proposals/${proposal.proposal.id}/apply`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "换成这个地点" }).click();
  const applied = await (await applyResponse).json() as { current_revision: { id: string } };
  await page.route(`**/api/trips/*/revisions/${applied.current_revision.id}/undo`, (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "service_unavailable", message: "Temporary service issue." } }),
  }));

  await page.getByRole("button", { name: "撤销刚才的替换" }).click();

  await expect(page.getByText("暂时无法确认这次撤销是否已保存。可重试撤销；系统会核对这次操作，不会重复创建版本。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试撤销" })).toBeVisible();
});

test("A stale replacement undo names the failed undo and loads the latest route", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const saved = await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  const proposal = await preview.json() as { proposal: { id: string } };
  const applyResponse = page.waitForResponse((response) => response.url().includes(`/mutation-proposals/${proposal.proposal.id}/apply`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "换成这个地点" }).click();
  const applied = await (await applyResponse).json() as { current_revision: { id: string } };
  await page.route(`**/api/trips/*/revisions/${applied.current_revision.id}/undo`, (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: {
      code: "mutation_command_failed",
      message: "The route changed before this undo could apply.",
      reason_code: "undo_target_not_current",
    } }),
  }));

  await page.getByRole("button", { name: "撤销刚才的替换" }).click();

  await expect(page.getByText("路线刚刚发生了变化。这次撤销没有保存。请载入最新路线确认当前安排。")).toBeVisible();
  await expect(page.getByRole("button", { name: "载入最新路线" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重试撤销" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "撤销刚才的替换" })).toHaveCount(0);

  const latestRouteResponse = page.waitForResponse((response) => (
    response.url().endsWith(`/api/trips/${saved.trip.id}`) && response.request().method() === "GET"
  ));
  await page.getByRole("button", { name: "载入最新路线" }).click();
  expect((await latestRouteResponse).status()).toBe(200);
});

test("Failed latest-route reload makes the retry explicit without changing the route", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const saved = await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  await selectReplacementCandidate(page, "茶人村");
  await expect(page.getByRole("heading", { name: "换成这里以后，这一段会这样走" })).toBeVisible();

  await page.route("**/api/trips/*/mutation-proposals/*/apply", (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "stale_mutation_proposal", message: "The mutation proposal is based on a stale revision." } }),
  }));
  await page.route(`**/api/trips/${saved.trip.id}`, (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "service_unavailable", message: "Temporary service issue." } }),
  }));

  await page.getByRole("button", { name: "换成这个地点" }).click();
  await expect(page.getByRole("button", { name: "载入最新路线" })).toBeVisible();
  const latestRouteResponse = page.waitForResponse((response) => (
    response.url().endsWith(`/api/trips/${saved.trip.id}`) && response.request().method() === "GET"
  ));
  await page.getByRole("button", { name: "载入最新路线" }).click();
  expect((await latestRouteResponse).status()).toBe(503);

  await expect(page.getByText("暂时无法载入最新路线。当前页面没有改动任何路线。", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新载入最新路线" })).toBeVisible();
  await expect(
    page.locator("[data-roadbook-stop]").filter({ hasText: "湖畔小馆" }).first(),
  ).toBeVisible();

  await page.unroute(`**/api/trips/${saved.trip.id}`);
  const retryResponse = page.waitForResponse((response) => (
    response.url().endsWith(`/api/trips/${saved.trip.id}`) && response.request().method() === "GET"
  ));
  await page.getByRole("button", { name: "重新载入最新路线" }).click();
  expect((await retryResponse).status()).toBe(200);
  const latestRouteReceipt = `已载入最新保存版本 ${saved.current_revision.revision_number}；没有应用刚才的替换。请基于这版路线重新选择地点。`;
  await expect(page.getByText(latestRouteReceipt)).toBeVisible();
  await expect(
    page
      .locator(".erp-repair-feedback")
      .filter({ hasText: latestRouteReceipt }),
  ).toBeFocused();
  assertClean();
});

test("Stale replacement preview lets the traveler load the latest route without changing it", async ({ page }) => {
  const assertClean = installNetworkGate(page, { ignoreConsoleError: isExpectedStaleConflictConsole });
  await page.setViewportSize({ width: 1440, height: 900 });
  const saved = await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);

  let previewRequests = 0;
  let latestRouteReads = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/mutations/preview")) previewRequests += 1;
    if (request.url().endsWith(`/api/trips/${saved.trip.id}`) && request.method() === "GET") latestRouteReads += 1;
  });
  await page.route("**/api/trips/*/mutations/preview", (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "stale_mutation_proposal", message: "The mutation proposal is based on a stale revision." } }),
  }));

  await selectReplacementCandidate(page, "茶人村");
  await expect(page.getByText("路线刚刚发生了变化。这次替换没有保存，原路线保持不变。请基于最新路线重新选择一个地点。")).toBeVisible();
  const latestRouteResponse = page.waitForResponse((response) => (
    response.url().endsWith(`/api/trips/${saved.trip.id}`) && response.request().method() === "GET"
  ));
  await page.getByRole("button", { name: "载入最新路线" }).click();
  expect((await latestRouteResponse).status()).toBe(200);

  const latestRouteReceipt = `已载入最新保存版本 ${saved.current_revision.revision_number}；没有应用刚才的替换。请基于这版路线重新选择地点。`;
  await expect(page.getByText(latestRouteReceipt)).toBeVisible();
  await expect(
    page
      .locator(".erp-repair-feedback")
      .filter({ hasText: latestRouteReceipt }),
  ).toBeFocused();
  expect(latestRouteReads).toBe(1);
  expect(previewRequests).toBe(1);
  assertClean();
});

test("Closing a stale replacement error returns focus to the original route stop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  const originalStop = page.locator("[data-roadbook-stop]").filter({
    has: page.locator(".roadbook-stop__copy > strong").getByText("湖畔小馆", { exact: true }),
  });
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  await page.route("**/api/trips/*/mutations/preview", (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "stale_mutation_proposal", message: "The mutation proposal is based on a stale revision." } }),
  }));

  await selectReplacementCandidate(page, "茶人村");
  await expect(page.getByText("路线刚刚发生了变化。这次替换没有保存，原路线保持不变。请基于最新路线重新选择一个地点。")).toBeVisible();
  await page.getByRole("button", { name: "关闭调整提示" }).click();
  await expect(originalStop).toBeFocused();
});

test("Stale local repair preview lets the traveler load the latest route without changing it", async ({ page }) => {
  const assertClean = installNetworkGate(page, {
    ignoreConsoleError: isExpectedStaleConflictConsole,
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  const saved = await createSavedRoadbook(page);
  const dayButtons = page.locator(".roadbook__masthead nav button");
  const trigger = page.getByRole("button", { name: /让第 \d+ 天轻松一些/ });
  for (let index = 0; index < await dayButtons.count() && await trigger.count() === 0; index += 1) {
    await dayButtons.nth(index).click();
  }
  await expect(trigger).toHaveCount(1);

  let previewRequests = 0;
  let latestRouteReads = 0;
  page.on("request", (request) => {
    if (request.url().includes("/local-repairs/relax-day/preview")) previewRequests += 1;
    if (request.url().endsWith(`/api/trips/${saved.trip.id}`) && request.method() === "GET") latestRouteReads += 1;
  });
  await page.route("**/api/trips/*/local-repairs/relax-day/preview", (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "stale_base_revision", message: "The revision is no longer current." } }),
  }));

  await trigger.click();
  await expect(page.getByText("路线刚刚发生了变化。这次调整没有保存，原路线保持不变。请基于最新版本重新看看调整建议。")).toBeVisible();
  const latestRevisionNumber = saved.current_revision.revision_number + 1;
  await page.route(`**/api/trips/${saved.trip.id}`, async (route) => {
    const response = await route.fetch();
    const latest = await response.json() as SavedRoadbookPayload;
    latest.current_revision.revision_number = latestRevisionNumber;
    const visibleLegs = allRouteItems(latest.itinerary)
      .filter((item) => shouldDisplayTravelLeg(latest.itinerary, item));
    for (const item of visibleLegs) {
      item.travel_data_status = "confirmed";
      item.travel_duration_s ??= 600;
      item.travel_distance_m ??= 1_000;
    }
    const pendingLeg = visibleLegs[0];
    if (!pendingLeg) throw new Error("Expected the latest route to contain a visible travel leg.");
    pendingLeg.travel_data_status = "unavailable";
    pendingLeg.travel_duration_s = null;
    pendingLeg.travel_distance_m = null;
    await route.fulfill({ response, json: latest });
  });
  const latestRouteResponse = page.waitForResponse((response) => (
    response.url().endsWith(`/api/trips/${saved.trip.id}`) && response.request().method() === "GET"
  ));
  await page.getByRole("button", { name: "载入最新路线" }).click();
  expect((await latestRouteResponse).status()).toBe(200);

  const latestRouteReceipt = `已载入最新保存版本 ${latestRevisionNumber}；没有应用刚才的调整。请基于这版路线重新查看当天是否仍然太赶。`;
  await expect(page.getByText(latestRouteReceipt)).toBeVisible();
  await expect(page.locator('[aria-label="路线核验提示"]')).toContainText("有 1 段相邻路线待确认");
  await expect(
    page
      .locator(".erp-repair-feedback")
      .filter({ hasText: latestRouteReceipt }),
  ).toBeFocused();
  expect(latestRouteReads).toBe(1);
  expect(previewRequests).toBe(1);
  assertClean();
});

test("Retrying a local repair after a lost save response replays the same adjustment", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  const { payload } = await previewRushedDayRepair(page);
  const idempotencyKeys: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes(`/mutation-proposals/${payload.proposal.id}/apply`)) {
      idempotencyKeys.push(request.headers()["x-idempotency-key"] ?? "");
    }
  });

  let dropFirstResponse = true;
  await page.route(`**/api/trips/*/mutation-proposals/${payload.proposal.id}/apply`, async (route) => {
    if (!dropFirstResponse) {
      await route.continue();
      return;
    }
    dropFirstResponse = false;
    await route.fetch();
    await route.abort("connectionreset");
  });

  await page.getByRole("button", { name: "应用这次调整" }).click();
  await expect(page.getByText("暂时无法确认这次调整是否已保存。可重试同一项调整；系统会核对这次操作，不会重复创建版本。")).toBeVisible();
  const replayResponse = page.waitForResponse((response) => (
    response.url().includes(`/mutation-proposals/${payload.proposal.id}/apply`)
    && response.request().method() === "POST"
    && idempotencyKeys.length === 2
  ));
  await page.getByRole("button", { name: "重试这次调整" }).click();
  const replay = await replayResponse;
  expect(replay.status()).toBe(200);
  expect((await replay.json() as { persistence: { idempotent_replay: boolean } }).persistence.idempotent_replay).toBe(true);
  expect(idempotencyKeys).toHaveLength(2);
  expect([...new Set(idempotencyKeys)]).toEqual([idempotencyKeys[0]]);
  await expect(page.getByText("这段路线已经松了一点，调整已保存为版本 2。")).toBeVisible();
});

test("A rejected local repair does not present an uncertain-save retry", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  const { payload } = await previewRushedDayRepair(page);
  await page.route(`**/api/trips/*/mutation-proposals/${payload.proposal.id}/apply`, (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "proposal_digest_mismatch", message: "The proposal does not match its digest." } }),
  }));

  await page.getByRole("button", { name: "应用这次调整" }).click();
  await expect(page.getByText("这次调整没有保存。你的原路线仍然保持不变。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试这次调整" })).toHaveCount(0);
});

test("A 422 local repair rejection without a business code does not claim an uncertain save", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  const { payload } = await previewRushedDayRepair(page);
  await page.route(`**/api/trips/*/mutation-proposals/${payload.proposal.id}/apply`, (route) => route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: "这项调整暂时不能应用。" }),
  }));

  await page.getByRole("button", { name: "应用这次调整" }).click();

  await expect(page.getByText("这次调整没有保存。你的原路线仍然保持不变。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试这次调整" })).toHaveCount(0);
  await expect(page.getByText("暂时无法确认这次调整是否已保存。可重试同一项调整；系统会核对这次操作，不会重复创建版本。")).toHaveCount(0);
});

test("A 503 local repair response keeps the safe idempotent retry", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  const { payload } = await previewRushedDayRepair(page);
  await page.route(`**/api/trips/*/mutation-proposals/${payload.proposal.id}/apply`, (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "service_unavailable", message: "Temporary service issue." } }),
  }));

  await page.getByRole("button", { name: "应用这次调整" }).click();

  await expect(page.getByText("暂时无法确认这次调整是否已保存。可重试同一项调整；系统会核对这次操作，不会重复创建版本。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试这次调整" })).toBeVisible();
});

test("Retrying a local repair undo after a lost response replays the same undo", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  const { payload } = await previewRushedDayRepair(page);
  const applied = await applyPreviewedRepair(page, payload.proposal.id);
  const idempotencyKeys: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes(`/revisions/${applied.current_revision.id}/undo`)) {
      idempotencyKeys.push(request.headers()["x-idempotency-key"] ?? "");
    }
  });

  let dropFirstResponse = true;
  await page.route(`**/api/trips/*/revisions/${applied.current_revision.id}/undo`, async (route) => {
    if (!dropFirstResponse) {
      await route.continue();
      return;
    }
    dropFirstResponse = false;
    await route.fetch();
    await route.abort("connectionreset");
  });

  await page.getByRole("button", { name: "撤销刚才的调整" }).click();
  await expect(page.getByText("暂时无法确认这次撤销是否已保存。可重试撤销；系统会核对这次操作，不会重复创建版本。")).toBeVisible();
  const replayResponse = page.waitForResponse((response) => (
    response.url().includes(`/revisions/${applied.current_revision.id}/undo`)
    && response.request().method() === "POST"
    && idempotencyKeys.length === 2
  ));
  await page.getByRole("button", { name: "重试撤销" }).click();
  const replay = await replayResponse;
  expect(replay.status()).toBe(200);
  expect((await replay.json() as { persistence: { idempotent_replay: boolean } }).persistence.idempotent_replay).toBe(true);
  expect(idempotencyKeys).toHaveLength(2);
  expect([...new Set(idempotencyKeys)]).toEqual([idempotencyKeys[0]]);
  await expect(page.getByText("已撤销这次调整，并保存为新版本 3。调整前的路线已恢复。")).toBeVisible();
});

test("A rejected local repair undo does not claim an uncertain result", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  const { payload } = await previewRushedDayRepair(page);
  const applied = await applyPreviewedRepair(page, payload.proposal.id);
  await page.route(`**/api/trips/*/revisions/${applied.current_revision.id}/undo`, (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "idempotency_conflict", message: "The operation key conflicts with a different request." } }),
  }));

  await page.getByRole("button", { name: "撤销刚才的调整" }).click();
  await expect(page.getByText("暂时无法撤销这次调整。当前保存的路线没有改变。")).toBeVisible();
  await expect(page.getByText("暂时无法确认这次撤销是否已保存。可重试撤销；系统会核对这次操作，不会重复创建版本。")).toHaveCount(0);
});

test("A 422 local repair undo rejection without a business code does not claim an uncertain result", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  const { payload } = await previewRushedDayRepair(page);
  const applied = await applyPreviewedRepair(page, payload.proposal.id);
  await page.route(`**/api/trips/*/revisions/${applied.current_revision.id}/undo`, (route) => route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: "这次撤销暂时不能应用。" }),
  }));

  await page.getByRole("button", { name: "撤销刚才的调整" }).click();

  await expect(page.getByText("暂时无法撤销这次调整。当前保存的路线没有改变。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试撤销" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "撤销刚才的调整" })).toBeVisible();
  await expect(page.getByText("暂时无法确认这次撤销是否已保存。可重试撤销；系统会核对这次操作，不会重复创建版本。")).toHaveCount(0);
});

test("A 503 local repair undo response keeps the safe idempotent retry", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  const { payload } = await previewRushedDayRepair(page);
  const applied = await applyPreviewedRepair(page, payload.proposal.id);
  await page.route(`**/api/trips/*/revisions/${applied.current_revision.id}/undo`, (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "service_unavailable", message: "Temporary service issue." } }),
  }));

  await page.getByRole("button", { name: "撤销刚才的调整" }).click();

  await expect(page.getByText("暂时无法确认这次撤销是否已保存。可重试撤销；系统会核对这次操作，不会重复创建版本。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试撤销" })).toBeVisible();
});

test("A stale local repair undo reported in error context loads the latest route instead of retrying", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const saved = await createSavedRoadbook(page);
  const { payload } = await previewRushedDayRepair(page);
  const applied = await applyPreviewedRepair(page, payload.proposal.id);
  await page.route(`**/api/trips/*/revisions/${applied.current_revision.id}/undo`, (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: {
      code: "mutation_command_failed",
      message: "The route changed before this undo could apply.",
      reason_code: "undo_target_not_current",
    } }),
  }));

  await page.getByRole("button", { name: "撤销刚才的调整" }).click();

  await expect(page.getByText("路线刚刚发生了变化。这次撤销没有保存。请载入最新路线确认当前安排。")).toBeVisible();
  await expect(page.getByRole("button", { name: "载入最新路线" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重试撤销" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "撤销刚才的调整" })).toHaveCount(0);

  const latestRouteResponse = page.waitForResponse((response) => (
    response.url().endsWith(`/api/trips/${saved.trip.id}`) && response.request().method() === "GET"
  ));
  await page.getByRole("button", { name: "载入最新路线" }).click();
  expect((await latestRouteResponse).status()).toBe(200);
});

test("Closing a stale local repair error returns focus to that day's repair entry", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const saved = await createSavedRoadbook(page);
  const dayButtons = page.locator(".roadbook__masthead nav button");
  const trigger = page.getByRole("button", { name: /让第 \d+ 天轻松一些/ });
  for (let index = 0; index < await dayButtons.count() && await trigger.count() === 0; index += 1) {
    await dayButtons.nth(index).click();
  }
  await expect(trigger).toHaveCount(1);
  await page.route("**/api/trips/*/local-repairs/relax-day/preview", (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "stale_base_revision", message: "The revision is no longer current." } }),
  }));

  await trigger.click();
  await expect(page.getByText("路线刚刚发生了变化。这次调整没有保存，原路线保持不变。请基于最新版本重新看看调整建议。")).toBeVisible();
  await page.getByRole("button", { name: "关闭调整提示" }).click();
  await expect(trigger).toBeFocused();
});

test("Version history restores a prior route as a new revision and confirms it", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const saved = await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  const previewPayload = await preview.json() as { proposal: { id: string } };
  const applyResponse = page.waitForResponse((response) => response.url().includes(`/mutation-proposals/${previewPayload.proposal.id}/apply`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "换成这个地点" }).click();
  const applied = await applyResponse;
  const appliedPayload = await applied.json() as { current_revision: { revision_number: number } };

  await page.getByRole("button", { name: "版本记录" }).click();
  await expect(page.getByText("恢复版本 1 会创建一个新的版本；当前版本会保留，之后仍可恢复。系统会先核验固定安排、必去地点、可用时间和到达/返程地点；若旧版本会改变其中任一项，当前路线不会变化。")).toBeVisible();
  const revisionDetailResponse = page.waitForResponse((response) => response.url().includes(`/revisions/${saved.current_revision.id}`) && response.request().method() === "GET");
  await page.getByRole("button", { name: "查看当时路线" }).click();
  await revisionDetailResponse;
  await expect(page.getByText("版本 1 的当时路线（只读）")).toBeVisible();
  await expect(page.getByText("这是保存当时的路线快照；出行前仍需核实实时路线与预约状态。")).toBeVisible();
  await page.getByRole("button", { name: "恢复为新版本" }).click();
  await expect(page.getByRole("alertdialog", { name: "确认恢复版本 1" })).toBeVisible();
  await expect(page.getByRole("button", { name: "确认恢复版本 1" })).toBeFocused();
  await page.getByRole("button", { name: "暂不恢复" }).click();
  await expect(page.getByRole("button", { name: "恢复为新版本" })).toBeFocused();
  await page.getByRole("button", { name: "恢复为新版本" }).click();
  await page.route(`**/api/trips/${saved.trip.id}/revisions/${saved.current_revision.id}/restore`, async (route) => {
    const response = await route.fetch();
    const restored = await response.json() as SavedRoadbookPayload;
    const visibleLegs = allRouteItems(restored.itinerary)
      .filter((item) => shouldDisplayTravelLeg(restored.itinerary, item));
    for (const item of visibleLegs) {
      item.travel_data_status = "confirmed";
      item.travel_duration_s ??= 600;
      item.travel_distance_m ??= 1_000;
    }
    const pendingLeg = visibleLegs[0];
    if (!pendingLeg) throw new Error("Expected the restored route to contain a visible travel leg.");
    pendingLeg.travel_data_status = "unavailable";
    pendingLeg.travel_duration_s = null;
    pendingLeg.travel_distance_m = null;
    await route.fulfill({ response, json: restored });
  });
  const restoreResponse = page.waitForResponse((response) => response.url().includes(`/revisions/${saved.current_revision.id}/restore`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "确认恢复版本 1" }).click();
  const restored = await restoreResponse;
  expect(restored.status()).toBe(200);
  const restoredPayload = await restored.json() as { current_revision: { revision_number: number; restored_from_revision_id: string | null } };
  expect(restoredPayload.current_revision.revision_number).toBe(appliedPayload.current_revision.revision_number + 1);
  expect(restoredPayload.current_revision.restored_from_revision_id).toBe(saved.current_revision.id);
  await expect(page.getByText(`已恢复版本 1，并保存为新版本 ${restoredPayload.current_revision.revision_number}。之前的版本仍可恢复。`)).toBeVisible();
  await expect(page.locator('[aria-label="路线核验提示"]')).toContainText("有 1 段相邻路线待确认");
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: `已恢复版本 1，并保存为新版本 ${restoredPayload.current_revision.revision_number}。之前的版本仍可恢复。` }),
  ).toBeFocused();
  assertClean();
});

test("Version history sends a blocked restore back to the current route for a local adjustment", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const saved = await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  const previewPayload = await preview.json() as { proposal: { id: string } };
  const applyResponse = page.waitForResponse((response) => response.url().includes(`/mutation-proposals/${previewPayload.proposal.id}/apply`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "换成这个地点" }).click();
  expect((await applyResponse).status()).toBe(200);

  await page.route(`**/api/trips/${saved.trip.id}/revisions/${saved.current_revision.id}/restore`, async (route) => {
    await route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "restore_would_change_travel_boundary_anchors",
          message: "Restoring this revision would remove or change a current travel boundary anchor.",
          protected_boundary_count: 1,
          protected_boundary_labels: ["到达：上海虹桥站"],
        },
      }),
    });
  });

  await page.getByRole("button", { name: "版本记录" }).click();
  await page.getByRole("button", { name: "恢复为新版本" }).click();
  await page.getByRole("button", { name: "确认恢复版本 1" }).click();
  await expect(page.getByText("无法恢复该版本：它会移除或改变当前路线中的 1 个到达或返程地点（到达：上海虹桥站）。当前路线没有变化。")).toBeVisible();
  await page.getByRole("button", { name: "回到当前路线，查看调整选项" }).click();
  await expect(page.getByRole("region", { name: "已保存的正式路线工作台" })).toBeFocused();
  await expect(page.getByRole("region", { name: "调整这份行程" })).toBeVisible();
  assertClean();
});

test("Saved Roadbook exposes a safe adjustment index before a user hunts through place details", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await createSavedRoadbook(page);
  const adjustmentIndex = page.getByRole("region", { name: "调整这份行程" });
  await expect(adjustmentIndex).toBeVisible();
  await expect(adjustmentIndex).toContainText("固定安排、必去地点和时间边界不会被这些调整改动。");
  const adjustmentToggle = adjustmentIndex.locator("summary");
  const replaceEntry = adjustmentIndex.getByRole("button", { name: "检查「湖畔小馆」能否安全替换" });
  await expect(replaceEntry).not.toBeVisible();
  await adjustmentToggle.click();
  const previewRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("preview-completion-task-candidates") || request.url().includes("local-repairs/relax-day/preview")) {
      previewRequests.push(request.url());
    }
  });

  await replaceEntry.click();

  await expect(page.getByRole("button", { name: "换一个" })).toBeFocused();
  expect(previewRequests).toEqual([]);

  await adjustmentIndex.getByRole("button", { name: /查看第 \d+ 天的放松方案/ }).click();
  await expect(page.getByRole("button", { name: /让第 \d+ 天轻松一些/ })).toBeFocused();
  expect(previewRequests).toEqual([]);
  assertClean();
});

test("Safe replacement remains usable and undoable on mobile", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 390, height: 844 });
  const saved = await createSavedRoadbook(page);
  await openSafeReplaceCandidates(page, "湖畔小馆", 2);
  await page.locator(".safe-replace--candidates").scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(REPLACE_QUALITY_SCREENSHOT_DIRECTORY, "mobile-replace-quality-candidates.png") });

  const previewResponse = page.waitForResponse((response) => response.url().includes("/mutations/preview") && response.request().method() === "POST");
  await selectReplacementCandidate(page, "茶人村");
  const preview = await previewResponse;
  expect(preview.status()).toBe(200);
  const previewPayload = await preview.json() as { proposal: { id: string }; current_revision: { id: string; revision_number: number } };
  await page.locator(".safe-replace--preview").scrollIntoViewIfNeeded();
  await expect(page.getByText("保持不变", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(REPLACE_SCREENSHOT_DIRECTORY, "mobile-replace-preview.png") });

  const applyResponse = page.waitForResponse((response) => response.url().includes(`/mutation-proposals/${previewPayload.proposal.id}/apply`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "换成这个地点" }).click();
  const appliedResponse = await applyResponse;
  expect(appliedResponse.status()).toBe(200);
  const applied = await appliedResponse.json() as { current_revision: { id: string; revision_number: number; source_type: string } };
  await expect(page.getByText(`这个地点已经从湖畔小馆换成茶人村，并保存为版本 ${applied.current_revision.revision_number}。其他已经确认的安排没有被改动。`)).toBeVisible();
  await expect(page.locator("[data-roadbook-selected-place]").getByText("茶人村", { exact: true })).toBeVisible();
  await page.locator(".erp-repair-feedback").scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(REPLACE_SCREENSHOT_DIRECTORY, "mobile-replace-applied.png") });

  const undoResponse = page.waitForResponse((response) => response.url().includes(`/revisions/${applied.current_revision.id}/undo`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "撤销刚才的替换" }).click();
  const undoneResponse = await undoResponse;
  expect(undoneResponse.status()).toBe(200);
  const undone = await undoneResponse.json() as { current_revision: { revision_number: number; source_type: string; restored_from_revision_id: string | null } };
  expect(undone.current_revision.revision_number).toBe(applied.current_revision.revision_number + 1);
  expect(undone.current_revision.source_type).toBe("mutation_undo");
  expect(undone.current_revision.restored_from_revision_id).toBe(previewPayload.current_revision.id);
  await expect(page.getByText(`已撤销这次替换，并保存为新版本 ${undone.current_revision.revision_number}。原来的地点和相邻路线已恢复。`)).toBeVisible();
  await expect(page.locator("[data-roadbook-selected-place]").getByText("湖畔小馆", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  await expect(page.getByText("湖畔小馆", { exact: true }).first()).toBeVisible();
  const beforeEmpty = await currentRevision(page, saved.trip.id);
  await openSafeReplaceCandidates(page, "青芝坞餐厅", 0);
  await page.locator(".safe-replace--candidates").scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(REPLACE_QUALITY_SCREENSHOT_DIRECTORY, "mobile-replace-quality-empty.png") });
  await page.getByRole("button", { name: "保留原地点" }).click();
  expect((await currentRevision(page, saved.trip.id)).id).toBe(beforeEmpty.id);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect((await currentRevision(page, saved.trip.id)).revision_number).toBe(undone.current_revision.revision_number);
  assertClean();
});

test("Meal Gap preserves a fixed lunch-time arrangement on desktop", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const saved = await createSavedRoadbook(page, MEAL_GAP_TRIP);
  const day = saved.itinerary.days.find((candidate) => candidate.day === 1);
  const fixed = day?.blocks.flatMap((block) => block.items).find((item) => item.is_fixed);
  const lunch = saved.itinerary.meal_rhythm?.days
    .find((candidate) => candidate.day === 1)?.slots
    .find((slot) => slot.role === "lunch");

  expect(fixed?.name).toContain("中国茶叶博物馆");
  expect(fixed?.start_time).toMatch(/^13:00/);
  expect(fixed?.end_time).toMatch(/^15:00/);
  expect(lunch?.status).toBe("unresolved");
  expect(day?.blocks.flatMap((block) => block.items).some((item) => item.meal_role === "lunch")).toBe(false);
  await page.locator(".roadbook__masthead nav button").first().click();
  const mealGapNote = page.getByRole("heading", { name: "午饭还没找到合适的位置。" });
  await expect(mealGapNote).toBeVisible();
  await expect(page.getByText("不会被随意移动")).toBeVisible();
  await mealGapNote.scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(MEAL_SCREENSHOT_DIRECTORY, "desktop-meal-gap.png") });
  await page.reload();
  await expect(page.getByRole("heading", { name: "午饭还没找到合适的位置。" })).toBeVisible();
  assertClean();
});

test("Meal Gap remains readable and persistent on mobile", async ({ page }) => {
  const assertClean = installNetworkGate(page);
  await page.setViewportSize({ width: 390, height: 844 });
  const saved = await createSavedRoadbook(page, MEAL_GAP_TRIP);
  const daySummary = saved.itinerary.meal_rhythm?.days.find((candidate) => candidate.day === 1);
  expect(daySummary?.slots.find((slot) => slot.role === "lunch")?.status).toBe("unresolved");
  await page.locator(".roadbook__masthead nav button").first().click();
  const note = page.getByRole("heading", { name: "午饭还没找到合适的位置。" });
  await expect(note).toBeVisible();
  await note.scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(MEAL_SCREENSHOT_DIRECTORY, "mobile-meal-gap.png") });
  await page.reload();
  await expect(page.getByRole("heading", { name: "午饭还没找到合适的位置。" })).toBeVisible();
  assertClean();
});
