import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCandidateAdmissionEnvelope,
  buildCompletionCandidatePayload,
  buildManualCandidatePayload,
  candidateIdempotencyKey,
  groupCandidates,
  type TripCandidate,
} from "./tripCandidates.ts";

test("groups persisted trip candidates by workflow state without changing candidate records", () => {
  const pending = candidate({ id: "cand_1", workflow_state: "pending" });
  const rejected = candidate({ id: "cand_2", workflow_state: "rejected" });
  const deferred = candidate({ id: "cand_3", workflow_state: "deferred" });
  const scheduled = candidate({ id: "cand_4", workflow_state: "scheduled" });

  const grouped = groupCandidates([pending, rejected, deferred, scheduled]);

  assert.equal(grouped.status, "ready");
  assert.deepEqual(grouped.pending, [pending]);
  assert.deepEqual(grouped.rejected, [rejected]);
  assert.deepEqual(grouped.deferred, [deferred]);
  assert.deepEqual(grouped.scheduled, [scheduled]);
});

test("manual candidate payload records candidate intake instead of itinerary mutation data", () => {
  const payload = buildManualCandidatePayload("  思南书局  ", "scenic");

  assert.deepEqual(payload, {
    candidate_type: "place",
    display_name: "思南书局",
    category: "scenic",
    source_kind: "manual_entry",
  });
  assert.equal("itinerary" in payload, false);
  assert.equal("days" in payload, false);
});

test("completion candidate payload preserves provenance hints without scheduling it locally", () => {
  const payload = buildCompletionCandidatePayload({
    name: "静安寺",
    type: "scenic",
    suggested_day: 2,
    suggested_block: "afternoon",
    reasoning_summary: "fills an open afternoon",
  });

  assert.equal(payload.source_kind, "completion");
  assert.equal(payload.explicit_day_reference, "2");
  assert.equal(payload.preferred_time_block, "afternoon");
  assert.equal(payload.source_ref, "fills an open afternoon");
  assert.equal("target_day" in payload, false);
});

test("candidate admission envelope sends only a candidate reference and target slot", () => {
  const envelope = buildCandidateAdmissionEnvelope(
    "rev_1",
    candidate({ id: "cand_server" }),
    1,
    "afternoon",
  );

  assert.equal(envelope.schema_version, "1.0");
  assert.equal(envelope.base_revision_id, "rev_1");
  assert.equal(envelope.mutation_kind, "candidate_admission");
  assert.deepEqual(envelope.commands, [
    {
      type: "add_candidate_stop",
      candidate_id: "cand_server",
      target_day: 1,
      target_block: "afternoon",
      placement: { at_end: true },
    },
  ]);
  assert.equal("itinerary" in envelope, false);
});

test("candidate idempotency keys are stable and bounded for retry-safe writes", () => {
  const key = candidateIdempotencyKey("candidate-register", "trip_1", "x".repeat(300));

  assert.ok(key.startsWith("candidate-register:trip_1:"));
  assert.ok(key.length <= 180);
  assert.equal(key, candidateIdempotencyKey("candidate-register", "trip_1", "x".repeat(300)));
});

function candidate(overrides: Partial<TripCandidate> = {}): TripCandidate {
  return {
    id: "cand_1",
    trip_id: "trip_1",
    candidate_type: "place",
    display_name: "思南书局",
    normalized_name: "思南书局",
    category: "scenic",
    coordinates: null,
    address_summary: null,
    estimated_duration_minutes: null,
    preferred_time_block: null,
    explicit_day_reference: null,
    source_kind: "manual_entry",
    source_ref: null,
    evidence_refs: [],
    location_state: "missing",
    route_state: "not_requested",
    duration_state: "missing",
    confidence: "unknown",
    content_digest: "digest",
    workflow_state: "pending",
    latest_decision_id: null,
    created_at: "2026-07-15T00:00:00Z",
    ...overrides,
  };
}
