export type IntentPlannerReadyStatus =
  | "ready"
  | "ready_with_assumptions"
  | "ready_for_planning"
  | "needs_clarification"
  | "blocked";

export type IntentSourceRef = {
  ref_id: string;
  source_type: string;
  source_id: string | null;
  field_path: string;
  label: string;
  priority: number;
  confirmed: boolean;
  authority: string;
  evidence_digest: string;
  evidence_refs: string[];
};

export type IntentDomainValue =
  | { type: "destination_city"; city: string }
  | { type: "trip_days"; days: number }
  | { type: "pace"; pace: "relaxed" | "balanced" | "intensive" }
  | { type: "transport_preference"; mode: string }
  | { type: "must_candidate"; candidate_id: string; display_name?: string | null }
  | { type: "optional_candidate"; candidate_id: string; display_name?: string | null }
  | { type: "avoid_candidate"; candidate_id: string; display_name?: string | null }
  | {
      type: "fixed_event";
      name: string;
      fixed_day?: number | null;
      fixed_time_start?: string | null;
      fixed_time_end?: string | null;
      source_label?: string | null;
      event_id?: string | null;
      start_at?: string | null;
      end_at?: string | null;
      timezone?: string | null;
      location_text?: string | null;
      flexibility?: "fixed" | "movable_with_confirmation";
    }
  | { type: "general_preference"; preference: string }
  | {
      type: "budget";
      amount_minor?: number | null;
      currency?: string | null;
      scope?: "total" | "per_person" | "per_day" | null;
      budget_level?: "low" | "medium" | "high" | null;
      flexibility_percent?: number;
    }
  | {
      type: "traveler_need";
      need: string;
      traveler_group?: string | null;
      need_type?: "mobility" | "wheelchair" | "child" | "elderly" | "dietary" | "medical" | "sensory" | "other";
      severity?: "required" | "preferred";
    }
  | { type: "unknown"; raw?: unknown };

export type TypedIntentValue = {
  field_path: string;
  field_id: string | null;
  value: IntentDomainValue;
  semantic_type: string;
  semantic_value: IntentDomainValue;
  kind: "hard" | "soft" | "assumption";
  confidence: number;
  confirmed_by_user: boolean;
  source_refs: IntentSourceRef[];
  validation_codes: string[];
};

export type TypedTripIntent = {
  destinations: TypedIntentValue[];
  date_policy: {
    trip_days: TypedIntentValue | null;
    availability_windows: TypedIntentValue[];
  };
  fixed_events: TypedIntentValue[];
  poi_preferences: {
    must_candidates: TypedIntentValue[];
    optional_candidates: TypedIntentValue[];
    exclusions: TypedIntentValue[];
  };
  pace: TypedIntentValue | null;
  transport_preferences: TypedIntentValue[];
  budget: TypedIntentValue | null;
  travelers: TypedIntentValue[];
  assumptions: string[];
  typed_assumptions: IntentAssumption[];
  unresolved_questions: IntentClarification[];
};

export type IntentAssumption = {
  assumption_id: string;
  field_path: string;
  assumption_type: "missing_value" | "empty_reviewed_candidate_set" | "carried_forward_assumption";
  value: IntentDomainValue | IntentDomainValue[] | null;
  has_assumed_value: boolean;
  blocks_planner_ready: boolean;
  reason_code: string;
  explanation: string;
  source_refs: IntentSourceRef[];
};

export type IntentProvenanceSummary = {
  field_path: string;
  selected_field_ids: string[];
  shadowed_field_ids: string[];
  source_types: string[];
  evidence_refs: string[];
  confirmed: boolean;
  max_confidence: number;
};

export type IntentField = {
  field_id: string;
  field_path: string;
  value: IntentDomainValue;
  semantic_type: string;
  semantic_value: IntentDomainValue;
  kind: "hard" | "soft" | "assumption";
  confidence: number;
  source_refs: IntentSourceRef[];
  confirmed_by_user: boolean;
  priority: number;
  status: "selected" | "shadowed" | "needs_clarification";
  validation_codes: string[];
  explanation: string;
};

export type IntentConflict = {
  conflict_id: string;
  field_path: string;
  severity: "blocking" | "non_blocking";
  reason_code: string;
  explanation: string;
  requires_clarification: boolean;
  source_refs: IntentSourceRef[];
};

export type IntentClarification = {
  question_id: string;
  field_paths: string[];
  answer_field_path: string | null;
  answer_value_type: "string" | "integer" | "pace" | "string_list" | "fixed_event" | "budget" | null;
  resolution_kind: "inline_answer" | "edit_contract" | "reimport_evidence";
  editor_field_path: string | null;
  question: string;
  priority: number;
  blocking: boolean;
  impact: "planner_blocking" | "planner_quality" | "evidence_quality";
  reason_code: string;
  options: unknown[];
};

export type IntentParserResult = {
  parser_name: string;
  parser_version: string;
  model_name?: string | null;
  status: "success" | "empty_input" | "unavailable" | "timeout" | "invalid_output" | "provider_error";
  input_digests: string[];
  extracted_field_paths: string[];
  warnings: string[];
};

