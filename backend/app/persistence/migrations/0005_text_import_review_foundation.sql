CREATE TABLE IF NOT EXISTS source_artifacts (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  artifact_type TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  content_checksum TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  charset TEXT NOT NULL,
  privacy_level TEXT NOT NULL,
  storage_key TEXT NOT NULL,
  original_label TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(trip_id, artifact_type, content_checksum)
);

CREATE TABLE IF NOT EXISTS import_jobs (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  artifact_id TEXT NOT NULL REFERENCES source_artifacts(id) ON DELETE CASCADE,
  input_type TEXT NOT NULL,
  status TEXT NOT NULL,
  extraction_schema_version TEXT NOT NULL,
  extractor_version TEXT NOT NULL,
  resolver_version TEXT NOT NULL,
  review_version INTEGER NOT NULL DEFAULT 0,
  mention_count INTEGER NOT NULL DEFAULT 0,
  warning_codes_json TEXT NOT NULL,
  error_code TEXT,
  committed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_processing_attempts (
  id TEXT PRIMARY KEY,
  import_job_id TEXT NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  extractor_version TEXT,
  resolver_version TEXT,
  status TEXT NOT NULL,
  warning_codes_json TEXT NOT NULL,
  error_code TEXT,
  started_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS extracted_mentions (
  id TEXT PRIMARY KEY,
  import_job_id TEXT NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
  artifact_id TEXT NOT NULL REFERENCES source_artifacts(id) ON DELETE CASCADE,
  entity_type TEXT NOT NULL,
  raw_text TEXT NOT NULL,
  normalized_text TEXT,
  start_offset INTEGER NOT NULL,
  end_offset INTEGER NOT NULL,
  context_before TEXT NOT NULL,
  context_after TEXT NOT NULL,
  city_hint TEXT,
  date_hint TEXT,
  time_hint TEXT,
  recommendation_reason TEXT,
  confidence REAL NOT NULL,
  extraction_warning_codes_json TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(import_job_id, content_digest)
);

CREATE TABLE IF NOT EXISTS resolved_place_candidates (
  id TEXT PRIMARY KEY,
  mention_id TEXT NOT NULL REFERENCES extracted_mentions(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  provider_place_id TEXT,
  canonical_name TEXT NOT NULL,
  address_summary TEXT,
  administrative_area TEXT,
  city_code TEXT,
  latitude REAL,
  longitude REAL,
  category TEXT,
  confidence REAL NOT NULL,
  resolution_reason_codes_json TEXT NOT NULL,
  data_state TEXT NOT NULL,
  candidate_digest TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_review_decisions (
  id TEXT PRIMARY KEY,
  import_job_id TEXT NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
  mention_id TEXT NOT NULL REFERENCES extracted_mentions(id) ON DELETE CASCADE,
  review_version INTEGER NOT NULL,
  action TEXT NOT NULL,
  selected_resolution_candidate_id TEXT REFERENCES resolved_place_candidates(id) ON DELETE SET NULL,
  merge_target_mention_id TEXT REFERENCES extracted_mentions(id) ON DELETE SET NULL,
  note_text TEXT,
  reason_code TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(import_job_id, review_version)
);

CREATE TABLE IF NOT EXISTS import_idempotency_records (
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  scope TEXT NOT NULL,
  idempotency_key_hash TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  result_ref TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(trip_id, scope, idempotency_key_hash)
);

CREATE TABLE IF NOT EXISTS import_commit_records (
  id TEXT PRIMARY KEY,
  import_job_id TEXT NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
  review_version INTEGER NOT NULL,
  result_json TEXT NOT NULL,
  commit_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(import_job_id)
);

CREATE INDEX IF NOT EXISTS idx_import_jobs_trip_created
  ON import_jobs(trip_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_extracted_mentions_job_span
  ON extracted_mentions(import_job_id, start_offset, end_offset, id);

CREATE TRIGGER IF NOT EXISTS source_artifacts_immutable_core
BEFORE UPDATE ON source_artifacts
BEGIN
  SELECT RAISE(ABORT, 'immutable_source_artifact_violation');
END;

CREATE TRIGGER IF NOT EXISTS extracted_mentions_immutable_core
BEFORE UPDATE ON extracted_mentions
BEGIN
  SELECT RAISE(ABORT, 'immutable_extracted_mention_violation');
END;

CREATE TRIGGER IF NOT EXISTS resolved_place_candidates_immutable_core
BEFORE UPDATE ON resolved_place_candidates
BEGIN
  SELECT RAISE(ABORT, 'immutable_resolved_place_candidate_violation');
END;

CREATE TRIGGER IF NOT EXISTS import_review_decisions_immutable_core
BEFORE UPDATE ON import_review_decisions
BEGIN
  SELECT RAISE(ABORT, 'immutable_import_review_decision_violation');
END;

CREATE TRIGGER IF NOT EXISTS import_commit_records_immutable_core
BEFORE UPDATE ON import_commit_records
BEGIN
  SELECT RAISE(ABORT, 'immutable_import_commit_violation');
END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0005_text_import_review_foundation');
