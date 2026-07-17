import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const componentPath = fileURLToPath(new URL("./ImportReviewWorkspace.tsx", import.meta.url));

test("url import workspace does not add iframe or raw html rendering paths", () => {
  const source = readFileSync(componentPath, "utf-8");
  assert.equal(source.includes("<iframe"), false);
  assert.equal(source.includes("dangerouslySetInnerHTML"), false);
  assert.match(source, /rel="noopener noreferrer"/);
  assert.match(source, /target="_blank"/);
});
