import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

type IntentRevisionRow = {
  id: string;
  revision_number: number;
  parent_draft_intent_revision_id: string | null;
  envelope: Record<string, any>;
};

type DraftDatabaseSnapshot = {
  draft_version: number;
  intent_revisions: IntentRevisionRow[];
  trip_revisions: TripRevisionRow[];
  trip_revision_count: number;
  preview_count: number;
  planning_run_count: number;
};

type TripRevisionRow = {
  id: string;
  revision_number: number;
  parent_revision_id: string | null;
  source_type: string;
  snapshot: Record<string, any>;
};

type ErrorGate = {
  allowExpectedInitialIntentAbsence: () => void;
  allowExpectedNetworkFailure: () => void;
  allowExpectedProviderUnavailable: () => void;
  allowExpectedStaleConflict: () => void;
  allowExpectedRouteSegmentAbort: () => void;
  assertClean: () => void;
};

const viewportCases = [
  { name: "desktop", viewport: { width: 1440, height: 900 } },
  { name: "tablet", viewport: { width: 768, height: 1024 } },
  { name: "mobile", viewport: { width: 390, height: 844 } },
] as const;

for (const viewportCase of viewportCases) {
  test(`Scenario A: edits critical fields in ${viewportCase.name}`, async ({ page }) => {
    await page.setViewportSize(viewportCase.viewport);
    const gate = installErrorGate(page);
    gate.allowExpectedInitialIntentAbsence();
    const tripId = await createDraftThroughHome(page, "周末去杭州玩两天，轻松一点。");

    const overview = page.getByRole("region", { name: "已理解" });
    await expect(overview).toContainText("杭州");
    await expect(overview).toContainText("2 天");
    await expect(overview).toContainText("轻松");
    const initialSnapshot = readDraftDatabase(tripId);

    await page.getByRole("button", { name: "修改旅行时间" }).click();
    await page.getByRole("button", { name: "按旅行天数" }).click();
    await page.getByLabel("旅行天数").fill("3");
    const dayEdit = page.waitForResponse(isDraftIntentEditResponse);
    await page.getByRole("button", { name: "保存修改" }).click();
    expect((await dayEdit).status()).toBe(201);
    await expect(overview).toContainText("3 天");

    await page.getByRole("button", { name: "修改旅行节奏" }).click();
    await page.getByRole("combobox", { name: "旅行节奏" }).selectOption("balanced");
    const paceEdit = page.waitForResponse(isDraftIntentEditResponse);
    await page.getByRole("button", { name: "保存修改" }).click();
    expect((await paceEdit).status()).toBe(201);
    await expect(overview).toContainText("适中");
    await expect(page.getByRole("heading", { name: "确认行程信息" })).toBeVisible();
    await expect(page.getByText("field_path", { exact: false })).toHaveCount(0);
    await assertViewportFits(page);

    const snapshot = readDraftDatabase(tripId);
    expect(snapshot.intent_revisions).toHaveLength(3);
    expect(snapshot.draft_version - initialSnapshot.draft_version).toBe(2);
    expect(snapshot.intent_revisions.map((row) => row.revision_number)).toEqual([1, 2, 3]);
    expect(snapshot.intent_revisions[0].parent_draft_intent_revision_id).toBeNull();
    expect(snapshot.intent_revisions[1].parent_draft_intent_revision_id).toBe(snapshot.intent_revisions[0].id);
    expect(snapshot.intent_revisions[2].parent_draft_intent_revision_id).toBe(snapshot.intent_revisions[1].id);
    expect(datePolicy(snapshot.intent_revisions[0]).trip_days).toBe(2);
    expect(pace(snapshot.intent_revisions[0])).toBe("relaxed");
    expect(datePolicy(snapshot.intent_revisions[2]).trip_days).toBe(3);
    expect(pace(snapshot.intent_revisions[2])).toBe("balanced");
    expect(snapshot.trip_revision_count).toBe(0);
    expect(snapshot.preview_count).toBe(0);
    gate.assertClean();
  });

  test(`Scenario B: resolves missing destination in ${viewportCase.name}`, async ({ page }) => {
    await page.setViewportSize(viewportCase.viewport);
    const gate = installErrorGate(page);
    gate.allowExpectedInitialIntentAbsence();
    const tripId = await createDraftThroughHome(page, "周末玩两天，轻松一点。");
    const overview = page.getByRole("region", { name: "已理解" });
    const clarification = page.getByRole("region", { name: "还需确认" });
    const primary = page.locator("#preplan-primary-action");

    await expect(clarification.getByText("请填写这次旅行的目的地")).toBeVisible();
    await expect(primary).toBeDisabled();
    const beforeResolution = readDraftDatabase(tripId);
    await clarification.getByRole("textbox", { name: "目的地" }).fill("杭州");
    const resolved = page.waitForResponse(isClarificationResponse);
    await clarification.getByRole("button", { name: "确认" }).click();
    expect((await resolved).status()).toBe(201);
    await expect(clarification).toHaveCount(0);
    await expect(overview).toContainText("杭州");
    await expect(primary).toBeEnabled();
    await expect(page.getByText("missing_destination", { exact: false })).toHaveCount(0);
    if (viewportCase.name === "mobile") {
      await page.getByRole("button", { name: "修改目的地" }).click();
      await expect(page.getByRole("textbox", { name: "目的地" })).toBeFocused();
    }
    await assertViewportFits(page);

    const snapshot = readDraftDatabase(tripId);
    expect(snapshot.intent_revisions).toHaveLength(2);
    expect(snapshot.draft_version - beforeResolution.draft_version).toBe(1);
    expect(destinations(snapshot.intent_revisions[0])).toEqual([]);
    expect(destinations(snapshot.intent_revisions[1])).toEqual(["杭州"]);
    expect(activeClarifications(snapshot.intent_revisions[1])).not.toContain("clarify_trip_city");
    expect(snapshot.intent_revisions[1].parent_draft_intent_revision_id).toBe(snapshot.intent_revisions[0].id);
    expect(snapshot.trip_revision_count).toBe(0);
    expect(snapshot.preview_count).toBe(0);
    gate.assertClean();
  });
}

