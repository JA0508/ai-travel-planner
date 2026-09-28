import assert from "node:assert/strict";
import test from "node:test";

import { placeConfirmationFeedback } from "./TripCompilerWorkspace";

test("explains when a confirmed place still leaves a fixed place unresolved", () => {
  assert.equal(
    placeConfirmationFeedback({
      formal_contract: {
        place_identities: [
          { ownership: "must", resolution_status: "verified" },
          { ownership: "fixed", resolution_status: "ambiguous" },
        ],
      },
    }),
    "地点已确认。固定安排地点仍待确认，确认后才能生成路线。",
  );
});
