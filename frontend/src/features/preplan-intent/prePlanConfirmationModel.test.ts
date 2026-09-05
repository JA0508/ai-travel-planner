import assert from "node:assert/strict";
import test from "node:test";
import { buildPrePlanConfirmationViewModel } from "./prePlanConfirmationModel";
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

test("direct must-visit place identities are shown in the confirmation summary", () => {
  const base = envelope();
  const view = buildPrePlanConfirmationViewModel(envelope({
    formal_contract: {
      ...base.formal_contract,
      place_identities: [{
        stable_id: "hongyadong", original_name: "洪崖洞", canonical_name: null, city: "重庆", ownership: "must",
        fixed_event_id: null, resolution_status: "ambiguous", provider: null, provider_place_id: null,
        latitude: null, longitude: null, category: null, source_fragment_ids: ["source"], confirmation_options: [], resolution_confidence: null,
      }],
    },
  }));

  assert.equal(view.summary.find((item) => item.label === "想去的地方")?.value, "1 个一定想去");
  assert.deepEqual(view.mustPlaces, [{ id: "hongyadong", name: "洪崖洞", source: "direct" }]);
});

test("an old inconsistent Draft cannot preview while its fixed place is unconfirmed", () => {
  const base = envelope();
  const view = buildPrePlanConfirmationViewModel(envelope({
    formal_contract: {
      ...base.formal_contract,
      fixed_events: [{
        event_id: "museum", title: "博物馆预约", start_at: null, end_at: null, timezone: "Asia/Shanghai",
        fixed_day: 2, place_candidate_id: null, location_text: "上海博物馆", flexibility: "fixed", metadata: {} as never,
      }],
      place_identities: [{
        stable_id: "museum", original_name: "上海博物馆", canonical_name: null, city: "上海", ownership: "fixed",
        fixed_event_id: "museum", resolution_status: "ambiguous", provider: null, provider_place_id: null,
        latitude: null, longitude: null, category: null, source_fragment_ids: ["source"], confirmation_options: [], resolution_confidence: null,
      }],
    },
  }));
  assert.equal(view.canGeneratePreview, false);
  assert.equal(view.heading, "还需要补充信息");
  assert.deepEqual(view.confirmationItems, [{
    id: "fixed-place:museum",
    kind: "fixed_place",
    title: "博物馆预约",
    detail: "这段时间会被保留；请确认具体地点后再安排路线。",
    eventId: "museum",
    identityId: "museum",
    tone: "todo",
  }]);
  assert.equal(view.remainingConfirmationCount, 1);
  assert.deepEqual(view.blockers, []);
});

test("must-place identity appears once in the shared confirmation queue", () => {
  const base = envelope();
  const view = buildPrePlanConfirmationViewModel(envelope({
    planner_ready_status: "needs_clarification",
    formal_contract: {
      ...base.formal_contract,
      readiness: { ...base.formal_contract.readiness, status: "needs_clarification", planner_contract_complete: false, blocking_issue_codes: ["must_place_identity_not_verified"] },
      place_identities: [{
        stable_id: "hongyadong", original_name: "洪崖洞", canonical_name: null, city: "重庆", ownership: "must",
        fixed_event_id: null, resolution_status: "ambiguous", provider: "amap", provider_place_id: null,
        latitude: null, longitude: null, category: null, source_fragment_ids: ["source"], confirmation_options: [], resolution_confidence: null,
      }],
    },
  }));

  assert.deepEqual(view.confirmationItems, [{
    id: "must-place:hongyadong",
    kind: "must_place",
    title: "确认「洪崖洞」具体是哪一处",
    detail: "确认后才会使用真实的位置和路线数据。",
    identityId: "hongyadong",
    tone: "todo",
  }]);
  assert.equal(view.remainingConfirmationCount, 1);
  assert.deepEqual(view.blockers, []);
});

test("fixed events retain their own identity state in the queue", () => {
  const base = envelope();
  const fixedEvent = (event_id: string, title: string) => ({
    event_id, title, start_at: null, end_at: null, timezone: "Asia/Shanghai",
    fixed_day: 2, place_candidate_id: null, location_text: null, flexibility: "fixed" as const, metadata: {} as never,
  });
  const fixedIdentity = (stable_id: string, resolution_status: "verified" | "ambiguous") => ({
    stable_id, original_name: stable_id, canonical_name: resolution_status === "verified" ? `${stable_id} 已确认地点` : null,
    city: "上海", ownership: "fixed" as const, fixed_event_id: stable_id, resolution_status,
    provider: null, provider_place_id: null, latitude: null, longitude: null, category: null,
    source_fragment_ids: ["source"], confirmation_options: [], resolution_confidence: null,
  });
  const view = buildPrePlanConfirmationViewModel(envelope({
    planner_ready_status: "needs_clarification",
    formal_contract: {
      ...base.formal_contract,
      readiness: { ...base.formal_contract.readiness, status: "needs_clarification", planner_contract_complete: false, blocking_issue_codes: ["fixed_event_identity_not_verified"] },
      fixed_events: [fixedEvent("museum", "博物馆预约"), fixedEvent("show", "演出票")],
      place_identities: [fixedIdentity("museum", "verified"), fixedIdentity("show", "ambiguous")],
    },
  }));

  assert.deepEqual(view.confirmationItems, [{
    id: "fixed-place:show",
    kind: "fixed_place",
    title: "演出票",
    detail: "这段时间会被保留；请确认具体地点后再安排路线。",
    eventId: "show",
    identityId: "show",
    tone: "todo",
  }]);
  assert.deepEqual(view.confirmedItems, [{
    id: "confirmed-fixed:museum",
    title: "博物馆预约",
    detail: "museum 已确认地点 · 时间已保留",
  }]);
});
