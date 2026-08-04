import assert from "node:assert/strict";
import test from "node:test";
import {
  buildPrePlanHandoffStatus,
  userFacingPrePlanHandoffError,
} from "./plannerHandoffModel";

test("an older frozen preview is visibly stale and cannot be applied", () => {
  const status = buildPrePlanHandoffStatus({
    previewIntentRevisionId: "draft_intent_1",
    latestIntentRevisionId: "draft_intent_2",
  });

  assert.equal(status.kind, "stale");
  assert.equal(status.canApply, false);
  assert.equal(status.canGenerateReplacement, true);
  assert.match(status.message, /已过期/);
});

test("the current frozen preview remains applicable", () => {
  const status = buildPrePlanHandoffStatus({
    previewIntentRevisionId: "draft_intent_2",
    latestIntentRevisionId: "draft_intent_2",
  });

  assert.equal(status.kind, "current");
  assert.equal(status.canApply, true);
  assert.equal(status.canGenerateReplacement, false);
});

test("stale apply failures explain the revision mismatch in product language", () => {
  assert.equal(
    userFacingPrePlanHandoffError("stale_intent_revision"),
    "路线预览已过期：行程信息已经更新，请重新生成预览后再保存。",
  );
  assert.equal(
    userFacingPrePlanHandoffError("stale_base_revision"),
    "行程已在其他页面生成或更新，旧预览不能再保存。请返回查看最新行程。",
  );
});