test("Scenario C: preserves a stale edit and manually reapplies it on desktop", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const pageA = await context.newPage();
  const gateA = installErrorGate(pageA);
  gateA.allowExpectedInitialIntentAbsence();
  const tripId = await createDraftThroughHome(pageA, "周末去杭州玩两天，轻松一点。");
  const pageB = await context.newPage();
  const gateB = installErrorGate(pageB);
  await pageB.goto("/");
  await expect(pageB.getByRole("heading", { name: "确认行程信息" })).toBeVisible();
  const overviewA = pageA.getByRole("region", { name: "已理解" });
  const overviewB = pageB.getByRole("region", { name: "已理解" });
  const initialSnapshot = readDraftDatabase(tripId);

  await pageB.getByRole("button", { name: "修改旅行节奏" }).click();
  await pageB.getByRole("combobox", { name: "旅行节奏" }).selectOption("balanced");
  await pageA.getByRole("button", { name: "修改旅行时间" }).click();
  await pageA.getByRole("button", { name: "按旅行天数" }).click();
  await pageA.getByLabel("旅行天数").fill("3");
  const firstEdit = pageA.waitForResponse(isDraftIntentEditResponse);
  await pageA.getByRole("button", { name: "保存修改" }).click();
  expect((await firstEdit).status()).toBe(201);
  await expect(overviewA).toContainText("3 天");

  const beforeStale = readDraftDatabase(tripId);
  gateB.allowExpectedStaleConflict();
  const staleEdit = pageB.waitForResponse(isDraftIntentEditResponse);
  await pageB.getByRole("button", { name: "保存修改" }).click();
  expect((await staleEdit).status()).toBe(409);
  const dialog = pageB.getByRole("dialog", { name: "行程信息已经在其他页面更新" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toBeFocused();
  await expect(dialog).toContainText("3 天");
  await expect(dialog).toContainText("旅行节奏：适中");
  await expect(pageB.getByRole("combobox", { name: "旅行节奏" })).toHaveValue("balanced");
  expect(readDraftDatabase(tripId).intent_revisions).toHaveLength(beforeStale.intent_revisions.length);

  await dialog.getByRole("button", { name: "查看最新内容" }).click();
  await expect(overviewB).toContainText("3 天");
  await expect(dialog).toBeVisible();
  const reapply = pageB.waitForResponse(isDraftIntentEditResponse);
  await dialog.getByRole("button", { name: "重新应用我的修改" }).click();
  expect((await reapply).status()).toBe(201);
  await expect(overviewB).toContainText("适中");
  await expect(dialog).toHaveCount(0);
  await expect(pageB.getByRole("button", { name: "生成路线预览" })).toBeFocused();
  await assertViewportFits(pageB);

  const snapshot = readDraftDatabase(tripId);
  expect(snapshot.intent_revisions).toHaveLength(3);
  expect(snapshot.draft_version - initialSnapshot.draft_version).toBe(2);
  expect(datePolicy(snapshot.intent_revisions[2]).trip_days).toBe(3);
  expect(pace(snapshot.intent_revisions[2])).toBe("balanced");
  expect(snapshot.intent_revisions[2].parent_draft_intent_revision_id).toBe(snapshot.intent_revisions[1].id);
  expect(new Set(snapshot.intent_revisions.map((row) => row.parent_draft_intent_revision_id).filter(Boolean)).size).toBe(2);
  expect(snapshot.trip_revision_count).toBe(0);
  expect(snapshot.preview_count).toBe(0);
  gateA.assertClean();
  gateB.assertClean();
  await context.close();
});

test("Scenario D: retries a lost edit response with the original idempotency key", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const gate = installErrorGate(page);
  gate.allowExpectedInitialIntentAbsence();
  const tripId = await createDraftThroughHome(page, "周末去杭州玩两天，轻松一点。");
  const droppedResponse: { value: Record<string, unknown> | null } = { value: null };
  let hasDroppedResponse = false;
  gate.allowExpectedNetworkFailure();
  await page.route("**/api/trips/*/preplan-intent/edits", async (route) => {
    if (!hasDroppedResponse) {
      hasDroppedResponse = true;
      const response = await route.fetch();
      droppedResponse.value = await response.json() as Record<string, unknown>;
      await route.abort("connectionreset");
      return;
    }
    await route.continue();
  });

  await page.getByRole("button", { name: "修改旅行时间" }).click();
  await page.getByRole("button", { name: "按旅行天数" }).click();
  await page.getByLabel("旅行天数").fill("3");
  const initialSnapshot = readDraftDatabase(tripId);
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(page.getByText("暂时无法确认这项修改是否已保存。可重新提交；系统会核对这次修改，不会重复创建版本。")).toHaveCount(1);
  await expect(page.getByLabel("旅行天数")).toHaveValue("3");
  expect(droppedResponse.value?.idempotent_replay).toBe(false);
  const afterLostResponse = readDraftDatabase(tripId);
  expect(afterLostResponse.intent_revisions).toHaveLength(2);

  const replay = page.waitForResponse(isDraftIntentEditResponse);
  await page.getByRole("button", { name: "重新提交" }).click();
  const replayPayload = await (await replay).json() as Record<string, unknown>;
  expect(replayPayload.idempotent_replay).toBe(true);
  await expect(page.getByText("已确认这项修改已经保存。")).toBeVisible();
  expect(readDraftDatabase(tripId).intent_revisions).toHaveLength(2);
  expect(readDraftDatabase(tripId).draft_version - initialSnapshot.draft_version).toBe(1);
  gate.assertClean();
});

