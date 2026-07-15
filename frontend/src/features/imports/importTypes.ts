export type SourceArtifact = {
  id: string;
  trip_id: string;
  artifact_type: "text";
  mime_type: "text/plain";
  content_checksum: string;
  byte_size: number;
  charset: "utf-8";
  privacy_level: string;
  original_label?: string | null;
  created_at: string;
};

export type ImportJob = {
  id: string;
  trip_id: string;
  artifact_id: string;
  input_type: "text";
  status: "created" | "extracting" | "resolving" | "review_ready" | "partial" | "failed" | "committed" | "cancelled" | string;
  extraction_schema_version: string;
  extractor_version: string;
  resolver_version: string;
  review_version: number;
  mention_count: number;
  warning_codes: string[];
  error_code?: string | null;
  committed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type ResolvedPlaceCandidate = {
  id: string;
  mention_id: string;
  provider: string;
  provider_place_id?: string | null;
  canonical_name: string;
  address_summary?: string | null;
  administrative_area?: string | null;
  city_code?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  category?: string | null;
  confidence: number;
  resolution_reason_codes: string[];
  data_state: "resolved" | "ambiguous" | "missing" | "provider_failed" | "cross_city" | "partial" | string;
  candidate_digest: string;
  created_at: string;
};

export type ImportMention = {
  id: string;
  import_job_id: string;
  artifact_id: string;
  entity_type: "place" | "fixed_event" | "time_constraint" | "note" | string;
  raw_text: string;
  normalized_text?: string | null;
  start_offset: number;
  end_offset: number;
  context_before: string;
  context_after: string;
  city_hint?: string | null;
  date_hint?: string | null;
  time_hint?: string | null;
  recommendation_reason?: string | null;
  confidence: number;
  extraction_warning_codes: string[];
  content_digest: string;
  review_state: "needs_review" | "confirmed" | "ambiguous" | "duplicate" | "ignored" | "note" | "unresolved" | string;
  selected_resolution_candidate_id?: string | null;
  latest_decision?: ImportReviewDecision | null;
  resolution_candidates: ResolvedPlaceCandidate[];
  created_at: string;
};

export type ImportReviewDecision = {
  id: string;
  import_job_id: string;
  mention_id: string;
  review_version: number;
  action: string;
  selected_resolution_candidate_id?: string | null;
  merge_target_mention_id?: string | null;
  note_text?: string | null;
  reason_code?: string | null;
  created_at: string;
  idempotent_replay?: boolean;
};

export type TextImportCreateResponse = {
  artifact: SourceArtifact;
  job: ImportJob;
  mentions: ImportMention[];
  duplicate_artifact: boolean;
  idempotent_replay: boolean;
};

export type ImportReviewResponse = {
  artifact: SourceArtifact;
  job: ImportJob;
  mentions: ImportMention[];
};

export type ImportCommitResult = {
  import_job_id: string;
  review_version: number;
  place_candidates_created: number;
  place_candidates_reused: number;
  candidate_ids: string[];
  notes_preserved: number;
  constraint_mentions_preserved: number;
  ignored_mentions: number;
  unresolved_mentions: number;
  committed_at: string;
  idempotent_replay: boolean;
};
