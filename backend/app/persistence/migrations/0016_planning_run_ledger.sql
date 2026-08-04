CREATE TABLE IF NOT EXISTS planning_runs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('generated', 'selecting', 'selected', 'expired', 'invalidated')),
  capability_hash TEXT NOT NULL,
  intent_digest TEXT NOT NULL,
  confirmed_intent_json TEXT NOT NULL,
  constraint_graph_json TEXT NOT NULL,
  planner_policy_version TEXT NOT NULL,
  snapshot_contract_version TEXT NOT NULL,
  candidate_set_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  selected_candidate_id TEXT,
  selected_at TEXT,
  trip_id TEXT UNIQUE REFERENCES trips(id) ON DELETE RESTRICT,
  revision_number INTEGER,
  selection_operation_id TEXT UNIQUE,
  selection_idempotency_key_hash TEXT,
  selection_request_digest TEXT,
  CHECK ((status = 'selected' AND selected_candidate_id IS NOT NULL AND trip_id IS NOT NULL)
     OR (status <> 'selected' AND selected_candidate_id IS NULL AND trip_id IS NULL))
);

CREATE TABLE IF NOT EXISTS planning_run_candidates (
  planning_run_id TEXT NOT NULL REFERENCES planning_runs(id) ON DELETE RESTRICT,
  candidate_id TEXT NOT NULL,
  candidate_hash TEXT NOT NULL,
  strategy TEXT NOT NULL CHECK (strategy IN ('relaxed', 'balanced', 'low_travel')),
  itinerary_snapshot_json TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  comparison_json TEXT NOT NULL,
  strategy_input_json TEXT NOT NULL,
  rank INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (planning_run_id, candidate_id),
  UNIQUE (planning_run_id, candidate_hash),
  UNIQUE (planning_run_id, rank)
);

CREATE TABLE IF NOT EXISTS planning_run_events (
  event_id TEXT PRIMARY KEY,
  planning_run_id TEXT NOT NULL REFERENCES planning_runs(id) ON DELETE RESTRICT,
  event_type TEXT NOT NULL CHECK (event_type IN ('planning_run_created', 'constraint_graph_built', 'candidates_generated', 'candidate_selection_started', 'candidate_selected', 'trip_revision_created', 'selection_replayed', 'selection_rejected', 'planning_run_expired', 'replay_verified', 'replay_mismatch')),
  occurred_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_planning_runs_capability ON planning_runs(capability_hash);
CREATE INDEX IF NOT EXISTS idx_planning_run_events_run_time ON planning_run_events(planning_run_id, occurred_at);

CREATE TRIGGER IF NOT EXISTS planning_runs_immutable_snapshot
BEFORE UPDATE ON planning_runs
WHEN OLD.capability_hash <> NEW.capability_hash
  OR OLD.intent_digest <> NEW.intent_digest
  OR OLD.confirmed_intent_json <> NEW.confirmed_intent_json
  OR OLD.constraint_graph_json <> NEW.constraint_graph_json
  OR OLD.planner_policy_version <> NEW.planner_policy_version
  OR OLD.snapshot_contract_version <> NEW.snapshot_contract_version
  OR OLD.candidate_set_hash <> NEW.candidate_set_hash
  OR OLD.created_at <> NEW.created_at
  OR OLD.expires_at <> NEW.expires_at
BEGIN SELECT RAISE(ABORT, 'immutable_planning_run_snapshot'); END;

CREATE TRIGGER IF NOT EXISTS planning_run_candidates_immutable
BEFORE UPDATE ON planning_run_candidates
BEGIN SELECT RAISE(ABORT, 'immutable_planning_run_candidate'); END;
CREATE TRIGGER IF NOT EXISTS planning_run_candidates_append_only
BEFORE DELETE ON planning_run_candidates
BEGIN SELECT RAISE(ABORT, 'planning_run_candidates_append_only'); END;
CREATE TRIGGER IF NOT EXISTS planning_run_events_append_only_update
BEFORE UPDATE ON planning_run_events
BEGIN SELECT RAISE(ABORT, 'planning_run_events_append_only'); END;
CREATE TRIGGER IF NOT EXISTS planning_run_events_append_only_delete
BEFORE DELETE ON planning_run_events
BEGIN SELECT RAISE(ABORT, 'planning_run_events_append_only'); END;

INSERT INTO schema_migrations(version, applied_at)
VALUES ('0016_planning_run_ledger', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