test("Scenario D: retries a 503 edit response with the original idempotency key", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const gate = installErrorGate(page);
  gate.allowExpectedInitialIntentAbsence();
  gate.allowExpectedProviderUnavailable();
  const tripId = await createDraftThroughHome(page, "周末去杭州玩两天，轻松一点。");
  const initialSnapshot = readDraftDatabase(tripId);
  let firstResponse = true;
  await page.route("**/api/trips/*/preplan-intent/edits", async (route) => {
    if (!firstResponse) {
      await route.continue();
      return;
    }
    firstResponse = false;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "service_unavailable", message: "Temporary service issue." } }),
    });
  });

  await page.getByRole("button", { name: "修改旅行时间" }).click();
  await page.getByRole("button", { name: "按旅行天数" }).click();
  await page.getByLabel("旅行天数").fill("3");
  const failedSave = page.waitForResponse(isDraftIntentEditResponse);
  await page.getByRole("button", { name: "保存修改" }).click();
  expect((await failedSave).status()).toBe(503);

  await expect(page.getByText("暂时无法确认这项修改是否已保存。可重新提交；系统会核对这次修改，不会重复创建版本。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重新提交" })).toBeVisible();
  expect(readDraftDatabase(tripId).intent_revisions).toHaveLength(initialSnapshot.intent_revisions.length);

  const replay = page.waitForResponse(isDraftIntentEditResponse);
  await page.getByRole("button", { name: "重新提交" }).click();
  expect((await replay).status()).toBe(201);
  await expect(page.getByText("已更新行程信息。")).toBeVisible();
  expect(readDraftDatabase(tripId).intent_revisions).toHaveLength(initialSnapshot.intent_revisions.length + 1);
  gate.assertClean();
});

test("Scenario E: keeps a provider-unavailable place unconfirmed and retries safely", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const gate = installErrorGate(page);
  gate.allowExpectedInitialIntentAbsence();
  gate.allowExpectedProviderUnavailable();
  const tripId = await createDraftThroughHome(page, "去杭州玩两天，想去西湖。");
  const before = readDraftDatabase(tripId);
  let hasReturnedProviderOutage = false;
  await page.route("**/api/trips/*/preplan-intent/edits", async (route) => {
    if (hasReturnedProviderOutage) {
      await route.continue();
      return;
    }
    hasReturnedProviderOutage = true;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "place_identity_provider_unavailable",
          message: "Place identity provider is temporarily unavailable.",
          recoverable: true,
        },
      }),
    });
  });

  const unavailable = page.waitForResponse(isDraftIntentEditResponse);
  await page.getByRole("button", { name: "采用这个地点" }).click();
  expect((await unavailable).status()).toBe(503);
  await expect(page.getByText("地点服务暂时不可用，当前地点尚未确认。")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "采用这个地点" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新提交" })).toBeVisible();
  expect(readDraftDatabase(tripId).intent_revisions).toHaveLength(before.intent_revisions.length);
  expect(readDraftDatabase(tripId).draft_version).toBe(before.draft_version);

  const retry = page.waitForResponse(isDraftIntentEditResponse);
  await page.getByRole("button", { name: "重新提交" }).click();
  expect((await retry).status()).toBe(201);
  await expect(page.getByText("已更新行程信息。")).toBeVisible();
  expect(readDraftDatabase(tripId).intent_revisions).toHaveLength(before.intent_revisions.length + 1);
  expect(readDraftDatabase(tripId).draft_version).toBe(before.draft_version + 1);
  gate.assertClean();
});

