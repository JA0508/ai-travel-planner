export type IntentPlannerReadyStatus = "ready" | "needs_clarification" | "blocked";

export type IntentSourceRef = {
  ref_id: string;
  source_type: string;
  source_id: string | null;
  field_path: string;
  label: string;
  priority: number;
  confirmed: boolean;
  evidence_digest: string;
  evidence_refs: string[];
};

export type TypedIntentValue = {
  field_path: string;
  field_id: string | null;
  value: unknown;
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
  unresolved_questions: IntentClarification[];
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
  value: unknown;
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
  answer_value_type: "string" | "integer" | "pace" | "string_list";
  question: string;
  priority: number;
  blocking: boolean;
  impact: "planner_blocking" | "planner_quality" | "evidence_quality";
  reason_code: string;
  options: unknown[];
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
  clarification_queue: IntentClarification[];
  typed_intent: TypedTripIntent;
  provenance_summary: IntentProvenanceSummary[];
  planner_ready_status: IntentPlannerReadyStatus;
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

export type TripIntentRevisionListResponse = {
  revisions: TripIntentRevisionMetadata[];
};
