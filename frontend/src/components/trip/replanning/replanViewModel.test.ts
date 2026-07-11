import assert from "node:assert/strict";
import test from "node:test";

import { buildItineraryChangeSet } from "./replanDiff";
import { replanFixtureItinerary, replanFixturePrompts } from "./replanFixtures";
import {
  applyReplanMutationPlanToItinerary,
  buildReplanMutationPlan,
} from "./replanViewModel";

test("builds a local remove-stop mutation for an unprotected target", () => {
  const plan = buildReplanMutationPlan(
    replanFixturePrompts.removeFlexibleStop,
    replanFixtureItinerary,
  );

  assert.equal(plan.intentKind, "remove_stop");
  assert.equal(plan.executionMode, "local_mutation");
  assert.equal(plan.executable, true);
  assert.equal(plan.targetStops[0].name, "曲江池遗址公园");
  assert.equal(plan.operations[0].kind, "remove_stop");
});

test("blocks removing a fixed user-owned stop", () => {
  const plan = buildReplanMutationPlan(
    replanFixturePrompts.blockFixedStop,
    replanFixtureItinerary,
  );

  assert.equal(plan.intentKind, "remove_stop");
  assert.equal(plan.executionMode, "unsupported");
  assert.equal(plan.executable, false);
  assert.equal(plan.constraints.some((finding) => finding.severity === "blocked"), true);
});

test("builds a move mutation with target day and block", () => {
  const plan = buildReplanMutationPlan(replanFixturePrompts.moveStop, replanFixtureItinerary);

  assert.equal(plan.intentKind, "move_stop");
  assert.equal(plan.executionMode, "local_mutation");
  assert.deepEqual(plan.operations[0], {
    kind: "move_stop",
    stopId: plan.targetStops[0].id,
    stopName: "大雁塔",
    fromDay: 2,
    fromBlockType: "afternoon",
    toDay: 3,
    toBlockType: "morning",
  });
});

test("chooses a flexible auto-filled stop for relax-day", () => {
  const plan = buildReplanMutationPlan(replanFixturePrompts.relaxDay, replanFixtureItinerary);

  assert.equal(plan.intentKind, "relax_day");
  assert.equal(plan.executionMode, "local_mutation");
  assert.equal(plan.targetStops[0].name, "曲江池遗址公园");
});

test("records weather adaptation as an unsupported contract gap", () => {
  const plan = buildReplanMutationPlan(replanFixturePrompts.weatherGap, replanFixtureItinerary);

  assert.equal(plan.intentKind, "weather_adaptation");
  assert.equal(plan.executionMode, "unsupported");
  assert.match(plan.contractGaps.join(" "), /天气/);
});

test("local mutation produces a before-after diff and updates rejected intent", () => {
  const plan = buildReplanMutationPlan(
    replanFixturePrompts.removeFlexibleStop,
    replanFixtureItinerary,
  );
  const next = applyReplanMutationPlanToItinerary(replanFixtureItinerary, plan);
  const diff = buildItineraryChangeSet(replanFixtureItinerary, next);

  assert.equal(diff.removed.length, 1);
  assert.equal(diff.removed[0].stopName, "曲江池遗址公园");
  assert.deepEqual(
    next.trip_intent?.current_intent?.rejected_scenic_spots,
    ["曲江池遗址公园"],
  );
});
