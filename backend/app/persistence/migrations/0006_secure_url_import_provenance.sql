CREATE TABLE IF NOT EXISTS url_fetch_snapshots (
  id TEXT PRIMARY KEY,
  import_job_id TEXT NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
  raw_artifact_id TEXT NOT NULL REFERENCES source_artifacts(id) ON DELETE CASCADE,
  request_url_sanitized TEXT NOT NULL,
  normalized_request_url TEXT NOT NULL,
  final_url_sanitized TEXT NOT NULL,
  final_url TEXT NOT NULL,
  redirect_chain_json TEXT NOT NULL,
  robots_status TEXT NOT NULL,
  robots_checked_at TEXT NOT NULL,
  status_code INTEGER NOT NULL,
  content_type TEXT NOT NULL,
  declared_charset TEXT,
  effective_charset TEXT,
  content_language TEXT,
  compressed_bytes INTEGER NOT NULL,
  decoded_bytes INTEGER NOT NULL,
  body_checksum TEXT NOT NULL,
  header_metadata_json TEXT NOT NULL,
  fetcher_version TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  warning_codes_json TEXT NOT NULL,
  cache_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_derivations (
  id TEXT PRIMARY KEY,
  parent_artifact_id TEXT NOT NULL REFERENCES source_artifacts(id) ON DELETE CASCADE,
  child_artifact_id TEXT NOT NULL REFERENCES source_artifacts(id) ON DELETE CASCADE,
  derivation_type TEXT NOT NULL,
  transformer_version TEXT NOT NULL,
  input_checksum TEXT NOT NULL,
  output_checksum TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(child_artifact_id)
);

CREATE INDEX IF NOT EXISTS idx_url_fetch_snapshots_job
  ON url_fetch_snapshots(import_job_id, fetched_at, id);

CREATE INDEX IF NOT EXISTS idx_url_fetch_snapshots_normalized_url
  ON url_fetch_snapshots(normalized_request_url, fetched_at, id);

CREATE TRIGGER IF NOT EXISTS url_fetch_snapshots_immutable_core
BEFORE UPDATE ON url_fetch_snapshots
BEGIN
  SELECT RAISE(ABORT, 'immutable_url_fetch_snapshot_violation');
END;

CREATE TRIGGER IF NOT EXISTS artifact_derivations_immutable_core
BEFORE UPDATE ON artifact_derivations
BEGIN
  SELECT RAISE(ABORT, 'immutable_artifact_derivation_violation');
END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0006_secure_url_import_provenance');
