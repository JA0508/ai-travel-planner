import assert from "node:assert/strict";
import test from "node:test";

import { buildItineraryChangeSet } from "./replanDiff";
import { replanFixtureItinerary, replanFixturePrompts } from "./replanFixtures";
import {
  createInitialReplanWorkflowState,
  reduceReplanWorkflowState,
} from "./replanState";
import {
  applyReplanMutationPlanToItinerary,
  buildReplanMutationPlan,
} from "./replanViewModel";

test("state machine moves from interpretation to review after confirmed execution", () => {
  const plan = buildReplanMutationPlan(
    replanFixturePrompts.removeFlexibleStop,
    replanFixtureItinerary,
  );
  const afterItinerary = applyReplanMutationPlanToItinerary(replanFixtureItinerary, plan);
  const changeSet = buildItineraryChangeSet(replanFixtureItinerary, afterItinerary);

  let state = createInitialReplanWorkflowState();
  state = reduceReplanWorkflowState(state, { type: "interpreted", plan });
  assert.equal(state.status, "needs_confirmation");

  state = reduceReplanWorkflowState(state, { type: "confirmed" });
  assert.equal(state.status, "executing");

  state = reduceReplanWorkflowState(state, {
    type: "execute_finished",
    result: {
      ok: true,
      beforeItinerary: replanFixtureItinerary,
      afterItinerary,
      message: "ok",
      usedBackend: false,
    },
    changeSet,
  });

  assert.equal(state.status, "review");
  assert.equal(state.history.length, 1);
  assert.equal(state.executedPlanIds.includes(plan.id), true);
});

test("state machine blocks duplicate execution of the same plan id", () => {
  const plan = buildReplanMutationPlan(
    replanFixturePrompts.removeFlexibleStop,
    replanFixtureItinerary,
  );
  let state = createInitialReplanWorkflowState();
  state = reduceReplanWorkflowState(state, { type: "interpreted", plan });
  state = {
    ...state,
    executedPlanIds: [plan.id],
  };

  state = reduceReplanWorkflowState(state, { type: "confirmed" });

  assert.equal(state.status, "review");
  assert.match(state.errorMessage ?? "", /已经执行/);
});
