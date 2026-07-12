import assert from "node:assert/strict";
import test from "node:test";

import { getResultWorkspaceFixture } from "../../components/trip/fixtures/resultWorkspaceFixtures.ts";
import {
  buildEditableRouteDays,
  buildManualPendingStop,
  buildRouteStopSelector,
  insertExistingStop,
  insertPendingStop,
  moveStopAcrossTimeline,
  reorderStops,
  sameReferenceList,
  toggleRouteStopLock,
} from "./routeWorkspaceEditModel.ts";

test("builds editable route days from the fixture itinerary contract", () => {
  const days = buildEditableRouteDays(getResultWorkspaceFixture("complete").itinerary);

  assert.equal(days.length, 3);
  assert.equal(days[0].stops[0].id, "1-morning-西湖断桥-09:00:00-10:30:00-0");
  assert.equal(days[1].stops[0].originalIsFixed, true);
  assert.equal(days[2].stops.at(-1)?.item.name, "杭州东站");
});

test("moves a flexible stop across days while preserving block insertion order", () => {
  const days = buildEditableRouteDays(getResultWorkspaceFixture("complete").itinerary);
  const movingStop = days[0].stops.find((stop) => stop.item.name === "浙江省博物馆");
  assert.ok(movingStop);

  const movedDays = moveStopAcrossTimeline(days, movingStop.id, 2, "morning");
  const day1Names = movedDays[0].stops.map((stop) => stop.item.name);
  const day2Names = movedDays[1].stops.map((stop) => `${stop.blockType}:${stop.item.name}`);

  assert.deepEqual(day1Names, ["西湖断桥", "湖滨银泰晚餐"]);
  assert.deepEqual(day2Names.slice(0, 2), ["morning:灵隐寺", "morning:浙江省博物馆"]);
  assert.equal(movedDays[1].stops[1].day, 2);
});

test("returns the same day references when a requested move target is missing", () => {
  const days = buildEditableRouteDays(getResultWorkspaceFixture("complete").itinerary);
  const movedDays = moveStopAcrossTimeline(days, "missing-stop", 2, "evening");

  assert.equal(sameReferenceList(movedDays, days), true);
});

test("inserts manual pending stops after existing stops in the target block", () => {
  const days = buildEditableRouteDays(getResultWorkspaceFixture("complete").itinerary);
  const nextDays = insertPendingStop(days, 1, "afternoon", "手动茶歇", "scenic");
  const day1Names = nextDays[0].stops.map((stop) => stop.item.name);
  const manualStop = nextDays[0].stops.find((stop) => stop.item.name === "手动茶歇");

  assert.deepEqual(day1Names, ["西湖断桥", "浙江省博物馆", "手动茶歇", "湖滨银泰晚餐"]);
  assert.equal(manualStop?.item.source_label, "手动插入");
  assert.equal(manualStop?.item.is_fixed, false);
});

test("places unplanned stops through the same block insertion rule", () => {
  const days = buildEditableRouteDays(getResultWorkspaceFixture("complete").itinerary);
  const unplanned = buildManualPendingStop(2, "evening", "武林夜游", "scenic");
  const nextDays = insertExistingStop(days, unplanned);

  assert.equal(nextDays[1].stops.at(-1)?.item.name, "武林夜游");
  assert.equal(nextDays[1].stops.at(-1)?.blockType, "evening");
});

test("toggles route locks while preserving non-editor fixed items", () => {
  const days = buildEditableRouteDays(getResultWorkspaceFixture("complete").itinerary);
  const flexibleStop = days[0].stops[0];
  const lockedStop = toggleRouteStopLock(flexibleStop);
  const unlockedStop = toggleRouteStopLock(lockedStop);
  const editableLockedStop = days[1].stops[0];
  const backendFixedStop = {
    ...editableLockedStop,
    item: {
      ...editableLockedStop.item,
      source_label: "固定预约",
      source_reason: "后端固定安排。",
    },
  };

  assert.equal(lockedStop.item.is_fixed, true);
  assert.equal(lockedStop.item.source_type, "user_fixed");
  assert.equal(unlockedStop.item.is_fixed, false);
  assert.equal(toggleRouteStopLock(editableLockedStop).item.is_fixed, false);
  assert.equal(toggleRouteStopLock(backendFixedStop), backendFixedStop);
});

test("reorders only when both stop ids are present", () => {
  const days = buildEditableRouteDays(getResultWorkspaceFixture("complete").itinerary);
  const day1Stops = days[0].stops;
  const reordered = reorderStops(day1Stops, day1Stops[2].id, day1Stops[0].id);
  const unchanged = reorderStops(day1Stops, "missing", day1Stops[0].id);

  assert.deepEqual(reordered.map((stop) => stop.item.name), [
    "湖滨银泰晚餐",
    "西湖断桥",
    "浙江省博物馆",
  ]);
  assert.equal(unchanged, day1Stops);
});

test("builds a safe selector for focus restoration after closing place detail", () => {
  assert.equal(
    buildRouteStopSelector('stop "quoted" \\ slash'),
    '[data-route-stop-id="stop \\"quoted\\" \\\\ slash"]',
  );
});
