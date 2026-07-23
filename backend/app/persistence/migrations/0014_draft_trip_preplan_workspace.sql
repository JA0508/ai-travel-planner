ALTER TABLE trips ADD COLUMN planning_phase TEXT NOT NULL DEFAULT 'planned'
  CHECK (planning_phase IN ('draft', 'planned'));

CREATE TABLE IF NOT EXISTS draft_trip_idempotency_records (
  idempotency_key_hash TEXT PRIMARY KEY,
  request_digest TEXT NOT NULL,
  result_trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS draft_intent_revisions (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  revision_number INTEGER NOT NULL,
  parent_draft_intent_revision_id TEXT REFERENCES draft_intent_revisions(id),
  envelope_schema_version TEXT NOT NULL,
  envelope_json TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  compiler_version TEXT NOT NULL,
  source_digest TEXT NOT NULL,
  validation_report_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(trip_id, revision_number)
);

CREATE TABLE IF NOT EXISTS draft_intent_idempotency_records (
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  idempotency_key_hash TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  result_draft_intent_revision_id TEXT NOT NULL REFERENCES draft_intent_revisions(id),
  created_at TEXT NOT NULL,
  PRIMARY KEY(trip_id, idempotency_key_hash)
);

CREATE TABLE IF NOT EXISTS preplan_handoff_runs (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE RESTRICT,
  draft_intent_revision_id TEXT NOT NULL REFERENCES draft_intent_revisions(id) ON DELETE RESTRICT,
  intent_semantic_digest TEXT NOT NULL,
  intent_lineage_digest TEXT NOT NULL,
  input_snapshot_json TEXT NOT NULL,
  input_digest TEXT NOT NULL,
  planner_version TEXT NOT NULL,
  trace_schema_version TEXT NOT NULL,
  trace_snapshot_json TEXT NOT NULL,
  trace_digest TEXT NOT NULL,
  result_snapshot_json TEXT NOT NULL,
  result_content_digest TEXT NOT NULL,
  validation_report_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'applied', 'invalidated', 'expired')),
  expires_at TEXT NOT NULL,
  applied_revision_id TEXT UNIQUE REFERENCES trip_revisions(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK ((status = 'applied' AND applied_revision_id IS NOT NULL) OR (status <> 'applied' AND applied_revision_id IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_draft_intent_revisions_trip_created
  ON draft_intent_revisions(trip_id, revision_number DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_preplan_handoff_runs_trip_created
  ON preplan_handoff_runs(trip_id, created_at DESC);

CREATE TRIGGER IF NOT EXISTS draft_intent_revisions_are_immutable
BEFORE UPDATE ON draft_intent_revisions
BEGIN
  SELECT RAISE(ABORT, 'immutable_draft_intent_revision_violation');
END;

CREATE TRIGGER IF NOT EXISTS draft_intent_revisions_are_append_only
BEFORE DELETE ON draft_intent_revisions
BEGIN
  SELECT RAISE(ABORT, 'immutable_draft_intent_revision_violation');
END;

CREATE TRIGGER IF NOT EXISTS preplan_handoff_runs_immutable_fields
BEFORE UPDATE ON preplan_handoff_runs
WHEN OLD.trip_id <> NEW.trip_id
  OR OLD.draft_intent_revision_id <> NEW.draft_intent_revision_id
  OR OLD.intent_semantic_digest <> NEW.intent_semantic_digest
  OR OLD.intent_lineage_digest <> NEW.intent_lineage_digest
  OR OLD.input_snapshot_json <> NEW.input_snapshot_json
  OR OLD.input_digest <> NEW.input_digest
  OR OLD.planner_version <> NEW.planner_version
  OR OLD.trace_schema_version <> NEW.trace_schema_version
  OR OLD.trace_snapshot_json <> NEW.trace_snapshot_json
  OR OLD.trace_digest <> NEW.trace_digest
  OR OLD.result_snapshot_json <> NEW.result_snapshot_json
  OR OLD.result_content_digest <> NEW.result_content_digest
  OR OLD.validation_report_json <> NEW.validation_report_json
  OR OLD.expires_at <> NEW.expires_at
  OR OLD.created_at <> NEW.created_at
BEGIN
  SELECT RAISE(ABORT, 'immutable_preplan_handoff_run_violation');
END;

CREATE TRIGGER IF NOT EXISTS preplan_handoff_runs_status_transition
BEFORE UPDATE OF status ON preplan_handoff_runs
WHEN NOT (OLD.status = NEW.status OR (OLD.status = 'pending' AND NEW.status IN ('applied', 'invalidated', 'expired')))
BEGIN
  SELECT RAISE(ABORT, 'invalid_preplan_handoff_run_status_transition');
END;

CREATE TRIGGER IF NOT EXISTS preplan_handoff_runs_append_only
BEFORE DELETE ON preplan_handoff_runs
BEGIN
  SELECT RAISE(ABORT, 'preplan_handoff_runs_are_append_only');
END;

INSERT INTO schema_migrations(version, applied_at)
VALUES ('0014_draft_trip_preplan_workspace', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
