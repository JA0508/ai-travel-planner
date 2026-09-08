import assert from "node:assert/strict";
import test from "node:test";

import { resolvePrePlanCompileAttempt } from "./prePlanCompileAttempt";

test("reuses an in-flight draft compile key only when retrying the same parent revision", () => {
  const current = { parentIntentRevisionId: "intent-1", idempotencyKey: "draft-intent:one" };

  assert.deepEqual(
    resolvePrePlanCompileAttempt(current, "intent-1", false, () => "draft-intent:new"),
    current,
  );
});

test("starts a fresh draft compile key for an explicit recompile without weakening retry safety", () => {
  const current = { parentIntentRevisionId: "intent-1", idempotencyKey: "draft-intent:one" };

  assert.deepEqual(
    resolvePrePlanCompileAttempt(current, "intent-1", true, () => "draft-intent:new"),
    { parentIntentRevisionId: "intent-1", idempotencyKey: "draft-intent:new" },
  );
});

test("starts a fresh draft compile key after the authoritative parent changes", () => {
  const current = { parentIntentRevisionId: "intent-1", idempotencyKey: "draft-intent:one" };

  assert.deepEqual(
    resolvePrePlanCompileAttempt(current, "intent-2", false, () => "draft-intent:two"),
    { parentIntentRevisionId: "intent-2", idempotencyKey: "draft-intent:two" },
  );
});
