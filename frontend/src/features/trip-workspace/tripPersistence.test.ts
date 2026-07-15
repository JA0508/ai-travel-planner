import assert from "node:assert/strict";
import test from "node:test";
import {
  buildPersistedTripRef,
  describeTripPersistence,
  markDirty,
  parsePersistedTripRef,
  serializePersistedTripRef,
  type TripMetadata,
  type TripRevisionMetadata,
} from "./tripPersistence.ts";

const trip: TripMetadata = {
  id: "trip_1",
  current_revision_id: "rev_1",
  revision_count: 1,
  lifecycle_status: "active",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const revision: TripRevisionMetadata = {
  id: "rev_1",
  trip_id: "trip_1",
  revision_number: 1,
  parent_revision_id: null,
  base_revision_id: null,
  source_type: "planner_generation",
  snapshot_schema_version: "1.0",
  content_digest: "content",
  parent_lineage_digest: null,
  lineage_digest: "lineage",
  planner_run_id: "run_1",
  planner_version: "current-baseline",
  trace_schema_version: "1.0",
  trace_digest: "trace",
  restored_from_revision_id: null,
  created_at: "2026-01-01T00:00:00Z",
};

test("persisted trip reference stores only trip and revision identity", () => {
  const ref = buildPersistedTripRef(trip, revision);
  const serialized = serializePersistedTripRef(ref);

  assert.deepEqual(JSON.parse(serialized), {
    schemaVersion: 1,
    tripId: "trip_1",
    currentRevisionId: "rev_1",
  });
  assert.equal(serialized.includes("capability"), false);
  assert.equal(serialized.includes("itinerary"), false);
});

test("invalid persisted reference schema clears safely", () => {
  assert.equal(parsePersistedTripRef(null), null);
  assert.equal(parsePersistedTripRef("{"), null);
  assert.equal(parsePersistedTripRef(JSON.stringify({ schemaVersion: 2 })), null);
});

test("saved and dirty states have stable user-facing labels", () => {
  const saved = {
    status: "saved" as const,
    tripId: "trip_1",
    currentRevisionId: "rev_1",
    revisionNumber: 1,
  };
  const dirty = markDirty(saved, "route_edit_commit");

  assert.equal(describeTripPersistence(saved), "Saved · Revision 1");
  assert.equal(describeTripPersistence(dirty), "Unsaved changes · Revision 1");
});
