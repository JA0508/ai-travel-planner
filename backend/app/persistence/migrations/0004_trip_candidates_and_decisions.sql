CREATE TABLE IF NOT EXISTS trip_candidates (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  candidate_type TEXT NOT NULL,
  display_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  canonical_place_id TEXT,
  provider_place_id TEXT,
  category TEXT,
  coordinates_json TEXT,
  address_summary TEXT,
  estimated_duration_minutes INTEGER,
  preferred_time_block TEXT,
  explicit_day_reference TEXT,
  source_kind TEXT NOT NULL,
  source_ref TEXT,
  evidence_refs_json TEXT NOT NULL,
  location_state TEXT NOT NULL,
  route_state TEXT NOT NULL,
  duration_state TEXT NOT NULL,
  confidence TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(trip_id, content_digest)
);

CREATE TABLE IF NOT EXISTS trip_candidate_decisions (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  candidate_id TEXT NOT NULL REFERENCES trip_candidates(id) ON DELETE CASCADE,
  decision_type TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  base_revision_id TEXT,
  related_revision_id TEXT,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_idempotency_records (
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  idempotency_key_hash TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  result_candidate_id TEXT REFERENCES trip_candidates(id) ON DELETE CASCADE,
  result_decision_id TEXT REFERENCES trip_candidate_decisions(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  PRIMARY KEY(trip_id, idempotency_key_hash)
);

CREATE INDEX IF NOT EXISTS idx_trip_candidates_trip_created
  ON trip_candidates(trip_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_trip_candidate_decisions_candidate_created
  ON trip_candidate_decisions(trip_id, candidate_id, created_at, id);

CREATE TRIGGER IF NOT EXISTS trip_candidates_immutable_core
BEFORE UPDATE ON trip_candidates
WHEN OLD.trip_id <> NEW.trip_id
  OR OLD.candidate_type <> NEW.candidate_type
  OR OLD.display_name <> NEW.display_name
  OR OLD.normalized_name <> NEW.normalized_name
  OR COALESCE(OLD.canonical_place_id, '') <> COALESCE(NEW.canonical_place_id, '')
  OR COALESCE(OLD.provider_place_id, '') <> COALESCE(NEW.provider_place_id, '')
  OR COALESCE(OLD.coordinates_json, '') <> COALESCE(NEW.coordinates_json, '')
  OR OLD.source_kind <> NEW.source_kind
  OR COALESCE(OLD.source_ref, '') <> COALESCE(NEW.source_ref, '')
  OR OLD.evidence_refs_json <> NEW.evidence_refs_json
  OR OLD.content_digest <> NEW.content_digest
  OR OLD.created_at <> NEW.created_at
BEGIN
  SELECT RAISE(ABORT, 'immutable_candidate_violation');
END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0004_trip_candidates_and_decisions');