for (const viewportCase of [
  { name: "desktop", viewport: { width: 1440, height: 900 } },
  { name: "mobile", viewport: { width: 390, height: 844 } },
] as const) {
test(`Scenario E: confirms canonical places before creating one existing Planning Run in ${viewportCase.name}`, async ({ page }) => {
  await page.setViewportSize(viewportCase.viewport);
  const gate = installErrorGate(page);
  // Saving replaces the candidate preview with the persisted Roadbook and cancels
  // only the obsolete in-flight route-segment request from the unmounted preview.
  gate.allowExpectedRouteSegmentAbort();
  const legacyPreviewRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/preplan-handoff/preview")) legacyPreviewRequests.push(request.url());
  });
  const tripId = await createTripCompilerDraft(page, "去杭州玩两天，轻松一点，想去西湖、灵隐寺和龙井村。第二天下午两点到四点预约了中国茶叶博物馆，最后一天傍晚六点前结束。");
  const before = readDraftDatabase(tripId);
  expect(before.intent_revisions).toHaveLength(1);
  await expect(page.getByRole("button", { name: /西湖风景名胜区/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^灵隐寺/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^龙井村/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /中国茶叶博物馆（双峰馆区）/ })).toBeVisible();

  const westLakeConfirmation = page.waitForResponse(isDraftIntentEditResponse);
  await page.getByRole("button", { name: /西湖风景名胜区/ }).click();
  expect((await westLakeConfirmation).status()).toBe(201);
  const lingyinConfirmation = page.waitForResponse(isDraftIntentEditResponse);
  await page.getByRole("button", { name: /^灵隐寺/ }).click();
  expect((await lingyinConfirmation).status()).toBe(201);
  const longjingConfirmation = page.waitForResponse(isDraftIntentEditResponse);
  await page.getByRole("button", { name: /^龙井村/ }).click();
  expect((await longjingConfirmation).status()).toBe(201);
  const teaMuseumConfirmation = page.waitForResponse(isDraftIntentEditResponse);
  await page.getByRole("button", { name: /中国茶叶博物馆（双峰馆区）/ }).click();
  expect((await teaMuseumConfirmation).status()).toBe(201);
  await expect(page.getByRole("button", { name: "生成我的路线" })).toBeEnabled();

  const confirmed = readDraftDatabase(tripId);
  expect(confirmed.intent_revisions).toHaveLength(5);
  expect(confirmed.intent_revisions[1].parent_draft_intent_revision_id).toBe(before.intent_revisions[0].id);
  expect(confirmed.intent_revisions[2].parent_draft_intent_revision_id).toBe(confirmed.intent_revisions[1].id);
  expect(confirmed.intent_revisions[4].parent_draft_intent_revision_id).toBe(confirmed.intent_revisions[3].id);
  expect(confirmed.intent_revisions[4].envelope.planner_ready_status).toMatch(/ready/);
  expect(confirmed.intent_revisions[4].envelope.formal_contract.place_identities.map((item: { resolution_status: string }) => item.resolution_status)).toEqual(["verified", "verified", "verified", "verified"]);
  const confirmedIdentityIds = confirmed.intent_revisions[4].envelope.formal_contract.place_identities
    .map((item: { stable_id: string }) => item.stable_id);
  const fixedIdentity = confirmed.intent_revisions[4].envelope.formal_contract.place_identities
    .find((item: { ownership: string }) => item.ownership === "fixed");
  expect(fixedIdentity).toBeDefined();
  const confirmedFixedEvents = confirmed.intent_revisions[4].envelope.formal_contract.fixed_events;
  expect(
    confirmedFixedEvents,
    JSON.stringify({
      fixedEvents: confirmedFixedEvents,
      identities: confirmed.intent_revisions[4].envelope.formal_contract.place_identities,
    }),
  ).toHaveLength(1);
  expect(confirmedFixedEvents[0]).toMatchObject({
    event_id: fixedIdentity.stable_id,
    fixed_day: 2,
    fixed_time_start: "14:00",
    fixed_time_end: "16:00",
  });

  const runResponse = page.waitForResponse((response) => response.url().includes("/preplan-intent/planning-run") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成我的路线" }).click();
  const planningResponse = await runResponse;
  expect(planningResponse.status(), await planningResponse.text()).toBe(200);
  const planningPayload = await planningResponse.json();
  const candidateItems = flattenedItems(planningPayload.candidates[0].itinerary);
  expect(
    candidateItems.map((item) => item.canonical_place_id),
    JSON.stringify(candidateItems.map((item) => ({
      name: item.name,
      stable_id: item.stable_id,
      canonical_place_id: item.canonical_place_id,
      is_fixed: item.is_fixed,
    }))),
  ).toContain("fixture-china-tea-museum");
  await expect(page.getByRole("heading", { name: "路线怎么不同，一眼就能看懂。" })).toBeVisible();
  const after = readDraftDatabase(tripId);
  expect(after.planning_run_count).toBe(before.planning_run_count + 1);
  expect(after.trip_revision_count).toBe(0);
  expect(legacyPreviewRequests).toEqual([]);
  const saveRoute = page.waitForResponse((response) => response.url().includes("/planning-runs/") && response.url().includes("/candidates/") && response.url().includes("/select") && response.request().method() === "POST");
  await page.getByRole("button", { name: "就选这条路线" }).click();
  const savedResponse = await saveRoute;
  expect(savedResponse.status()).toBe(201);
  const savedPayload = await savedResponse.json() as { trip: { id: string } };
  const savedRoadbook = page.getByRole("region", { name: "可执行路线预览" });
  await expect(savedRoadbook).toBeVisible();
  await savedRoadbook.getByRole("button", { name: "DAY 02" }).click();
  await expect(savedRoadbook.getByText("14 分钟 · 1.1 公里").first()).toBeVisible();
  await page.screenshot({ path: `test-results/intent/round26.1-hangzhou-${viewportCase.name}.png`, fullPage: true });
  const saved = readDraftDatabase(savedPayload.trip.id);
  expect(saved.trip_revisions).toHaveLength(1);
  const snapshotItems = flattenedItems(saved.trip_revisions[0].snapshot);
  expect(snapshotItems.map((item) => item.stable_id), JSON.stringify(snapshotItems.map((item) => ({ name: item.name, stable_id: item.stable_id, canonical_place_id: item.canonical_place_id, is_fixed: item.is_fixed })))).toEqual(expect.arrayContaining(confirmedIdentityIds));
  expect(snapshotItems.map((item) => item.canonical_place_id)).toEqual(expect.arrayContaining(["fixture-west-lake", "fixture-lingyin-temple", "fixture-longjing-village", "fixture-china-tea-museum"]));
  expect(snapshotItems.some((item) => item.travel_data_status === "confirmed" && item.travel_duration_s === 840 && item.travel_distance_m === 1100)).toBe(true);
  await assertViewportFits(page);
  gate.assertClean();
});
}

