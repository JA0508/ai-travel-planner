import assert from "node:assert/strict";
import test from "node:test";

import { isStalePrePlanIntentError, plannerHandoffRecoveryAction, previewTimedOutMessage, previewUnavailableMessage, userFacingPrePlanRequestError } from "./prePlanRequestError";

test("turns a blocked direct must-place handoff into an actionable recovery message", () => {
  const message = userFacingPrePlanRequestError(
    "planner_handoff_blocked",
    "暂时无法生成路线预览，你确认的信息已经保留。",
    { reason_code: "must_place_identity_not_verified" },
  );

  assert.match(message, /必去地点/);
  assert.match(message, /重新选择/);
  assert.doesNotMatch(message, /暂时无法生成路线预览/);
});

test("keeps an unknown preview failure honest and preserves the safe fallback", () => {
  assert.equal(
    userFacingPrePlanRequestError(
      "unexpected_failure",
      "暂时无法生成路线预览，你确认的信息已经保留。",
    ),
    "暂时无法生成路线预览，你确认的信息已经保留。",
  );
});

test("recognizes only stale Draft revisions as safe-to-refresh preview failures", () => {
  assert.equal(isStalePrePlanIntentError("stale_intent_revision"), true);
  assert.equal(isStalePrePlanIntentError("stale_base_revision"), true);
  assert.equal(isStalePrePlanIntentError("planner_handoff_blocked"), false);
});

test("makes a slow route-preview request safely retryable", () => {
  assert.match(previewTimedOutMessage(), /未完成/);
  assert.match(previewTimedOutMessage(), /重新生成/);
  assert.doesNotMatch(previewTimedOutMessage(), /已经保存/);
});

test("makes a recoverable route-preview failure explicitly retryable", () => {
  assert.match(previewUnavailableMessage(), /服务/);
  assert.match(previewUnavailableMessage(), /重新生成/);
  assert.doesNotMatch(previewUnavailableMessage(), /已保存/);
});

test("explains a fixed arrangement that falls outside the trip instead of showing a generic preview failure", () => {
  const message = userFacingPrePlanRequestError(
    "planner_handoff_blocked",
    "暂时无法生成路线预览，你确认的信息已经保留。",
    { reason_code: "fixed_event_outside_trip" },
  );

  assert.match(message, /固定安排/);
  assert.match(message, /旅行时间/);
});

test("explains missing verified place data as a refreshable planning issue", () => {
  const message = userFacingPrePlanRequestError(
    "planner_handoff_blocked",
    "暂时无法生成路线预览，你确认的信息已经保留。",
    { reason_code: "intent_candidate_identity_not_verified" },
  );

  assert.match(message, /地点资料/);
  assert.match(message, /重新整理/);
});

test("offers a direct date editor only for a blocked preview that can be repaired by travel dates", () => {
  assert.equal(plannerHandoffRecoveryAction("planner_handoff_blocked", { reason_code: "fixed_event_outside_trip" }), "edit_date_policy");
  assert.equal(plannerHandoffRecoveryAction("planner_handoff_blocked", { reason_code: "destination_missing" }), "edit_destination");
  assert.equal(plannerHandoffRecoveryAction("planner_handoff_blocked", { reason_code: "must_place_identity_not_verified" }), "focus_place_confirmation");
  assert.equal(plannerHandoffRecoveryAction("planner_handoff_blocked", { reason_code: "fixed_event_identity_not_verified" }), "focus_fixed_place_confirmation");
});

test("offers an explicit safe refresh when selected place facts have changed", () => {
  assert.equal(
    plannerHandoffRecoveryAction("planner_handoff_blocked", { reason_code: "intent_candidate_missing" }),
    "refresh_intent",
  );
  assert.equal(
    plannerHandoffRecoveryAction("planner_handoff_blocked", { reason_code: "intent_candidate_identity_not_verified" }),
    "refresh_intent",
  );
  assert.equal(
    plannerHandoffRecoveryAction("planner_handoff_blocked", { reason_code: "fixed_event_candidate_missing" }),
    "refresh_intent",
  );
});
