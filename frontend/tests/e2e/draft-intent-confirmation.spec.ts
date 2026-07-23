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
  trip_revision_count: number;
  preview_count: number;
};

type ErrorGate = {
  allowExpectedInitialIntentAbsence: () => void;
  allowExpectedNetworkFailure: () => void;
  allowExpectedStaleConflict: () => void;
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
  page.on("console", (message) => {
    // Chromium logs the deliberate, user-visible 409 stale response as a resource error.
    const expectedInitialIntentAbsence = allowExpectedInitialIntentAbsence && message.text().includes("status of 422");
    const expectedNetworkReset = allowExpectedNetworkFailure && message.text().includes("net::ERR_CONNECTION_RESET");
    const expectedStaleConflict = allowExpectedStaleConflict && message.text().includes("status of 409");
    // The initial GET probes for an existing immutable IntentRevision before first compile.
    if (message.type() === "error" && !expectedInitialIntentAbsence && !expectedNetworkReset && !expectedStaleConflict) {
      errors.push(`console.error: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("requestfailed", (request) => {
    if (request.url().includes("/api/") && !allowExpectedNetworkFailure) {
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
trip = connection.execute("SELECT draft_version FROM trips WHERE id = ?", (trip_id,)).fetchone()
snapshot = {
  "draft_version": trip["draft_version"],
  "intent_revisions": [{"id": row["id"], "revision_number": row["revision_number"], "parent_draft_intent_revision_id": row["parent_draft_intent_revision_id"], "envelope": json.loads(row["envelope_json"])} for row in rows],
  "trip_revision_count": connection.execute("SELECT COUNT(*) FROM trip_revisions WHERE trip_id = ?", (trip_id,)).fetchone()[0],
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

function activeClarifications(row: IntentRevisionRow): string[] {
  return (row.envelope.clarification_queue ?? []).map((item: { question_id: string }) => item.question_id);
}

async function assertViewportFits(page: Page): Promise<void> {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}
