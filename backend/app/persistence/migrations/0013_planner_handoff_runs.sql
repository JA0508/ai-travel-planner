CREATE TABLE IF NOT EXISTS planner_handoff_runs (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE RESTRICT,
  base_trip_revision_id TEXT NOT NULL REFERENCES trip_revisions(id) ON DELETE RESTRICT,
  intent_revision_id TEXT NOT NULL REFERENCES trip_intent_revisions(id) ON DELETE RESTRICT,
  intent_semantic_digest TEXT NOT NULL,
  intent_lineage_digest TEXT NOT NULL,
  input_schema_version TEXT NOT NULL,
  input_snapshot_json TEXT NOT NULL,
  input_digest TEXT NOT NULL,
  planner_version TEXT NOT NULL,
  trace_schema_version TEXT NOT NULL,
  trace_snapshot_json TEXT NOT NULL,
  trace_digest TEXT NOT NULL,
  result_snapshot_schema_version TEXT NOT NULL,
  result_snapshot_json TEXT NOT NULL,
  result_content_digest TEXT NOT NULL,
  validation_report_json TEXT NOT NULL,
  proposal_id TEXT UNIQUE REFERENCES trip_mutation_proposals(id) ON DELETE RESTRICT,
  status TEXT NOT NULL CHECK (status IN ('pending', 'applied', 'invalidated')),
  applied_revision_id TEXT UNIQUE REFERENCES trip_revisions(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK ((status = 'applied' AND applied_revision_id IS NOT NULL) OR (status <> 'applied' AND applied_revision_id IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_planner_handoff_runs_trip_created
  ON planner_handoff_runs(trip_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_planner_handoff_runs_intent
  ON planner_handoff_runs(trip_id, intent_revision_id);

CREATE TRIGGER IF NOT EXISTS planner_handoff_runs_immutable_fields
BEFORE UPDATE ON planner_handoff_runs
WHEN OLD.trip_id <> NEW.trip_id
  OR OLD.base_trip_revision_id <> NEW.base_trip_revision_id
  OR OLD.intent_revision_id <> NEW.intent_revision_id
  OR OLD.intent_semantic_digest <> NEW.intent_semantic_digest
  OR OLD.intent_lineage_digest <> NEW.intent_lineage_digest
  OR OLD.input_schema_version <> NEW.input_schema_version
  OR OLD.input_snapshot_json <> NEW.input_snapshot_json
  OR OLD.input_digest <> NEW.input_digest
  OR OLD.planner_version <> NEW.planner_version
  OR OLD.trace_schema_version <> NEW.trace_schema_version
  OR OLD.trace_snapshot_json <> NEW.trace_snapshot_json
  OR OLD.trace_digest <> NEW.trace_digest
  OR OLD.result_snapshot_schema_version <> NEW.result_snapshot_schema_version
  OR OLD.result_snapshot_json <> NEW.result_snapshot_json
  OR OLD.result_content_digest <> NEW.result_content_digest
  OR OLD.validation_report_json <> NEW.validation_report_json
  OR COALESCE(OLD.proposal_id, '') <> COALESCE(NEW.proposal_id, '')
  OR OLD.created_at <> NEW.created_at
BEGIN
  SELECT RAISE(ABORT, 'immutable_planner_handoff_run_violation');
END;

CREATE TRIGGER IF NOT EXISTS planner_handoff_runs_status_transition
BEFORE UPDATE OF status ON planner_handoff_runs
WHEN NOT (OLD.status = NEW.status OR (OLD.status = 'pending' AND NEW.status IN ('applied', 'invalidated')))
BEGIN
  SELECT RAISE(ABORT, 'invalid_planner_handoff_run_status_transition');
END;

CREATE TRIGGER IF NOT EXISTS planner_handoff_runs_append_only
BEFORE DELETE ON planner_handoff_runs
BEGIN
  SELECT RAISE(ABORT, 'planner_handoff_runs_are_append_only');
END;

INSERT INTO schema_migrations(version, applied_at)
VALUES ('0013_planner_handoff_runs', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
