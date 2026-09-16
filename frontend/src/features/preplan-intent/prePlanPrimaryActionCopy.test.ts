import assert from "node:assert/strict";
import test from "node:test";

import { prePlanPrimaryAction, prePlanPrimaryActionLabel } from "./prePlanPrimaryActionCopy";

test("names the next required confirmation count on a disabled preview action", () => {
  assert.equal(
    prePlanPrimaryActionLabel({
      sourcesChanged: false,
      canGeneratePreview: false,
      requiresTravelInformationEdit: false,
      remainingActionableConfirmationCount: 3,
    }),
    "还差 3 项待确认",
  );
});

test("names request editing instead of implying a preview can start for a conflict", () => {
  assert.equal(
    prePlanPrimaryActionLabel({
      sourcesChanged: false,
      canGeneratePreview: false,
      requiresTravelInformationEdit: true,
      remainingActionableConfirmationCount: 0,
    }),
    "请先修改旅行信息",
  );
});

test("turns the primary action into request recovery only for a confirmed editing conflict", () => {
  assert.deepEqual(
    prePlanPrimaryAction({
      sourcesChanged: false,
      canGeneratePreview: false,
      requiresTravelInformationEdit: true,
      remainingActionableConfirmationCount: 0,
    }),
    { kind: "modify_request", label: "请先修改旅行信息" },
  );
  assert.equal(
    prePlanPrimaryAction({
      sourcesChanged: true,
      canGeneratePreview: false,
      requiresTravelInformationEdit: true,
      remainingActionableConfirmationCount: 0,
    }).kind,
    "blocked",
  );
});

test("names required recompilation when imported material has changed", () => {
  assert.equal(
    prePlanPrimaryActionLabel({
      sourcesChanged: true,
      canGeneratePreview: true,
      requiresTravelInformationEdit: false,
      remainingActionableConfirmationCount: 0,
    }),
    "请先重新整理旅行信息",
  );
});

test("keeps the preview action direct when the Draft is ready", () => {
  assert.equal(
    prePlanPrimaryActionLabel({
      sourcesChanged: false,
      canGeneratePreview: true,
      requiresTravelInformationEdit: false,
      remainingActionableConfirmationCount: 0,
    }),
    "生成路线预览",
  );
});
