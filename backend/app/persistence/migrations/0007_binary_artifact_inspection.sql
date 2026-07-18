CREATE TABLE IF NOT EXISTS artifact_inspections (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  import_job_id TEXT NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
  artifact_id TEXT NOT NULL REFERENCES source_artifacts(id) ON DELETE CASCADE,
  attempt INTEGER NOT NULL,
  schema_version TEXT NOT NULL,
  inspector_version TEXT NOT NULL,
  declared_kind TEXT NOT NULL,
  detected_kind TEXT NOT NULL,
  declared_mime_type TEXT,
  detected_mime_type TEXT NOT NULL,
  status TEXT NOT NULL,
  classification TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  content_checksum TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  sanitized_artifact_id TEXT REFERENCES source_artifacts(id) ON DELETE RESTRICT,
  manifest_artifact_id TEXT REFERENCES source_artifacts(id) ON DELETE RESTRICT,
  warning_codes_json TEXT NOT NULL,
  error_code TEXT,
  started_at TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  UNIQUE(artifact_id, inspector_version, attempt),
  CHECK(status IN ('quarantined', 'inspecting', 'artifact_ready', 'needs_password', 'rejected', 'unsupported', 'inspection_failed')),
  CHECK(classification IN ('artifact_ready', 'needs_password', 'rejected', 'unsupported', 'inspection_failed')),
  CHECK(declared_kind IN ('image', 'pdf')),
  CHECK(detected_kind IN ('image', 'pdf')),
  CHECK((declared_kind = 'image' AND detected_kind = 'image') OR (declared_kind = 'pdf' AND detected_kind = 'pdf')),
  CHECK((status = 'artifact_ready' AND declared_kind = 'image' AND sanitized_artifact_id IS NOT NULL AND manifest_artifact_id IS NULL)
        OR (status = 'artifact_ready' AND declared_kind = 'pdf' AND manifest_artifact_id IS NOT NULL AND sanitized_artifact_id IS NULL)
        OR status <> 'artifact_ready')
);

CREATE TABLE IF NOT EXISTS artifact_inspection_findings (
  id TEXT PRIMARY KEY,
  inspection_id TEXT NOT NULL REFERENCES artifact_inspections(id) ON DELETE CASCADE,
  code TEXT NOT NULL,
  severity TEXT NOT NULL CHECK(severity IN ('info', 'warning', 'block')),
  category TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifact_inspections_job
  ON artifact_inspections(import_job_id, completed_at, id);

CREATE INDEX IF NOT EXISTS idx_artifact_inspections_artifact_version
  ON artifact_inspections(artifact_id, inspector_version, attempt);

CREATE INDEX IF NOT EXISTS idx_artifact_inspection_findings_inspection
  ON artifact_inspection_findings(inspection_id, created_at, id);

CREATE TRIGGER IF NOT EXISTS artifact_inspections_immutable_core
BEFORE UPDATE ON artifact_inspections
BEGIN
  SELECT RAISE(ABORT, 'immutable_artifact_inspection_violation');
END;

CREATE TRIGGER IF NOT EXISTS artifact_inspection_findings_immutable_core
BEFORE UPDATE ON artifact_inspection_findings
BEGIN
  SELECT RAISE(ABORT, 'immutable_artifact_inspection_finding_violation');
END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0007_binary_artifact_inspection');
