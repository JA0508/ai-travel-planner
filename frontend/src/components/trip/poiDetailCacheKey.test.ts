import assert from "node:assert/strict";
import test from "node:test";

import { buildPoiDetailCacheKey } from "./MobileEditRouteWorkspace";

test("keeps POI detail coverage cache entries separate for different scheduled windows", () => {
  const place = {
    name: "天津之眼",
    city: "天津",
    latitude: 39.153,
    longitude: 117.18,
  };

  const morning = buildPoiDetailCacheKey({
    ...place,
    scheduledStartTime: "10:00:00",
    scheduledEndTime: "11:30:00",
  });
  const evening = buildPoiDetailCacheKey({
    ...place,
    scheduledStartTime: "18:30:00",
    scheduledEndTime: "20:00:00",
  });

  assert.notEqual(morning, evening);
});