test("Scenario F: previews and applies a local relaxation without regenerating the saved route", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const gate = installErrorGate(page);
  // The replaced route workspace cancels its in-flight map segment preview.
  // The route preview and mutation APIs remain subject to the normal error gate.
  gate.allowExpectedRouteSegmentAbort();
  await createTripCompilerDraft(page, "去杭州玩三天，节奏轻松一点，想去西湖、灵隐寺和龙井村。第二天下午两点到四点预约了中国茶叶博物馆，不能改。");
  const choices = page.locator(".tc-place-options button");
  while (await choices.count()) {
    const confirmed = page.waitForResponse(isDraftIntentEditResponse);
    await choices.first().click();
    expect((await confirmed).status()).toBe(201);
  }
  const planned = page.waitForResponse((response) => response.url().includes("/preplan-intent/planning-run") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成我的路线" }).click();
  expect((await planned).status()).toBe(200);
  const save = page.waitForResponse((response) => response.url().includes("/planning-runs/") && response.url().includes("/candidates/") && response.url().includes("/select") && response.request().method() === "POST");
  await page.getByRole("button", { name: "就选这条路线" }).click();
  const savedPayload = await (await save).json() as { trip: { id: string } };
  const tripId = savedPayload.trip.id;

  const routePreview = page.getByRole("region", { name: "可执行路线预览" });
  await expect(routePreview.getByText("LIVING ROADBOOK / SAVED ROUTE")).toBeVisible();
  const dayButtons = routePreview.getByRole("navigation", { name: "选择行程日期" }).getByRole("button");
  const relaxButton = routePreview.getByRole("button", { name: /让第 \d+ 天轻松一些/ });
  for (let index = 0; index < await dayButtons.count() && await relaxButton.count() === 0; index += 1) {
    await dayButtons.nth(index).click();
  }
  await expect(routePreview.getByRole("heading", { name: "今天稍微赶了一点。" })).toBeVisible();
  await expect(relaxButton).toBeVisible();
  const beforeRepair = readDraftDatabase(tripId);
  expect(beforeRepair.trip_revisions).toHaveLength(1);
  expect(flattenedItems(beforeRepair.trip_revisions[0].snapshot).some((item) => (
    !item.is_fixed && ["auto_seeded_poi", "auto_filled", "auto_seeded_meal"].includes(String(item.source_type))
  ))).toBe(true);

  const previewRepair = page.waitForResponse((response) => response.url().includes("/local-repairs/relax-day/preview") && response.request().method() === "POST");
  await relaxButton.click();
  expect((await previewRepair).status()).toBe(200);
  const review = page.getByRole("region", { name: "我们建议只调整这一段" });
  await expect(review).toContainText(/把“.+”从第 \d+ 天挪到第 \d+ 天/);
  await expect(review.getByText("固定安排和你明确想去的地点不会被随意移动。")).toBeVisible();
  const move = (await review.textContent())?.match(/把“(.+)”从第 (\d+) 天挪到第 (\d+) 天/);
  const movedStop = move?.[1];
  const fromDay = Number(move?.[2]);
  const toDay = Number(move?.[3]);
  expect(movedStop).toBeTruthy();
  expect(fromDay).toBeGreaterThan(0);
  expect(toDay).toBeGreaterThan(0);

  const applyRepair = page.waitForResponse((response) => response.url().includes("/mutation-proposals/") && response.url().includes("/apply") && response.request().method() === "POST");
  await review.getByRole("button", { name: "应用这次调整" }).click();
  expect((await applyRepair).status()).toBe(200);
  await expect(review).toHaveCount(0);

  const afterRepair = readDraftDatabase(tripId);
  expect(afterRepair.planning_run_count).toBe(beforeRepair.planning_run_count);
  expect(afterRepair.trip_revisions).toHaveLength(2);
  expect(afterRepair.trip_revisions.map((revision) => revision.revision_number)).toEqual([1, 2]);
  expect(afterRepair.trip_revisions[1].source_type).toBe("route_edit");
  expect(afterRepair.trip_revisions[1].parent_revision_id).toBe(afterRepair.trip_revisions[0].id);
  expect(flattenedStopNames(afterRepair.trip_revisions[0].snapshot)).toContain(movedStop);
  expect(dayStopNames(afterRepair.trip_revisions[1].snapshot, fromDay)).not.toContain(movedStop);
  expect(dayStopNames(afterRepair.trip_revisions[1].snapshot, toDay)).toContain(movedStop);
  await assertViewportFits(page);
  gate.assertClean();
});

