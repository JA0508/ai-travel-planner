CREATE TABLE IF NOT EXISTS trip_intent_revisions (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  revision_number INTEGER NOT NULL,
  parent_intent_revision_id TEXT REFERENCES trip_intent_revisions(id),
  base_trip_revision_id TEXT NOT NULL REFERENCES trip_revisions(id),
  envelope_schema_version TEXT NOT NULL,
  envelope_json TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  compiler_version TEXT NOT NULL,
  source_digest TEXT NOT NULL,
  validation_report_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(trip_id, revision_number)
);

CREATE INDEX IF NOT EXISTS idx_trip_intent_revisions_trip_revision
  ON trip_intent_revisions(trip_id, revision_number DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS trip_intent_idempotency_records (
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  idempotency_key_hash TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  result_intent_revision_id TEXT NOT NULL REFERENCES trip_intent_revisions(id),
  created_at TEXT NOT NULL,
  PRIMARY KEY(trip_id, idempotency_key_hash)
);

CREATE TRIGGER IF NOT EXISTS trip_intent_revisions_are_immutable
BEFORE UPDATE ON trip_intent_revisions
BEGIN
  SELECT RAISE(ABORT, 'immutable_intent_revision_violation');
END;

CREATE TRIGGER IF NOT EXISTS trip_intent_revisions_are_append_only
BEFORE DELETE ON trip_intent_revisions
BEGIN
  SELECT RAISE(ABORT, 'immutable_intent_revision_violation');
END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0010_trip_intent_envelope_revisions');
