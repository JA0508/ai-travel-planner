import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

const pagePath = fileURLToPath(new URL("./page.tsx", import.meta.url));

test("first formal route handoff restores keyboard focus without affecting later route reveals", () => {
  const source = readFileSync(pagePath, "utf8");

  assert.match(source, /scheduleResultReveal\(\{ focus: true \}\)/);
  assert.match(source, /shouldFocusResultRef/);
  assert.match(source, /target\.focus\(\{ preventScroll: true \}\)/);
  assert.match(source, /<section\s+ref=\{resultSectionRef\}\s+className="ec-result-entry"\s+tabIndex=\{-1\}/);
});

test("returning from confirmation places focus back in the original travel request", () => {
  const source = readFileSync(pagePath, "utf8");

  assert.match(source, /restoreTripTextFocus/);
  assert.match(source, /document\.getElementById\("trip-text"\)/);
  assert.match(source, /input\?\.focus\(\{ preventScroll: true \}\)/);
  assert.match(source, /onCancel=\{returnToOriginalRequest\}/);
  assert.doesNotMatch(source, /trip-text"\)\?\.scrollIntoView/);
});

test("returning from a blocked confirmation keeps its existing explanation beside the request", () => {
  const source = readFileSync(pagePath, "utf8");

  assert.match(source, /returnToTripTextNotice/);
  assert.match(source, /function returnToOriginalRequest\(notice\?: string\)/);
  assert.match(source, /setReturnToTripTextNotice\(notice\?\.trim\(\) \|\| null\)/);
  assert.match(source, /请先修改这项行程信息/);
  assert.match(source, /setReturnToTripTextNotice\(null\)/);
});
