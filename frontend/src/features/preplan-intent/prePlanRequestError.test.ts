import assert from "node:assert/strict";
import test from "node:test";

import { isStalePrePlanIntentError, previewTimedOutMessage, previewUnavailableMessage, userFacingPrePlanRequestError } from "./prePlanRequestError";

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
