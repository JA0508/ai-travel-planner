import assert from "node:assert/strict";
import test from "node:test";
import {
  buildIntentCompileIdempotencyKey,
  compareIntentContracts,
  formatIntentDomainValue,
  summarizeIntentEnvelope,
} from "./intentConfirmationModel";
import type { SourceLinkedTripIntentEnvelope } from "./intentTypes";

test("intent compile idempotency key is bounded and does not leak raw source text", () => {
  const key = buildIntentCompileIdempotencyKey("trip_1", "rev_1", "城市：上海，不要太赶");
  assert.ok(key.startsWith("intent-compile:trip_1:rev_1:"));
  assert.ok(key.length <= 140);
  assert.equal(key.includes("上海"), false);
});

test("intent summary separates selected and shadowed fields", () => {
  const summary = summarizeIntentEnvelope(envelope({
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
      parser_version: "intent-compiler-v5",
      status: "success",
      input_digests: [],
      extracted_field_paths: ["trip.city"],
      warnings: [],
    },
    formal_contract: formalContract("intent_1", 1, "上海", 2),
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
  }));
  assert.equal(summary.statusLabel, "Planner-ready");
  assert.equal(summary.selectedFields.length, 1);
  assert.equal(summary.shadowedFields.length, 1);
  assert.equal(summary.assumptionCount, 1);
});

test("formal contract semantic compare ignores lineage churn and reports domain changes", () => {
  const base = envelope({
    id: "intent_1",
    revision_number: 1,
    formal_contract: formalContract("intent_1", 1, "上海", 2),
    semantic_digest: "same-semantic",
    lineage_digest: "lineage-a",
  });
  const sameDomainNewLineage = envelope({
    id: "intent_2",
    revision_number: 2,
    parent_intent_revision_id: "intent_1",
    formal_contract: formalContract("intent_2", 2, "上海", 2),
    semantic_digest: "same-semantic",
    lineage_digest: "lineage-b",
  });
  const changedDomain = envelope({
    id: "intent_3",
    revision_number: 3,
    parent_intent_revision_id: "intent_2",
    formal_contract: formalContract("intent_3", 3, "杭州", 3),
    semantic_digest: "changed-semantic",
    lineage_digest: "lineage-c",
  });

  assert.equal(compareIntentContracts(base, sameDomainNewLineage).identical, true);
  const changed = compareIntentContracts(sameDomainNewLineage, changedDomain);
  assert.equal(changed.identical, false);
  assert.deepEqual(
    changed.changed.map((item) => item.fieldPath),
    ["trip.city", "trip.trip_days"],
  );
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

function envelope(
  overrides: Partial<SourceLinkedTripIntentEnvelope> & Pick<SourceLinkedTripIntentEnvelope, "id" | "revision_number" | "formal_contract">,
): SourceLinkedTripIntentEnvelope {
  const { id, revision_number, formal_contract, ...rest } = overrides;
  return {
    id,
    revision_number,
    trip_id: "trip_1",
    base_trip_revision_id: "rev_1",
    parent_intent_revision_id: null,
    fields: [
      field("city-a", "trip.city", { type: "destination_city", city: "上海" }, "selected"),
      field("city-b", "trip.city", { type: "destination_city", city: "北京" }, "shadowed"),
    ],
    conflicts: [
      {
        conflict_id: "conf_1",
        field_path: "trip.city",
        severity: "non_blocking",
        reason_code: "higher_priority_source_selected",
        explanation: "manual wins",
        requires_clarification: false,
        source_refs: [],
      },
    ],
    assumptions: ["No reviewed must-visit TripCandidate has been selected yet."],
    typed_assumptions: [],
    clarification_queue: [],
    parser_result: {
      parser_name: "deterministic_text_fallback",
      parser_version: "intent-compiler-v5",
      status: "success",
      input_digests: [],
      extracted_field_paths: ["trip.city"],
      warnings: [],
    },
    formal_contract,
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
    planner_ready_status: "ready_for_planning",
    readiness_policy: {
      policy_version: "intent-readiness-v3",
      status: "ready_for_planning",
      blocking_reason_codes: [],
      allowed_assumption_ids: [],
      requires_user_confirmation: false,
    },
    planner_ready_intent: {
      city: "上海",
      trip_days: 2,
      must_place_candidate_ids: [],
      must_place_names: [],
      pace: null,
      transport_preferences: [],
      fixed_events: [],
      assumptions: [],
    },
    validation_report: {},
    source_digest: "source",
    semantic_digest: "semantic",
    lineage_digest: "lineage",
    content_digest: "content",
    created_at: "2026-07-21T00:00:00Z",
    ...rest,
  };
}

function formalContract(
  revisionId: string,
  revisionNumber: number,
  city: string,
  tripDays: number,
): SourceLinkedTripIntentEnvelope["formal_contract"] {
  return {
    schema_version: "1.4",
    destinations: [
      {
        city_name: city,
        country_code: null,
        timezone: null,
        order: 0,
        metadata: metadata("trip.city", revisionId, revisionNumber),
      },
    ],
    date_policy: {
      trip_days: tripDays,
      start_date: null,
      end_date: null,
      timezone: "unknown",
      original_expressions: [],
      reference_date: null,
      normalization_rule_codes: [],
      metadata: metadata("trip.trip_days", revisionId, revisionNumber),
    },
    formal_contract_origin: "deterministic_compiler",
    formal_contract_verified: true,
    arrival_boundary: null,
    departure_boundary: null,
    availability_windows: [],
    fixed_events: [],
    must_visit_places: [],
    optional_places: [],
    avoid_places: [],
    pace: null,
    transport_preferences: [],
    meal_preferences: [],
    budget: null,
    traveler_needs: [],
    exclusions: [],
    assumptions: [],
    clarifications: [],
    conflicts: [],
    readiness: {
      status: "ready_for_planning",
      planner_contract_complete: true,
      blocking_issue_codes: [],
      unresolved_required_field_paths: [],
      active_assumption_ids: [],
      warning_codes: [],
    },
  };
}

function metadata(
  fieldPath: string,
  revisionId: string,
  revisionNumber: number,
): SourceLinkedTripIntentEnvelope["formal_contract"]["destinations"][number]["metadata"] {
  return {
    field_id: `field-${revisionId}`,
    field_path: fieldPath,
    kind: "hard",
    authority: "user_confirmed",
    confirmation_state: "user_confirmed",
    confidence: 1,
    source_refs: [],
    compiler_rule_code: "test",
    warning_codes: [],
  };
}
