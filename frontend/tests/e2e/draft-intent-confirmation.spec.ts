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

    const overview = page.getByRole("region", { name: "行程概览" });
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
    const overview = page.getByRole("region", { name: "行程概览" });
    const clarification = page.getByRole("region", { name: "还需要你补充" });
    const primary = page.getByRole("button", { name: "生成路线预览" });

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
  const overviewA = pageA.getByRole("region", { name: "行程概览" });
  const overviewB = pageB.getByRole("region", { name: "行程概览" });
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
  await expect(page.getByText("网络连接失败，你的修改还在这里。")).toBeVisible();
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

test("Scenario E: shows a readable route preview before it creates the first TripRevision", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const gate = installErrorGate(page);
  gate.allowExpectedInitialIntentAbsence();
  const tripId = await createDraftThroughHome(page, "周末去杭州玩两天，轻松一点，想去西湖和灵隐寺。");
  const before = readDraftDatabase(tripId);
  const previewResponse = page.waitForResponse((response) => response.url().includes("/preplan-handoff/preview") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成路线预览" }).click();
  expect((await previewResponse).status()).toBe(200);
  const routePreview = page.getByRole("region", { name: "可执行路线预览" });
  await expect(routePreview.getByRole("heading", { name: "你的第一版行程" })).toBeVisible();
  await expect(routePreview.getByText("第 1 天").first()).toBeVisible();
  await expect(routePreview.getByText("预计移动").first()).toBeVisible();
  await expect(routePreview.getByText("活动时长").first()).toBeVisible();
  await expect(routePreview.getByText("路线距离").first()).toBeVisible();
  await expect(routePreview.getByRole("heading", { name: /轻松|适中|偏赶|不可执行/ }).first()).toBeVisible();
  await expect(routePreview.getByText("为什么这样安排").first()).toBeVisible();
  await expect(routePreview.getByText("trace_digest", { exact: false })).toHaveCount(0);
  await expect(routePreview.getByText("planner_run_id", { exact: false })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "确认并生成行程" })).toBeEnabled();
  const after = readDraftDatabase(tripId);
  expect(after.preview_count).toBe(before.preview_count + 1);
  expect(after.trip_revision_count).toBe(0);
  await assertViewportFits(page);
  gate.assertClean();
});

test("Scenario F: previews and applies a local relaxation without regenerating the saved route", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const gate = installErrorGate(page);
  gate.allowExpectedInitialIntentAbsence();
  // The replaced route workspace cancels its in-flight map segment preview.
  // The route preview and mutation APIs remain subject to the normal error gate.
  gate.allowExpectedRouteSegmentAbort();
  const tripId = await createDraftThroughHome(page, "周末去杭州玩两天，轻松一点。");

  const firstPreview = page.waitForResponse((response) => response.url().includes("/preplan-handoff/preview") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成路线预览" }).click();
  expect((await firstPreview).status()).toBe(200);
  const beforeSave = readDraftDatabase(tripId);
  const save = page.waitForResponse((response) => response.url().includes("/preplan-handoff/runs/") && response.url().includes("/apply") && response.request().method() === "POST");
  await page.getByRole("button", { name: "确认并生成行程" }).click();
  expect((await save).status()).toBe(200);

  const routePreview = page.getByRole("region", { name: "可执行路线预览" });
  await expect(routePreview.getByRole("heading", { name: "当前可执行路线" })).toBeVisible();
  await expect(routePreview.getByRole("heading", { name: "偏赶" })).toBeVisible();
  const beforeRepair = readDraftDatabase(tripId);
  expect(beforeRepair.trip_revisions).toHaveLength(1);
  expect(flattenedStopNames(beforeRepair.trip_revisions[0].snapshot)).toContain("武林夜市");

  const previewRepair = page.waitForResponse((response) => response.url().includes("/local-repairs/relax-day/preview") && response.request().method() === "POST");
  await routePreview.getByRole("button", { name: "让这一天轻松一些" }).click();
  expect((await previewRepair).status()).toBe(200);
  const review = page.getByRole("dialog", { name: "调整预览" });
  await expect(review).toContainText(/系统建议将“.+”从第 1 天移动到第 2 天/);
  await expect(review.getByText("固定安排没有移动；你明确想去的地点没有删除；没有重新生成全部行程。")).toBeVisible();
  const movedStop = (await review.textContent())?.match(/系统建议将“(.+)”从第 1 天移动到第 2 天/)?.[1];
  expect(movedStop).toBeTruthy();

  const applyRepair = page.waitForResponse((response) => response.url().includes("/mutation-proposals/") && response.url().includes("/apply") && response.request().method() === "POST");
  await review.getByRole("button", { name: "应用这次调整" }).click();
  expect((await applyRepair).status()).toBe(200);
  await expect(review).toHaveCount(0);

  const afterRepair = readDraftDatabase(tripId);
  expect(afterRepair.preview_count).toBe(beforeSave.preview_count);
  expect(afterRepair.trip_revisions).toHaveLength(2);
  expect(afterRepair.trip_revisions.map((revision) => revision.revision_number)).toEqual([1, 2]);
  expect(afterRepair.trip_revisions[1].source_type).toBe("route_edit");
  expect(afterRepair.trip_revisions[1].parent_revision_id).toBe(afterRepair.trip_revisions[0].id);
  expect(flattenedStopNames(afterRepair.trip_revisions[0].snapshot)).toContain(movedStop);
  expect(dayStopNames(afterRepair.trip_revisions[1].snapshot, 1)).not.toContain(movedStop);
  expect(dayStopNames(afterRepair.trip_revisions[1].snapshot, 2)).toContain(movedStop);
  await assertViewportFits(page);
  gate.assertClean();
});