test("Scenario G: blocks an unresolved fixed reservation before any route request", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const gate = installErrorGate(page);
  const blockedRouteRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/preplan-handoff/preview") || request.url().includes("/preplan-intent/planning-run")) {
      blockedRouteRequests.push(request.url());
    }
  });
  const planningRunsBefore = readPlanningRunCount();
  const tripId = await createTripCompilerDraft(page, "去上海三天，第二天下午2点到4点预约了上海博物馆。");

  await expect(page.getByText("固定安排“上海博物馆”的地点还需要确认。")).toBeVisible();
  await expect(page.getByRole("button", { name: "生成我的路线" })).toBeDisabled();
  await expect(page.getByRole("button", { name: /上海博物馆（人民广场馆）/ })).toBeVisible();
  const snapshot = readDraftDatabase(tripId);
  expect(snapshot.planning_run_count).toBe(planningRunsBefore);
  expect(snapshot.trip_revision_count).toBe(0);
  expect(blockedRouteRequests).toEqual([]);
  gate.assertClean();
});

test("Scenario H: home confirmation requires a fixed-place revision before preview", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const gate = installErrorGate(page);
  gate.allowExpectedInitialIntentAbsence();
  const previewRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/preplan-handoff/preview")) previewRequests.push(request.url());
  });
  const tripId = await createDraftThroughHome(page, "去上海两天，第二天下午两点到四点预约了上海博物馆。");
  const primary = page.locator("#preplan-primary-action");
  const fixedPlace = page.getByRole("region", { name: "还需确认" });

  await expect(fixedPlace.getByText(/确认.*上海博物馆/)).toBeVisible();
  await expect(fixedPlace.getByRole("button", { name: "采用这个地点" })).toBeVisible();
  await expect(primary).toBeDisabled();
  expect(previewRequests).toEqual([]);
  const before = readDraftDatabase(tripId);

  const confirmation = page.waitForResponse(isDraftIntentEditResponse);
  await fixedPlace.getByRole("button", { name: "采用这个地点" }).click();
  expect((await confirmation).status()).toBe(201);
  await expect(primary).toBeEnabled();

  const confirmed = readDraftDatabase(tripId);
  expect(confirmed.intent_revisions).toHaveLength(before.intent_revisions.length + 1);
  expect(confirmed.intent_revisions.at(-1)?.parent_draft_intent_revision_id).toBe(before.intent_revisions.at(-1)?.id);
  const fixedIdentity = confirmed.intent_revisions.at(-1)?.envelope.formal_contract.place_identities
    .find((item: { ownership: string }) => item.ownership === "fixed");
  expect(fixedIdentity).toMatchObject({
    resolution_status: "verified",
    provider_place_id: "fixture-shanghai-museum",
  });

  const preview = page.waitForResponse((response) => response.url().includes("/preplan-handoff/preview") && response.request().method() === "POST");
  await primary.click();
  expect((await preview).status()).toBe(200);
  expect(previewRequests).toHaveLength(1);
  expect(readDraftDatabase(tripId).trip_revision_count).toBe(0);
  gate.assertClean();
});

test("Scenario I: home confirmation reveals the first route preview after the final required place", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const gate = installErrorGate(page);
  gate.allowExpectedInitialIntentAbsence();
  // Saving swaps the Draft preview for the saved Roadbook, which cancels only
  // the preview's obsolete route-segment request.
  gate.allowExpectedRouteSegmentAbort();
  const tripId = await createDraftThroughHome(page, "去杭州玩两天，轻松一点，想去西湖。");
  const primary = page.locator("#preplan-primary-action");
  const confirmationQueue = page.getByRole("region", { name: "还需确认" });

  await expect(primary).toBeDisabled();
  const confirmation = page.waitForResponse(isDraftIntentEditResponse);
  await confirmationQueue.getByRole("button", { name: "采用这个地点" }).click();
  expect((await confirmation).status()).toBe(201);
  await expect(primary).toBeEnabled();

  const previewResponse = page.waitForResponse((response) => response.url().includes("/preplan-handoff/preview") && response.request().method() === "POST");
  await primary.click();
  const previewPayload = await (await previewResponse).json() as { handoff: { id: string } };
  expect(previewPayload.handoff.id).toBeTruthy();
  const preview = page.getByRole("region", { name: "第一版路线预览" });
  await expect(preview).toBeVisible();
  await expect(preview).toBeFocused();
  await expect(preview.getByRole("heading", { name: "你的第一版行程" })).toBeVisible();
  const applyResponse = page.waitForResponse((response) => response.url().includes("/preplan-handoff/runs/") && response.url().includes("/apply") && response.request().method() === "POST");
  await preview.getByRole("button", { name: "确认并生成行程" }).click();
  expect((await applyResponse).status()).toBe(200);
  await expect(page.getByRole("region", { name: "可执行路线预览" })).toBeVisible();
  const routeGuide = page.getByRole("complementary", { name: "阅读路线提示" });
  await expect(routeGuide).toContainText("正在查看第 1 天");
  await expect(routeGuide).toContainText("当前没有需要调整的项目；已明确的安排会按原计划保留。");
  expect(readDraftDatabase(tripId).trip_revision_count).toBe(1);
  await assertViewportFits(page);
  gate.assertClean();
});

