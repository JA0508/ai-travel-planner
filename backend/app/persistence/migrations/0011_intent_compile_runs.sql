CREATE TABLE IF NOT EXISTS intent_compile_runs (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id),
  operation TEXT NOT NULL,
  base_trip_revision_id TEXT NOT NULL REFERENCES trip_revisions(id),
  base_intent_revision_id TEXT REFERENCES trip_intent_revisions(id),
  result_intent_revision_id TEXT NOT NULL REFERENCES trip_intent_revisions(id),
  parser_status TEXT NOT NULL,
  parser_name TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  model_name TEXT,
  compiler_version TEXT NOT NULL,
  precedence_version TEXT NOT NULL,
  readiness_policy_version TEXT NOT NULL,
  date_policy_version TEXT NOT NULL,
  input_digest TEXT NOT NULL,
  proposal_digest TEXT,
  semantic_digest TEXT NOT NULL,
  lineage_digest TEXT NOT NULL,
  status TEXT NOT NULL,
  warning_codes_json TEXT NOT NULL,
  error_code TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_intent_compile_runs_trip_revision
  ON intent_compile_runs(trip_id, result_intent_revision_id, created_at DESC);

CREATE TRIGGER IF NOT EXISTS intent_compile_runs_are_immutable
BEFORE UPDATE ON intent_compile_runs
BEGIN
  SELECT RAISE(ABORT, 'intent_compile_runs are immutable');
END;

CREATE TRIGGER IF NOT EXISTS intent_compile_runs_are_append_only
BEFORE DELETE ON intent_compile_runs
BEGIN
  SELECT RAISE(ABORT, 'intent_compile_runs are append-only');
END;

INSERT INTO schema_migrations(version, applied_at)
VALUES ('0011_intent_compile_runs', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
