import assert from "node:assert/strict";
import test from "node:test";

import { buildRevisionRouteOutline } from "./revisionRouteOutline.ts";

test("builds a read-only route outline from the persisted revision snapshot", () => {
  assert.deepEqual(
    buildRevisionRouteOutline({
      trip_days: 2,
      days: [
        {
          day: 1,
          blocks: [
            {
              items: [
                { name: "博物馆", is_fixed: true, source_type: "user_fixed" },
                { name: "老街", is_fixed: false, source_type: "user_seed" },
              ],
            },
          ],
        },
        {
          day: 2,
          blocks: [{ items: [{ name: "湖边餐厅", is_fixed: false, source_type: "auto_seeded_meal" }] }],
        },
      ],
    }),
    {
      tripDays: 2,
      stopCount: 3,
      fixedStopNames: ["博物馆"],
      days: [
        { day: 1, stopNames: ["博物馆", "老街"] },
        { day: 2, stopNames: ["湖边餐厅"] },
      ],
    },
  );
});
