import assert from "node:assert/strict";
import test from "node:test";
import {
  buildPersistedTripRef,
  buildPersistedDraftTripRef,
  buildReplanProposalIdempotencyKey,
  describeRevisionRestoreBlock,
  describeRevisionRestoreMustVisitBlock,
  describeTripPersistence,
  describeRevisionRestoreImpact,
  describeRevisionRestoreReceipt,
  describeTripRevisionSource,
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

test("draft trip reference keeps only draft identity and never raw trip text", () => {
  const ref = buildPersistedDraftTripRef("trip_draft_1");
  const serialized = serializePersistedTripRef(ref);

  assert.deepEqual(JSON.parse(serialized), { schemaVersion: 2, kind: "draft", tripId: "trip_draft_1" });
  assert.deepEqual(parsePersistedTripRef(serialized), ref);
  assert.equal(serialized.includes("西安"), false);
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

test("revision source labels explain the saved change without exposing internal codes", () => {
  assert.equal(describeTripRevisionSource("route_edit"), "局部路线调整");
  assert.equal(describeTripRevisionSource("swap"), "替换一个地点");
  assert.equal(describeTripRevisionSource("mutation_undo"), "撤销上一项调整");
  assert.equal(describeTripRevisionSource("unknown_source"), "已保存的路线变更");
});

test("revision restore impact makes the compensating version explicit", () => {
  assert.equal(
    describeRevisionRestoreImpact(2),
    "恢复版本 2 会创建一个新的版本；当前版本会保留，之后仍可恢复。",
  );
});

test("revision restore receipt names both the restored and newly saved versions", () => {
  assert.equal(
    describeRevisionRestoreReceipt(2, 4),
    "已恢复版本 2，并保存为新版本 4。之前的版本仍可恢复。",
  );
});

test("revision restore block explains that the current route remains unchanged", () => {
  assert.equal(
    describeRevisionRestoreBlock(2),
    "无法恢复该版本：它会移除或改变当前路线中的 2 项固定安排。当前路线没有变化。",
  );
});

test("revision restore block explains that current must-visit places remain protected", () => {
  assert.equal(
    describeRevisionRestoreMustVisitBlock(1),
    "无法恢复该版本：它会移除当前路线中的 1 个必去地点。当前路线没有变化。",
  );
});

test("replan proposal idempotency key is stable without leaking raw follow-up text", () => {
  const first = buildReplanProposalIdempotencyKey("prop_1", "digest_abc");
  const second = buildReplanProposalIdempotencyKey("prop_1", "digest_abc");
  const differentProposal = buildReplanProposalIdempotencyKey("prop_2", "digest_abc");

  assert.equal(first, second);
  assert.notEqual(first, differentProposal);
  assert.equal(first.includes("第二天"), false);
  assert.match(first, /^replan-proposal:prop_1:[0-9a-f]+$/);
});
