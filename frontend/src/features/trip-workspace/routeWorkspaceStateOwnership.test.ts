import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  getWorkspaceStateOwner,
  groupWorkspaceStateOwnership,
  routeWorkspaceFeatureStateOwnership,
  routeWorkspacePageStateOwnership,
} from "./routeWorkspaceStateOwnership.ts";

test("classifies every current page useState owner explicitly", () => {
  const pageSource = readFileSync(new URL("../../app/page.tsx", import.meta.url), "utf8");
  const stateNames = Array.from(
    pageSource.matchAll(/const\s+\[\s*([A-Za-z0-9_]+)\s*,/g),
    (match) => match[1],
  ).sort();
  const classifiedNames = Object.keys(routeWorkspacePageStateOwnership).sort();

  assert.deepEqual(classifiedNames, stateNames);
});

test("keeps route workspace UI state owned by the feature boundary", () => {
  const pageSource = readFileSync(new URL("../../app/page.tsx", import.meta.url), "utf8");
  assert.equal(pageSource.includes("const [routeEditMode,"), false);
  assert.equal(pageSource.includes("const [activeRouteSheet,"), false);

  assert.deepEqual(routeWorkspaceFeatureStateOwnership, {
    activeRouteSheet: "ui",
    routeEditMode: "ui",
  });
});

test("keeps the core workspace owners distinct", () => {
  assert.equal(getWorkspaceStateOwner("result"), "server");
  assert.equal(getWorkspaceStateOwner("generationContext"), "durable");
  assert.equal(getWorkspaceStateOwner("followUpText"), "draft");
  assert.equal(getWorkspaceStateOwner("selectedCompletionOptionKeys"), "selection");
  assert.equal(getWorkspaceStateOwner("routeEditMode"), "ui");
  assert.equal(getWorkspaceStateOwner("replanning"), "async");
});

test("groups all expected state ownership buckets", () => {
  const grouped = groupWorkspaceStateOwnership();

  assert.ok(grouped.durable.includes("userIntentState"));
  assert.ok(grouped.server.includes("completionTaskCandidatePreviews"));
  assert.ok(grouped.draft.includes("availabilityWindowsText"));
  assert.ok(grouped.selection.includes("activeSwapTarget"));
  assert.ok(groupWorkspaceStateOwnership(routeWorkspaceFeatureStateOwnership).ui.includes("activeRouteSheet"));
  assert.ok(grouped.async.includes("previewingCompletionTaskId"));
});
