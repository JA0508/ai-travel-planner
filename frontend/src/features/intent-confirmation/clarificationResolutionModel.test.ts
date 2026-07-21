import assert from "node:assert/strict";
import test from "node:test";
import {
  canSubmitInlineClarification,
  getClarificationResolutionAction,
} from "./clarificationResolutionModel";

test("only inline clarification kinds accept a free-text answer", () => {
  assert.equal(canSubmitInlineClarification({ resolution_kind: "inline_answer" }, "2"), true);
  assert.equal(canSubmitInlineClarification({ resolution_kind: "inline_answer" }, "   "), false);
  assert.equal(canSubmitInlineClarification({ resolution_kind: "edit_contract" }, "2"), false);
  assert.equal(canSubmitInlineClarification({ resolution_kind: "reimport_evidence" }, "confirmed"), false);
});

test("clarification resolution action preserves the compiler-directed workflow", () => {
  assert.equal(getClarificationResolutionAction({ resolution_kind: "inline_answer" }), "answer_inline");
  assert.equal(getClarificationResolutionAction({ resolution_kind: "edit_contract" }), "edit_contract");
  assert.equal(getClarificationResolutionAction({ resolution_kind: "reimport_evidence" }), "reimport_evidence");
});
