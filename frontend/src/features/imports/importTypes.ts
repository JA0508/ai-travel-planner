export type SourceArtifact = {
  id: string;
  trip_id: string;
  artifact_type: "text" | "url_document" | "derived_text" | string;
  mime_type: string;
  content_checksum: string;
  byte_size: number;
  charset: string;
  privacy_level: string;
  original_label?: string | null;
  created_at: string;
};

export type ImportJob = {
  id: string;
  trip_id: string;
  artifact_id: string;
  input_type: "text" | "url" | "image" | "pdf" | string;
  status: "created" | "receiving" | "quarantined" | "inspecting" | "artifact_ready" | "needs_password" | "rejected" | "extracting" | "resolving" | "review_ready" | "partial" | "failed" | "committed" | "cancelled" | string;
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

export type URLFetchSnapshot = {
  id: string;
  import_job_id: string;
  raw_artifact_id: string;
  request_url_sanitized: string;
  normalized_request_url: string;
  final_url_sanitized: string;
  redirect_chain: Array<{ from_url: string; to_url: string; status_code: number; validation: string }>;
  robots_status: string;
  robots_checked_at: string;
  status_code: number;
  content_type: string;
  declared_charset?: string | null;
  effective_charset?: string | null;
  content_language?: string | null;
  compressed_bytes: number;
  decoded_bytes: number;
  body_checksum: string;
  fetcher_version: string;
  policy_version: string;
  fetched_at: string;
  warning_codes: string[];
  cache_status: string;
  page_title?: string | null;
  source_host?: string | null;
  final_host?: string | null;
  recovery_actions: string[];
};

export type ArtifactDerivation = {
  id: string;
  parent_artifact_id: string;
  child_artifact_id: string;
  derivation_type: string;
  transformer_version: string;
  input_checksum: string;
  output_checksum: string;
  created_at: string;
};

export type URLImportCreateResponse = TextImportCreateResponse & {
  source_fetch?: URLFetchSnapshot | null;
  derivation?: ArtifactDerivation | null;
};

export type ImportReviewResponse = {
  artifact: SourceArtifact;
  job: ImportJob;
  mentions: ImportMention[];
  source_fetch?: URLFetchSnapshot | null;
  derivation?: ArtifactDerivation | null;
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

export type SafeFinding = {
  id: string;
  inspection_id: string;
  code: string;
  severity: "info" | "warning" | "block";
  category: string;
  evidence: Record<string, string | number | boolean | null>;
  created_at: string;
};

export type BinaryInspectionView = {
  id: string;
  trip_id: string;
  import_job_id: string;
  artifact_id: string;
  attempt: number;
  schema_version: string;
  inspector_version: string;
  declared_kind: "image" | "pdf" | string;
  detected_kind: "image" | "pdf" | string;
  declared_mime_type?: string | null;
  detected_mime_type: string;
  status: "artifact_ready" | "needs_password" | "rejected" | "inspection_failed" | string;
  classification: "artifact_ready" | "needs_password" | "rejected" | "inspection_failed" | string;
  byte_size: number;
  content_checksum: string;
  metadata: Record<string, string | number | boolean | null>;
  sanitized_artifact_id?: string | null;
  manifest_artifact_id?: string | null;
  findings: SafeFinding[];
  warning_codes: string[];
  error_code?: string | null;
  started_at: string;
  completed_at: string;
};

export type BinaryImportCreateResponse = {
  artifact: SourceArtifact;
  job: ImportJob;
  inspection: BinaryInspectionView;
  derivation?: ArtifactDerivation | null;
  duplicate_artifact: boolean;
  idempotent_replay: boolean;
};

export type DocumentTextSpan = {
  id: string;
  generation_id: string;
  span_start: number;
  span_end: number;
  page_number: number;
  block_index: number;
  line_index: number;
  token_index?: number | null;
  block_id?: string | null;
  line_id?: string | null;
  token_id?: string | null;
  reading_order: number;
  bbox: Record<string, string | number | boolean | null>;
  source_kind: "native_pdf_text" | "ocr_token" | "ocr_line" | string;
  confidence?: number | null;
  text_digest: string;
  warning_codes: string[];
  created_at: string;
};

export type DocumentExtractionGeneration = {
  id: string;
  trip_id: string;
  source_import_job_id: string;
  source_artifact_id: string;
  inspection_id: string;
  derived_import_job_id?: string | null;
  derived_artifact_id?: string | null;
  layout_artifact_id?: string | null;
  span_map_artifact_id?: string | null;
  generation: number;
  schema_version: string;
  extractor_version: string;
  strategy: "pdf_native_text" | "image_ocr" | "pdf_native_plus_selective_ocr" | string;
  status: "review_ready" | "partial" | "failed" | string;
  page_count: number;
  extracted_text_chars: number;
  warning_codes: string[];
  error_code?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type DocumentExtractionCreateResponse = {
  generation: DocumentExtractionGeneration;
  artifact?: SourceArtifact | null;
  job?: ImportJob | null;
  mentions: ImportMention[];
  derivation?: ArtifactDerivation | null;
  spans: DocumentTextSpan[];
  duplicate_artifact: boolean;
  idempotent_replay: boolean;
};

export type DocumentMentionEvidence = {
  mention_id: string;
  mention_text: string;
  start_offset: number;
  end_offset: number;
  page_numbers: number[];
  block_ids: string[];
  line_ids: string[];
  token_ids: string[];
  bounding_boxes: Array<Record<string, string | number | boolean | null>>;
  extraction_methods: string[];
  geometry_available: boolean;
};

export type DocumentExtractionEvidenceResponse = {
  generation: DocumentExtractionGeneration;
  artifact: SourceArtifact;
  job: ImportJob;
  layout_manifest: Record<string, unknown>;
  span_map: Array<Record<string, unknown>>;
  mentions: ImportMention[];
  mention_evidence: DocumentMentionEvidence[];
};
