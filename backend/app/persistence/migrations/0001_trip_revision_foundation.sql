CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS trips (
  id TEXT PRIMARY KEY,
  current_revision_id TEXT,
  revision_count INTEGER NOT NULL DEFAULT 0 CHECK (revision_count >= 0),
  lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN ('active', 'archived')),
  capability_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trip_revisions (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE RESTRICT,
  revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
  parent_revision_id TEXT REFERENCES trip_revisions(id) ON DELETE RESTRICT,
  base_revision_id TEXT REFERENCES trip_revisions(id) ON DELETE RESTRICT,
  source_type TEXT NOT NULL,
  snapshot_schema_version TEXT NOT NULL,
  itinerary_snapshot TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  parent_lineage_digest TEXT,
  lineage_digest TEXT NOT NULL,
  planner_run_id TEXT,
  planner_version TEXT,
  trace_schema_version TEXT,
  trace_digest TEXT,
  restored_from_revision_id TEXT REFERENCES trip_revisions(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL,
  UNIQUE (trip_id, revision_number)
);

CREATE TABLE IF NOT EXISTS revision_operations (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE RESTRICT,
  revision_id TEXT NOT NULL REFERENCES trip_revisions(id) ON DELETE RESTRICT,
  base_revision_id TEXT REFERENCES trip_revisions(id) ON DELETE RESTRICT,
  source_type TEXT NOT NULL,
  operation_type TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  idempotency_key_hash TEXT,
  actor_type TEXT NOT NULL,
  summary TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (revision_id)
);

CREATE TABLE IF NOT EXISTS idempotency_records (
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE RESTRICT,
  idempotency_key_hash TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  result_revision_id TEXT NOT NULL REFERENCES trip_revisions(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (trip_id, idempotency_key_hash)
);

CREATE INDEX IF NOT EXISTS idx_trip_revisions_trip_created
  ON trip_revisions(trip_id, revision_number DESC);

CREATE TRIGGER IF NOT EXISTS trip_revisions_no_update
BEFORE UPDATE ON trip_revisions
BEGIN
  SELECT RAISE(ABORT, 'immutable_revision_violation');
END;

CREATE TRIGGER IF NOT EXISTS trip_revisions_no_delete
BEFORE DELETE ON trip_revisions
BEGIN
  SELECT RAISE(ABORT, 'immutable_revision_violation');
END;

CREATE TRIGGER IF NOT EXISTS revision_operations_no_update
BEFORE UPDATE ON revision_operations
BEGIN
  SELECT RAISE(ABORT, 'immutable_revision_violation');
END;

CREATE TRIGGER IF NOT EXISTS revision_operations_no_delete
BEFORE DELETE ON revision_operations
BEGIN
  SELECT RAISE(ABORT, 'immutable_revision_violation');
END;

CREATE TRIGGER IF NOT EXISTS trips_current_revision_same_trip
BEFORE UPDATE OF current_revision_id ON trips
WHEN NEW.current_revision_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM trip_revisions
    WHERE id = NEW.current_revision_id
      AND trip_id = NEW.id
  )
BEGIN
  SELECT RAISE(ABORT, 'revision_not_in_trip');
END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0001_trip_revision_foundation');
