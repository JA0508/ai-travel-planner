import assert from "node:assert/strict";
import test from "node:test";

import { buildItineraryChangeSet } from "./replanDiff";
import { replanFixtureItinerary, replanFixturePrompts } from "./replanFixtures";
import {
  applyReplanMutationPlanToItinerary,
  buildReplanMutationPlan,
} from "./replanViewModel";

test("detects moved stops by semantic identity across generated ids", () => {
  const plan = buildReplanMutationPlan(replanFixturePrompts.moveStop, replanFixtureItinerary);
  const next = applyReplanMutationPlanToItinerary(replanFixtureItinerary, plan);
  const diff = buildItineraryChangeSet(replanFixtureItinerary, next);

  assert.equal(diff.moved.length, 1);
  assert.equal(diff.moved[0].stopName, "大雁塔");
  assert.match(diff.summary, /移动/);
});

test("returns a quiet summary when itinerary snapshots are equivalent", () => {
  const diff = buildItineraryChangeSet(replanFixtureItinerary, replanFixtureItinerary);

  assert.equal(diff.summary, "没有检测到可见行程变化");
  assert.equal(diff.added.length, 0);
  assert.equal(diff.removed.length, 0);
  assert.equal(diff.moved.length, 0);
});
