import assert from "node:assert/strict";
import test from "node:test";
import { buildIntentCompileIdempotencyKey, formatIntentDomainValue, summarizeIntentEnvelope } from "./intentConfirmationModel";

test("intent compile idempotency key is bounded and does not leak raw source text", () => {
  const key = buildIntentCompileIdempotencyKey("trip_1", "rev_1", "城市：上海，不要太赶");
  assert.ok(key.startsWith("intent-compile:trip_1:rev_1:"));
  assert.ok(key.length <= 140);
  assert.equal(key.includes("上海"), false);
});

test("intent summary separates selected and shadowed fields", () => {
  const summary = summarizeIntentEnvelope({
    id: "intent_1",
    revision_number: 1,
    trip_id: "trip_1",
    base_trip_revision_id: "rev_1",
    parent_intent_revision_id: null,
    fields: [
      field("city-a", "trip.city", { type: "destination_city", city: "上海" }, "selected"),
      field("city-b", "trip.city", { type: "destination_city", city: "北京" }, "shadowed"),
    ],
    conflicts: [{ conflict_id: "conf_1", field_path: "trip.city", severity: "non_blocking", reason_code: "higher_priority_source_selected", explanation: "manual wins", requires_clarification: false, source_refs: [] }],
    assumptions: ["No reviewed must-visit TripCandidate has been selected yet."],
    typed_assumptions: [],
    clarification_queue: [],
    parser_result: {
      parser_name: "deterministic_text_fallback",
      parser_version: "intent-compiler-v4",
      status: "parsed",
      input_digests: [],
      extracted_field_paths: ["trip.city"],
      warnings: [],
    },
    typed_intent: {
      destinations: [],
      date_policy: { trip_days: null, availability_windows: [] },
      fixed_events: [],
      poi_preferences: { must_candidates: [], optional_candidates: [], exclusions: [] },
      pace: null,
      transport_preferences: [],
      budget: null,
      travelers: [],
      assumptions: ["No reviewed must-visit TripCandidate has been selected yet."],
      typed_assumptions: [],
      unresolved_questions: [],
    },
    provenance_summary: [],
    provenance_graph: { nodes: [], edges: [] },
    planner_ready_status: "ready",
    readiness_policy: {
      policy_version: "intent-readiness-v2",
      status: "ready",
      blocking_reason_codes: [],
      allowed_assumption_ids: [],
      requires_user_confirmation: false,
    },
    planner_ready_intent: { city: "上海", trip_days: 2, must_place_candidate_ids: [], must_place_names: [], pace: null, transport_preferences: [], fixed_events: [], assumptions: [] },
    validation_report: {},
    source_digest: "source",
    semantic_digest: "semantic",
    lineage_digest: "lineage",
    content_digest: "content",
    created_at: "2026-07-21T00:00:00Z",
  });
  assert.equal(summary.statusLabel, "Planner-ready");
  assert.equal(summary.selectedFields.length, 1);
  assert.equal(summary.shadowedFields.length, 1);
  assert.equal(summary.assumptionCount, 1);
});

test("intent domain values format without leaking raw envelopes", () => {
  assert.equal(formatIntentDomainValue({ type: "destination_city", city: "上海" }), "上海");
  assert.equal(formatIntentDomainValue({ type: "trip_days", days: 3 }), "3 days");
  assert.equal(formatIntentDomainValue({ type: "must_candidate", candidate_id: "cand_1", display_name: "豫园" }), "豫园 (cand_1)");
});

function field(
  id: string,
  path: string,
  value: { type: "destination_city"; city: string },
  status: "selected" | "shadowed",
) {
  return {
    field_id: id,
    field_path: path,
    value,
    semantic_type: path === "trip.city" ? "destination_city" : "unknown",
    semantic_value: value,
    kind: "hard" as const,
    confidence: 1,
    source_refs: [],
    confirmed_by_user: true,
    priority: 80,
    status,
    validation_codes: [],
    explanation: "",
  };
}
