import assert from "node:assert/strict";
import test from "node:test";
import { buildPlannerHandoffApplyIdempotencyKey, canPreviewPlannerHandoff } from "./plannerHandoffModel";

test("planner handoff allows only latest confirmed planner-ready contracts", () => {
  const ready = {
    formal_contract: { readiness: { status: "ready_for_planning" } },
  } as never;
  const assumed = {
    formal_contract: { readiness: { status: "ready_with_assumptions" } },
  } as never;
  const blocked = {
    formal_contract: { readiness: { status: "needs_clarification" } },
  } as never;
  assert.equal(canPreviewPlannerHandoff(ready, true), true);
  assert.equal(canPreviewPlannerHandoff(assumed, true), true);
  assert.equal(canPreviewPlannerHandoff(blocked, true), false);
  assert.equal(canPreviewPlannerHandoff(ready, false), false);
});

test("planner handoff apply keys are stable for the frozen proposal", () => {
  assert.equal(
    buildPlannerHandoffApplyIdempotencyKey("proposal_1", "abcdef0123456789"),
    buildPlannerHandoffApplyIdempotencyKey("proposal_1", "abcdef0123456789"),
  );
});
