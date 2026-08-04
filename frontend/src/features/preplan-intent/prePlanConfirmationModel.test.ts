import assert from "node:assert/strict";
import test from "node:test";
import { buildPrePlanConfirmationViewModel, getPrePlanClarificationControl } from "./prePlanConfirmationModel";
import type { SourceLinkedTripIntentEnvelope } from "@/features/intent-confirmation/intentTypes";

function envelope(overrides: Partial<SourceLinkedTripIntentEnvelope> = {}): SourceLinkedTripIntentEnvelope {
  return {
    id: "intent_1", revision_number: 1, trip_id: "trip_1", base_trip_revision_id: null as never,
    parent_intent_revision_id: null, fields: [
      { field_id: "city", field_path: "trip.city", value: { type: "destination_city", city: "杭州" }, semantic_type: "destination_city", semantic_value: { type: "destination_city", city: "杭州" }, kind: "hard", confidence: 1, source_refs: [{ ref_id: "src", source_type: "direct_user_language", source_id: null, field_path: "trip.city", label: "input", priority: 1, confirmed: true, authority: "user_confirmed", evidence_digest: "digest", evidence_refs: [] }], confirmed_by_user: true, priority: 1, status: "selected", validation_codes: [], explanation: "" },
    ], conflicts: [], assumptions: [], typed_assumptions: [], clarification_queue: [], parser_result: { parser_name: "test", parser_version: "1", status: "success", input_digests: [], extracted_field_paths: [], warnings: [] },
    formal_contract: { schema_version: "1", formal_contract_origin: "deterministic_compiler", formal_contract_verified: true, destinations: [{ city_name: "杭州", country_code: null, timezone: null, order: 0, metadata: {} as never }], date_policy: { start_date: null, end_date: null, trip_days: 2, timezone: "unknown", original_expressions: [], reference_date: null, normalization_rule_codes: [], metadata: {} as never }, arrival_boundary: null, departure_boundary: null, availability_windows: [], fixed_events: [], must_visit_places: [], optional_places: [], avoid_places: [], pace: { value: "relaxed", metadata: {} as never }, transport_preferences: [], meal_preferences: [], budget: null, traveler_needs: [], exclusions: [], assumptions: [], clarifications: [], conflicts: [], readiness: { status: "ready_for_planning", planner_contract_complete: true, blocking_issue_codes: [], unresolved_required_field_paths: [], active_assumption_ids: [], warning_codes: [] } },
    typed_intent: {} as never, provenance_summary: [], provenance_graph: { nodes: [], edges: [] }, planner_ready_status: "ready_for_planning", readiness_policy: null, planner_ready_intent: { city: "杭州", trip_days: 2, must_place_candidate_ids: [], must_place_names: [], pace: "relaxed", transport_preferences: [], fixed_events: [], assumptions: [] }, validation_report: {}, source_digest: "source", semantic_digest: "semantic", lineage_digest: "lineage", content_digest: "content", created_at: "2026-01-01T00:00:00Z", ...overrides,
  };
}

test("simple confirmed trip can continue without optional transport or budget", () => {
  const view = buildPrePlanConfirmationViewModel(envelope());
  assert.equal(view.heading, "可以开始规划");
  assert.equal(view.canGeneratePreview, true);
  assert.match(view.summary.find((item) => item.label === "旅行时间")?.value ?? "", /2 天/);
});

test("missing destination uses plain language and blocks the primary action", () => {
  const view = buildPrePlanConfirmationViewModel(envelope({
    fields: [],
    planner_ready_status: "needs_clarification",
    clarification_queue: [{ question_id: "city", field_paths: ["trip.city"], answer_field_path: "trip.city", answer_value_type: "string", resolution_kind: "inline_answer", editor_field_path: "trip.city", question: "Which destination city should this trip be compiled for?", priority: 1, blocking: true, impact: "planner_blocking", reason_code: "missing_destination", options: [] }],
    formal_contract: { ...envelope().formal_contract, destinations: [], readiness: { ...envelope().formal_contract.readiness, status: "needs_clarification", planner_contract_complete: false, blocking_issue_codes: ["missing_destination"] } },
  }));
  assert.equal(view.canGeneratePreview, false);
  assert.equal(view.blockers[0]?.title, "请填写这次旅行的目的地");
  assert.doesNotMatch(view.blockers[0]?.detail ?? "", /missing_destination/);
});

test("fixed arrangements stay visible in the plain-language confirmation summary", () => {
  const base = envelope();
  const view = buildPrePlanConfirmationViewModel(envelope({
    formal_contract: {
      ...base.formal_contract,
      fixed_events: [{
        event_id: "museum", title: "博物馆预约", start_at: null, end_at: null, timezone: "Asia/Shanghai",
        fixed_day: 2, place_candidate_id: null, location_text: "上海博物馆", flexibility: "fixed", metadata: {} as never,
      }],
    },
  }));
  assert.deepEqual(view.fixedArrangements, [{ title: "博物馆预约", detail: "第 2 天 · 上海博物馆" }]);
});

test("contract-edit blockers reuse the matching pre-plan editor", () => {
  assert.equal(
    getPrePlanClarificationControl({
      question_id: "fixed-event", field_paths: ["time.fixed_events"], answer_field_path: null, answer_value_type: null,
      resolution_kind: "edit_contract", editor_field_path: "time.fixed_events", question: "Fixed event is outside the trip.",
      priority: 98, blocking: true, impact: "planner_blocking", reason_code: "fixed_event_outside_trip_dates", options: [],
    }),
    "date_choice",
  );
  assert.equal(
    getPrePlanClarificationControl({
      question_id: "pace-conflict", field_paths: ["trip.pace"], answer_field_path: null, answer_value_type: null,
      resolution_kind: "edit_contract", editor_field_path: "trip.pace", question: "Choose the pace.",
      priority: 95, blocking: true, impact: "planner_blocking", reason_code: "same_priority_conflict", options: [],
    }),
    "pace",
  );
  assert.equal(
    getPrePlanClarificationControl({
      question_id: "legacy-date", field_paths: ["trip.trip_days"], answer_field_path: "trip.trip_days", answer_value_type: "integer",
      resolution_kind: "inline_answer", editor_field_path: "trip.trip_days", question: "How long is the trip?",
      priority: 70, blocking: true, impact: "planner_blocking", reason_code: "trip_dates_missing", options: [],
    }),
    "trip_days",
  );
});