test("Scenario J: keeps a recoverable formal-save retry beside the route preview", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const gate = installErrorGate(page);
  gate.allowExpectedInitialIntentAbsence();
  gate.allowExpectedNetworkFailure();
  gate.allowExpectedRouteSegmentAbort();
  const tripId = await createDraftThroughHome(page, "去杭州玩两天，轻松一点，想去西湖。");
  const primary = page.getByRole("button", { name: "生成路线预览" });
  const confirmationQueue = page.getByRole("region", { name: "还需确认" });

  const confirmation = page.waitForResponse(isDraftIntentEditResponse);
  await confirmationQueue.getByRole("button", { name: "采用这个地点" }).click();
  expect((await confirmation).status()).toBe(201);

  const previewResponse = page.waitForResponse((response) => response.url().includes("/preplan-handoff/preview") && response.request().method() === "POST");
  await primary.click();
  expect((await previewResponse).status()).toBe(200);
  const preview = page.getByRole("region", { name: "第一版路线预览" });
  await expect(preview).toBeVisible();

  let droppedFirstSave = false;
  await page.route("**/api/trips/*/preplan-handoff/runs/*/apply", async (route) => {
    if (!droppedFirstSave) {
      droppedFirstSave = true;
      await route.abort("connectionreset");
      return;
    }
    await route.continue();
  });
  await preview.getByRole("button", { name: "确认并生成行程" }).click();
  await expect(preview.getByText("正式行程的保存结果暂时未确认；你的路线预览和确认信息都还在。请稍后重新保存。")).toBeVisible();
  await expect(preview.getByRole("button", { name: "重新保存正式行程" })).toBeVisible();
  expect(readDraftDatabase(tripId).trip_revision_count).toBe(0);

  const retry = page.waitForResponse((response) => response.url().includes("/preplan-handoff/runs/") && response.url().includes("/apply") && response.request().method() === "POST");
  await preview.getByRole("button", { name: "重新保存正式行程" }).click();
  expect((await retry).status()).toBe(200);
  await expect(page.getByRole("region", { name: "可执行路线预览" })).toBeVisible();
  expect(readDraftDatabase(tripId).trip_revision_count).toBe(1);
  await assertViewportFits(page);
  gate.assertClean();
});

async function createTripCompilerDraft(page: Page, text: string): Promise<string> {
  await page.goto("/trip-compiler");
  await page.getByLabel("这一趟，你已经知道些什么？").fill(text);
  const created = page.waitForResponse((response) => response.url().includes("/api/trips/drafts") && response.request().method() === "POST");
  const compiled = page.waitForResponse((response) => response.url().includes("/preplan-intent/compile") && response.request().method() === "POST");
  await page.getByRole("button", { name: "开始编排行程" }).click();
  const payload = await (await created).json() as { trip: { id: string } };
  expect((await compiled).status()).toBe(201);
  await expect(page.getByRole("heading", { name: "这些是我理解到的旅行安排。" })).toBeVisible();
  return payload.trip.id;
}

async function createDraftThroughHome(page: Page, text: string): Promise<string> {
  await page.addInitScript(() => window.localStorage.clear());
  await page.goto("/");
  await expect(page.getByLabel("旅行需求")).toBeVisible();
  const created = page.waitForResponse((response) => response.url().includes("/api/trips/drafts") && response.request().method() === "POST");
  await page.getByLabel("旅行需求").fill(text);
  await page.getByRole("button", { name: /生成旅行骨架/ }).click();
  const createResponse = await created;
  expect(createResponse.status()).toBe(201);
  const payload = await createResponse.json() as { trip: { id: string } };
  await expect(page.getByRole("heading", { name: "确认行程信息" })).toBeVisible();
  await expect(page.getByRole("region", { name: "已理解" })).toBeVisible();
  return payload.trip.id;
}

