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
