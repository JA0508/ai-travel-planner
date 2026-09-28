import assert from "node:assert/strict";
import test from "node:test";

import { previewRevealScrollTop } from "./prePlanPreviewFocus";

test("reveals a generated preview with a small top gutter", () => {
  assert.equal(
    previewRevealScrollTop({ top: 420 }, 180),
    576,
  );
});

test("never requests a negative preview reveal scroll position", () => {
  assert.equal(
    previewRevealScrollTop({ top: 12 }, 0),
    0,
  );
});