export type IntentSourceReference = {
  source_type: string;
  source_id: string | null;
  artifact_id: string | null;
  import_job_id: string | null;
  mention_id: string | null;
  review_decision_id: string | null;
  candidate_id: string | null;
  page_number: number | null;
  bbox: Record<string, number | string> | null;
  field_path: string;
  label: string;
  authority: string;
  confirmed: boolean;
  confidence: number;
  observed_at: string | null;
  evidence_digest: string;
  evidence_refs: string[];
};

export type IntentFieldMetadata = {
  field_path: string;
  semantic_type: string;
  kind: "hard" | "soft" | "assumption";
  authority: string;
  confidence: number;
  confirmed_by_user: boolean;
  status: "selected" | "shadowed" | "needs_clarification";
  source_refs: IntentSourceReference[];
  validation_codes: string[];
  revision_id: string;
  revision_number: number;
};

export type FormalIntentMetadata = {
  field_id: string;
  field_path: string;
  kind: "hard" | "soft" | "assumption";
  confirmation_state: "user_confirmed" | "review_confirmed" | "proposed" | "assumed" | "conflicted" | "superseded";
  authority: "user_confirmed" | "review_confirmed" | "saved_state" | "direct_user_proposal" | "llm_untrusted" | "system_assumption";
  confidence: number | null;
  source_refs: IntentSourceReference[];
  compiler_rule_code: string;
  warning_codes: string[];
};

export type DestinationIntent = {
  city_name: string;
  country_code: string | null;
  timezone: string | null;
  order: number;
  metadata: FormalIntentMetadata;
};

export type DatePolicyIntent = {
  start_date: string | null;
  end_date: string | null;
  trip_days: number | null;
  timezone: string;
  original_expressions: string[];
  reference_date: string | null;
  normalization_rule_codes: string[];
  metadata: FormalIntentMetadata;
};

export type PaceIntent = { metadata: FormalIntentMetadata; value: "relaxed" | "balanced" | "intensive" };

export type TravelBoundaryIntent = {
  metadata: FormalIntentMetadata;
  boundary_type: "arrival" | "departure";
  local_datetime: string;
  timezone: string;
  flexibility_minutes: number;
  location_candidate_id: string | null;
  location_text: string | null;
};

export type AvailabilityWindowIntent = {
  metadata: FormalIntentMetadata;
  date: string;
  start_time: string;
  end_time: string;
  timezone: string;
  crosses_midnight: boolean;
};

export type FixedEventIntent = {
  metadata: FormalIntentMetadata;
  event_id: string;
  title: string;
  start_at: string | null;
  end_at: string | null;
  timezone: string | null;
  fixed_day: number | null;
  place_candidate_id: string | null;
  location_text: string | null;
  flexibility: "fixed" | "movable_with_confirmation";
};

export type PlacePreferenceIntent = {
  metadata: FormalIntentMetadata;
  trip_candidate_id: string;
  display_name: string | null;
  preference: "must" | "optional" | "avoid";
  strength: number;
};

export type TransportPreferenceIntent = {
  metadata: FormalIntentMetadata;
  mode: "walk" | "metro" | "bus" | "taxi" | "ride_hailing" | "drive" | "bike" | "rail" | "flight" | "other";
  preference: "prefer" | "avoid" | "require";
  custom_label: string | null;
};

export type BudgetIntent = {
  metadata: FormalIntentMetadata;
  amount_minor: number | null;
  currency: string | null;
  scope: "total" | "per_person" | "per_day" | null;
  level: "low" | "medium" | "high" | null;
  flexibility_percent: number;
};

export type TravelerNeedIntent = {
  metadata: FormalIntentMetadata;
  need_type: "mobility" | "wheelchair" | "child" | "elderly" | "dietary" | "medical" | "sensory" | "other";
  description: string;
  severity: "required" | "preferred";
};

export type FormalPlanningAssumption = {
  assumption_id: string;
  field_path: string;
  assumed_value: string | number | boolean;
  value_type: "integer" | "string" | "date" | "datetime" | "enum" | "boolean";
  reason_code: string;
  impact: "medium" | "low";
  source_refs: IntentSourceReference[];
  user_acknowledged: boolean;
  supersedes_clarification_id: string | null;
};

export type FormalTripIntentContract = {
  schema_version: string;
  formal_contract_origin: "deterministic_compiler" | "legacy_backfill";
  formal_contract_verified: boolean;
  destinations: DestinationIntent[];
  date_policy: DatePolicyIntent | null;
  arrival_boundary: TravelBoundaryIntent | null;
  departure_boundary: TravelBoundaryIntent | null;
  availability_windows: AvailabilityWindowIntent[];
  fixed_events: FixedEventIntent[];
  must_visit_places: PlacePreferenceIntent[];
  optional_places: PlacePreferenceIntent[];
  avoid_places: PlacePreferenceIntent[];
  pace: PaceIntent | null;
  transport_preferences: TransportPreferenceIntent[];
  meal_preferences: Array<{ metadata: FormalIntentMetadata; preference_text: string; preference: "prefer" | "avoid" | "require" }>;
  budget: BudgetIntent | null;
  traveler_needs: TravelerNeedIntent[];
  exclusions: Array<{ metadata: FormalIntentMetadata; exclusion_text: string }>;
  assumptions: FormalPlanningAssumption[];
  clarifications: IntentClarification[];
  conflicts: IntentConflict[];
  readiness: {
    status: "blocked" | "needs_clarification" | "ready_with_assumptions" | "ready_for_planning";
    planner_contract_complete: boolean;
    blocking_issue_codes: string[];
    unresolved_required_field_paths: string[];
    active_assumption_ids: string[];
    warning_codes: string[];
  };
};

