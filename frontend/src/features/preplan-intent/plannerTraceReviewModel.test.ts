import assert from "node:assert/strict";
import test from "node:test";
import { buildPlannerTraceReviewView, type PlannerHandoffReviewSummary } from "./plannerTraceReviewModel";

function summary(overrides: Partial<PlannerHandoffReviewSummary> = {}): PlannerHandoffReviewSummary {
  return {
    status: "apply_ready",
    can_apply: true,
    intent_revision_id: "intent-1",
    current_intent_revision_id: "intent-1",
    base_trip_revision_id: null,
    current_trip_revision_id: null,
    readiness_status: "ready_for_planning",
    blocking_reason_codes: [],
    warning_codes: [],
    trace: { decision_count: 3, accepted_decision_count: 2, rejected_decision_count: 1, warning_count: 0, reason_codes: [] },
    ...overrides,
  };
}

test("handoff review view explains an applicable frozen preview without internal scoring", () => {
  const view = buildPlannerTraceReviewView(summary());

  assert.equal(view.tone, "ready");
  assert.match(view.title, /可以确认/);
  assert.match(view.traceSummary, /2 项纳入路线/);
  assert.doesNotMatch(view.detail, /reason_code|score/i);
});

test("handoff review view distinguishes stale and unstable previews", () => {
  const stale = buildPlannerTraceReviewView(summary({ status: "stale", can_apply: false, blocking_reason_codes: ["intent_revision_advanced"] }));
  const unstable = buildPlannerTraceReviewView(summary({ status: "unstable", can_apply: false, blocking_reason_codes: ["route_conflict"] }));

  assert.match(stale.title, /过期/);
  assert.match(stale.detail, /行程信息已更新/);
  assert.match(unstable.title, /执行冲突/);
  assert.match(unstable.detail, /重新生成/);
});