function installErrorGate(page: Page): ErrorGate {
  const errors: string[] = [];
  let allowExpectedInitialIntentAbsence = false;
  let allowExpectedNetworkFailure = false;
  let allowExpectedProviderUnavailable = false;
  let allowExpectedStaleConflict = false;
  let allowExpectedRouteSegmentAbort = false;
  page.on("console", (message) => {
    // Chromium logs the deliberate, user-visible 409 stale response as a resource error.
    const expectedInitialIntentAbsence = allowExpectedInitialIntentAbsence && message.text().includes("status of 422");
    const expectedNetworkReset = allowExpectedNetworkFailure && message.text().includes("net::ERR_CONNECTION_RESET");
    const expectedProviderUnavailable = allowExpectedProviderUnavailable && message.text().includes("status of 503");
    const expectedStaleConflict = allowExpectedStaleConflict && message.text().includes("status of 409");
    const expectedRouteSegmentAbort = allowExpectedRouteSegmentAbort && message.text().includes("net::ERR_INTERNET_DISCONNECTED");
    // The initial GET probes for an existing immutable IntentRevision before first compile.
    if (message.type() === "error" && !expectedInitialIntentAbsence && !expectedNetworkReset && !expectedProviderUnavailable && !expectedStaleConflict && !expectedRouteSegmentAbort) {
      errors.push(`console.error: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("requestfailed", (request) => {
    const expectedRouteSegmentAbort = allowExpectedRouteSegmentAbort
      && request.url().includes("/api/preview-route-segments")
      && request.failure()?.errorText === "net::ERR_ABORTED";
    if (request.url().includes("/api/") && !allowExpectedNetworkFailure && !expectedRouteSegmentAbort) {
      errors.push(`failed API request: ${request.url()} ${request.failure()?.errorText ?? "unknown"}`);
    }
  });
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 500 && !allowExpectedProviderUnavailable) {
      errors.push(`API ${response.status()}: ${response.url()}`);
    }
  });
  return {
    allowExpectedInitialIntentAbsence: () => { allowExpectedInitialIntentAbsence = true; },
    allowExpectedNetworkFailure: () => { allowExpectedNetworkFailure = true; },
    allowExpectedProviderUnavailable: () => { allowExpectedProviderUnavailable = true; },
    allowExpectedStaleConflict: () => { allowExpectedStaleConflict = true; },
    allowExpectedRouteSegmentAbort: () => { allowExpectedRouteSegmentAbort = true; },
    assertClean: () => expect(errors, errors.join("\n")).toEqual([]),
  };
}

function isDraftIntentEditResponse(response: { url(): string; request(): { method(): string } }): boolean {
  return response.url().includes("/preplan-intent/edits") && response.request().method() === "POST";
}

function isClarificationResponse(response: { url(): string; request(): { method(): string } }): boolean {
  return response.url().includes("/preplan-intent/clarifications/")
    && response.url().includes("/resolve")
    && response.request().method() === "POST";
}

function readDraftDatabase(tripId: string): DraftDatabaseSnapshot {
  const databasePath = process.env.TRIP_E2E_DATABASE_PATH;
  if (!databasePath) throw new Error("TRIP_E2E_DATABASE_PATH is required for SQLite assertions.");
  const program = String.raw`import json, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.row_factory = sqlite3.Row
trip_id = sys.argv[2]
rows = connection.execute("SELECT id, revision_number, parent_draft_intent_revision_id, envelope_json FROM draft_intent_revisions WHERE trip_id = ? ORDER BY revision_number", (trip_id,)).fetchall()
trip_revisions = connection.execute("SELECT id, revision_number, parent_revision_id, source_type, itinerary_snapshot FROM trip_revisions WHERE trip_id = ? ORDER BY revision_number", (trip_id,)).fetchall()
trip = connection.execute("SELECT draft_version FROM trips WHERE id = ?", (trip_id,)).fetchone()
snapshot = {
  "draft_version": trip["draft_version"],
  "intent_revisions": [{"id": row["id"], "revision_number": row["revision_number"], "parent_draft_intent_revision_id": row["parent_draft_intent_revision_id"], "envelope": json.loads(row["envelope_json"])} for row in rows],
  "trip_revisions": [{"id": row["id"], "revision_number": row["revision_number"], "parent_revision_id": row["parent_revision_id"], "source_type": row["source_type"], "snapshot": json.loads(row["itinerary_snapshot"])} for row in trip_revisions],
  "trip_revision_count": len(trip_revisions),
  "preview_count": connection.execute("SELECT COUNT(*) FROM preplan_handoff_runs WHERE trip_id = ?", (trip_id,)).fetchone()[0],
  "planning_run_count": connection.execute("SELECT COUNT(*) FROM planning_runs").fetchone()[0],
}
print(json.dumps(snapshot, ensure_ascii=False))`;
  const stdout = execFileSync(process.env.TRIP_E2E_PYTHON ?? ".venv/bin/python", ["-c", program, databasePath, tripId], {
    cwd: resolve(process.cwd(), "../backend"),
    encoding: "utf8",
  });
  return JSON.parse(stdout) as DraftDatabaseSnapshot;
}

function readPlanningRunCount(): number {
  const databasePath = process.env.TRIP_E2E_DATABASE_PATH;
  if (!databasePath) throw new Error("TRIP_E2E_DATABASE_PATH is required for SQLite assertions.");
  const stdout = execFileSync(
    process.env.TRIP_E2E_PYTHON ?? ".venv/bin/python",
    ["-c", "import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute('SELECT COUNT(*) FROM planning_runs').fetchone()[0])", databasePath],
    { cwd: resolve(process.cwd(), "../backend"), encoding: "utf8" },
  );
  return Number(stdout.trim());
}

function datePolicy(row: IntentRevisionRow): Record<string, any> {
  return row.envelope.formal_contract.date_policy ?? {};
}

function pace(row: IntentRevisionRow): string | undefined {
  return row.envelope.formal_contract.pace?.value;
}

function destinations(row: IntentRevisionRow): string[] {
  return (row.envelope.formal_contract.destinations ?? []).map((item: { city_name: string }) => item.city_name);
}

function flattenedStopNames(snapshot: Record<string, any>): string[] {
  return (snapshot.days ?? []).flatMap((day: Record<string, any>) => day.blocks ?? [])
    .flatMap((block: Record<string, any>) => block.items ?? [])
    .map((item: Record<string, any>) => item.name);
}

function flattenedItems(snapshot: Record<string, any>): Array<Record<string, any>> {
  return (snapshot.days ?? []).flatMap((day: Record<string, any>) => day.blocks ?? [])
    .flatMap((block: Record<string, any>) => block.items ?? []);
}

function dayStopNames(snapshot: Record<string, any>, dayNumber: number): string[] {
  const day = (snapshot.days ?? []).find((item: Record<string, any>) => item.day === dayNumber);
  return (day?.blocks ?? []).flatMap((block: Record<string, any>) => block.items ?? [])
    .map((item: Record<string, any>) => item.name);
}

function activeClarifications(row: IntentRevisionRow): string[] {
  return (row.envelope.clarification_queue ?? []).map((item: { question_id: string }) => item.question_id);
}

async function assertViewportFits(page: Page): Promise<void> {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}