export type IntentStructuredOverrides = {
  city: string | null;
  trip_days: number | null;
  start_date: string | null;
  end_date: string | null;
  timezone: string | null;
  arrival_boundary: {
    local_datetime: string;
    timezone: string;
    flexibility_minutes: number;
    location_text: string | null;
  } | null;
  departure_boundary: {
    local_datetime: string;
    timezone: string;
    flexibility_minutes: number;
    location_text: string | null;
  } | null;
  availability_windows: Array<{
    date: string;
    start_time: string;
    end_time: string;
    timezone: string;
    crosses_midnight: boolean;
  }>;
  fixed_events: Array<{
    event_id: string;
    name: string;
    start_at: string | null;
    end_at: string | null;
    timezone: string | null;
    fixed_day: number | null;
    location_text: string | null;
    flexibility: "fixed" | "movable_with_confirmation";
  }>;
  must_candidate_ids: string[];
  optional_candidate_ids: string[];
  avoid_candidate_ids: string[];
  pace: "relaxed" | "balanced" | "intensive" | null;
  transport_preferences: string[];
  budget: {
    type: "budget";
    amount_minor: number | null;
    currency: string | null;
    scope: "total" | "per_person" | "per_day" | null;
    budget_level: "low" | "medium" | "high" | null;
    flexibility_percent: number;
  } | null;
  traveler_needs: Array<{
    type: "traveler_need";
    need: string;
    need_type: "mobility" | "wheelchair" | "child" | "elderly" | "dietary" | "medical" | "sensory" | "other";
    severity: "required" | "preferred";
  }>;
};

export type IntentProvenanceGraph = {
  nodes: Array<{
    node_id: string;
    node_type: string;
    label: string;
    field_path: string | null;
    source_type: string | null;
    source_id: string | null;
    artifact_id: string | null;
    import_job_id: string | null;
    mention_id: string | null;
    review_decision_id: string | null;
    candidate_id: string | null;
    page_number: number | null;
    bbox: Record<string, number | string> | null;
    authority: string;
    confirmed: boolean;
    digest: string | null;
  }>;
  edges: Array<{
    from_node_id: string;
    to_node_id: string;
    relation: string;
  }>;
};

export type IntentReadinessPolicy = {
  policy_version: string;
  status: IntentPlannerReadyStatus;
  blocking_reason_codes: string[];
  allowed_assumption_ids: string[];
  requires_user_confirmation: boolean;
};

export type SourceLinkedTripIntentEnvelope = {
  id: string;
  revision_number: number;
  trip_id: string;
  base_trip_revision_id: string;
  parent_intent_revision_id: string | null;
  fields: IntentField[];
  conflicts: IntentConflict[];
  assumptions: string[];
  typed_assumptions: IntentAssumption[];
  clarification_queue: IntentClarification[];
  parser_result: IntentParserResult;
  formal_contract: FormalTripIntentContract;
  typed_intent: TypedTripIntent;
  provenance_summary: IntentProvenanceSummary[];
  provenance_graph: IntentProvenanceGraph;
  planner_ready_status: IntentPlannerReadyStatus;
  readiness_policy: IntentReadinessPolicy | null;
  planner_ready_intent: {
    city: string | null;
    trip_days: number | null;
    must_place_candidate_ids: string[];
    must_place_names: string[];
    pace: string | null;
    transport_preferences: string[];
    fixed_events: Array<Record<string, unknown>>;
    assumptions: string[];
  };
  validation_report: Record<string, unknown>;
  source_digest: string;
  semantic_digest: string | null;
  lineage_digest: string | null;
  content_digest: string;
  created_at: string;
};

export type TripIntentRevisionMetadata = {
  id: string;
  trip_id: string;
  revision_number: number;
  base_trip_revision_id: string;
  parent_intent_revision_id: string | null;
  envelope_schema_version: string;
  compiler_version: string;
  source_digest: string;
  content_digest: string;
  created_at: string;
};

export type CompileTripIntentResponse = {
  envelope: SourceLinkedTripIntentEnvelope;
  revision: TripIntentRevisionMetadata;
  idempotent_replay: boolean;
};

export type TripIntentRevisionDetailResponse = {
  envelope: SourceLinkedTripIntentEnvelope;
  revision: TripIntentRevisionMetadata;
};

export type TripIntentRevisionListResponse = {
  revisions: TripIntentRevisionMetadata[];
};
