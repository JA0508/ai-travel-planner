CREATE TABLE IF NOT EXISTS draft_trip_source_inputs (
  trip_id TEXT PRIMARY KEY REFERENCES trips(id) ON DELETE CASCADE,
  direct_user_text TEXT NOT NULL,
  source_digest TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS draft_trip_source_inputs_are_immutable
BEFORE UPDATE ON draft_trip_source_inputs
BEGIN
  SELECT RAISE(ABORT, 'immutable_draft_trip_source_input_violation');
END;

CREATE TRIGGER IF NOT EXISTS draft_trip_source_inputs_are_append_only
BEFORE DELETE ON draft_trip_source_inputs
BEGIN
  SELECT RAISE(ABORT, 'immutable_draft_trip_source_input_violation');
END;

INSERT INTO schema_migrations(version, applied_at)
VALUES ('0015_draft_trip_source_input', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
