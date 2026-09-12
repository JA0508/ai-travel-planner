import assert from "node:assert/strict";
import test from "node:test";

import { centeredConfirmationScrollTop } from "./PrePlanConfirmationQueue";

test("centers a requested confirmation item within the current page scroll", () => {
  assert.equal(
    centeredConfirmationScrollTop({ top: 160, height: 160 }, 240, 800),
    80,
  );
});

test("never requests a negative confirmation scroll position", () => {
  assert.equal(
    centeredConfirmationScrollTop({ top: 20, height: 160 }, 0, 800),
    0,
  );
});
