import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

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

async function previewRushedDayRepair(page: import("@playwright/test").Page) {
  const dayButtons = page.locator(".roadbook__masthead nav button");
  const trigger = page.getByRole("button", { name: /帮我松一点/ });
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
  await expect(page.getByRole("heading", { name: "换一个更适合你的地点" })).toBeVisible();
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
  await desktopDetail.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(ROADBOOK_SCREENSHOT_DIRECTORY, "desktop-roadbook-selected-place.png") });
  await desktopDetail.getByRole("button", { name: /查看下一站/ }).click();
  await expect(desktopStops.nth(2)).toHaveAttribute("aria-pressed", "true");

  const { payload: repairPreview, proof } = await previewRushedDayRepair(page);
  await expect(page.locator(".roadbook__timeline").getByText(repairPreview.impact_summary.local_repair.stop_name, { exact: true })).toBeVisible();
  await proof.evaluate((element) => element.scrollIntoView({ block: "start" }));
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: join(REPAIR_SCREENSHOT_DIRECTORY, "desktop-repair-preview.png") });
  const applied = await applyPreviewedRepair(page, repairPreview.proposal.id);
  expect(applied.current_revision.revision_number).toBe(repairPreview.current_revision.revision_number + 1);
  expect(applied.current_revision.parent_revision_id).toBe(repairPreview.current_revision.id);
  expect(applied.current_revision.source_type).toBe("route_edit");
  await expect(page.getByText("这段路线已经松了一点，调整也已经保存。")).toBeVisible();
  await expect(
    page
      .locator(".erp-repair-feedback")
      .filter({ hasText: "这段路线已经松了一点，调整也已经保存。" }),
  ).toBeFocused();
  await expect(page.getByRole("button", { name: "撤销刚才的调整" })).toBeVisible();
  await expect(page.locator(".roadbook__timeline").getByText(repairPreview.impact_summary.local_repair.stop_name, { exact: true })).toHaveCount(0);
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
  await expect(page.getByText("这段路线已经松了一点，调整也已经保存。")).toBeVisible();
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
  await expect(page.getByText("已恢复调整前的路线。")).toBeVisible();
  await expect(
    page
      .locator(".erp-repair-feedback")
      .filter({ hasText: "已恢复调整前的路线。" }),
  ).toBeFocused();
  await expect(
    page
      .locator(".erp-repair-feedback")
      .filter({ hasText: "已恢复调整前的路线。" }),
  ).toContainText("ROUTE RESTORED");
  await expect(page.locator(".roadbook__timeline").getByText(repairPreview.impact_summary.local_repair.stop_name, { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  await page.locator(".roadbook__masthead nav button").nth(repairPreview.impact_summary.local_repair.from_day - 1).click();
  await expect(page.locator(".roadbook__timeline").getByText(repairPreview.impact_summary.local_repair.stop_name, { exact: true })).toBeVisible();
  assertClean();
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