test("Scenario G: blocks an unresolved fixed reservation instead of creating a false executable route", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const gate = installErrorGate(page);
  gate.allowExpectedInitialIntentAbsence();
  const tripId = await createDraftThroughHome(page, "去上海三天，第二天下午2点到4点预约了上海博物馆。");

  const previewResponse = page.waitForResponse((response) => response.url().includes("/preplan-handoff/preview") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成路线预览" }).click();
  expect((await previewResponse).status()).toBe(422);
  await expect(page.getByText("固定安排的地点还没有确认", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "返回修改需求" })).toBeVisible();
  await expect(page.getByRole("region", { name: "可执行路线预览" })).toHaveCount(0);
  expect(readDraftDatabase(tripId).trip_revision_count).toBe(0);
  gate.assertClean();
});

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
  await expect(page.getByRole("region", { name: "行程概览" })).toBeVisible();
  return payload.trip.id;
}

function installErrorGate(page: Page): ErrorGate {
  const errors: string[] = [];
  let allowExpectedInitialIntentAbsence = false;
  let allowExpectedNetworkFailure = false;
  let allowExpectedStaleConflict = false;
  let allowExpectedRouteSegmentAbort = false;
  page.on("console", (message) => {
    // Chromium logs the deliberate, user-visible 409 stale response as a resource error.
    const expectedInitialIntentAbsence = allowExpectedInitialIntentAbsence && message.text().includes("status of 422");
    const expectedNetworkReset = allowExpectedNetworkFailure && message.text().includes("net::ERR_CONNECTION_RESET");
    const expectedStaleConflict = allowExpectedStaleConflict && message.text().includes("status of 409");
    const expectedRouteSegmentAbort = allowExpectedRouteSegmentAbort && message.text().includes("net::ERR_INTERNET_DISCONNECTED");
    // The initial GET probes for an existing immutable IntentRevision before first compile.
    if (message.type() === "error" && !expectedInitialIntentAbsence && !expectedNetworkReset && !expectedStaleConflict && !expectedRouteSegmentAbort) {
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
    if (response.url().includes("/api/") && response.status() >= 500) {
      errors.push(`API ${response.status()}: ${response.url()}`);
    }
  });
  return {
    allowExpectedInitialIntentAbsence: () => { allowExpectedInitialIntentAbsence = true; },
    allowExpectedNetworkFailure: () => { allowExpectedNetworkFailure = true; },
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
}
print(json.dumps(snapshot, ensure_ascii=False))`;
  const stdout = execFileSync(process.env.TRIP_E2E_PYTHON ?? ".venv/bin/python", ["-c", program, databasePath, tripId], {
    cwd: resolve(process.cwd(), "../backend"),
    encoding: "utf8",
  });
  return JSON.parse(stdout) as DraftDatabaseSnapshot;
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
