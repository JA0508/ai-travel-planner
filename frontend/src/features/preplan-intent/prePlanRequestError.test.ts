import assert from "node:assert/strict";
import test from "node:test";

import { userFacingPrePlanRequestError } from "./prePlanRequestError";

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
