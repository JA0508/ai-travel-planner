CREATE TABLE IF NOT EXISTS trip_mutation_proposals (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE RESTRICT,
  base_revision_id TEXT NOT NULL REFERENCES trip_revisions(id) ON DELETE RESTRICT,
  proposal_schema_version TEXT NOT NULL,
  source_type TEXT NOT NULL,
  operation_type TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  instruction_digest TEXT,
  preview_snapshot_schema_version TEXT NOT NULL,
  preview_snapshot_json TEXT NOT NULL,
  preview_content_digest TEXT NOT NULL,
  proposal_digest TEXT NOT NULL,
  planner_run_id TEXT,
  planner_version TEXT,
  trace_schema_version TEXT,
  trace_digest TEXT,
  validation_report_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'applied', 'cancelled', 'expired', 'invalidated')),
  expires_at TEXT NOT NULL,
  applied_revision_id TEXT REFERENCES trip_revisions(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (
    (status = 'applied' AND applied_revision_id IS NOT NULL)
    OR (status <> 'applied' AND applied_revision_id IS NULL)
  ),
  UNIQUE (applied_revision_id)
);

CREATE INDEX IF NOT EXISTS idx_trip_mutation_proposals_trip
  ON trip_mutation_proposals(trip_id);

CREATE INDEX IF NOT EXISTS idx_trip_mutation_proposals_base
  ON trip_mutation_proposals(base_revision_id);

CREATE INDEX IF NOT EXISTS idx_trip_mutation_proposals_status
  ON trip_mutation_proposals(status);

CREATE INDEX IF NOT EXISTS idx_trip_mutation_proposals_expires
  ON trip_mutation_proposals(expires_at);

CREATE TRIGGER IF NOT EXISTS trip_mutation_proposals_base_same_trip_insert
BEFORE INSERT ON trip_mutation_proposals
WHEN NOT EXISTS (
  SELECT 1 FROM trip_revisions
  WHERE id = NEW.base_revision_id
    AND trip_id = NEW.trip_id
)
BEGIN
  SELECT RAISE(ABORT, 'proposal_revision_not_in_trip');
END;

CREATE TRIGGER IF NOT EXISTS trip_mutation_proposals_applied_same_trip_insert
BEFORE INSERT ON trip_mutation_proposals
WHEN NEW.applied_revision_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM trip_revisions
    WHERE id = NEW.applied_revision_id
      AND trip_id = NEW.trip_id
  )
BEGIN
  SELECT RAISE(ABORT, 'proposal_revision_not_in_trip');
END;

CREATE TRIGGER IF NOT EXISTS trip_mutation_proposals_applied_same_trip_update
BEFORE UPDATE OF applied_revision_id ON trip_mutation_proposals
WHEN NEW.applied_revision_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM trip_revisions
    WHERE id = NEW.applied_revision_id
      AND trip_id = NEW.trip_id
  )
BEGIN
  SELECT RAISE(ABORT, 'proposal_revision_not_in_trip');
END;

CREATE TRIGGER IF NOT EXISTS trip_mutation_proposals_immutable_fields
BEFORE UPDATE ON trip_mutation_proposals
WHEN OLD.trip_id <> NEW.trip_id
  OR OLD.base_revision_id <> NEW.base_revision_id
  OR OLD.proposal_schema_version <> NEW.proposal_schema_version
  OR OLD.source_type <> NEW.source_type
  OR OLD.operation_type <> NEW.operation_type
  OR OLD.request_digest <> NEW.request_digest
  OR COALESCE(OLD.instruction_digest, '') <> COALESCE(NEW.instruction_digest, '')
  OR OLD.preview_snapshot_schema_version <> NEW.preview_snapshot_schema_version
  OR OLD.preview_snapshot_json <> NEW.preview_snapshot_json
  OR OLD.preview_content_digest <> NEW.preview_content_digest
  OR OLD.proposal_digest <> NEW.proposal_digest
  OR COALESCE(OLD.planner_run_id, '') <> COALESCE(NEW.planner_run_id, '')
  OR COALESCE(OLD.planner_version, '') <> COALESCE(NEW.planner_version, '')
  OR COALESCE(OLD.trace_schema_version, '') <> COALESCE(NEW.trace_schema_version, '')
  OR COALESCE(OLD.trace_digest, '') <> COALESCE(NEW.trace_digest, '')
  OR OLD.validation_report_json <> NEW.validation_report_json
  OR OLD.expires_at <> NEW.expires_at
  OR OLD.created_at <> NEW.created_at
BEGIN
  SELECT RAISE(ABORT, 'immutable_proposal_violation');
END;

CREATE TRIGGER IF NOT EXISTS trip_mutation_proposals_status_transition
BEFORE UPDATE OF status ON trip_mutation_proposals
WHEN NOT (
  OLD.status = NEW.status
  OR (OLD.status = 'pending' AND NEW.status IN ('applied', 'cancelled', 'expired', 'invalidated'))
)
BEGIN
  SELECT RAISE(ABORT, 'invalid_proposal_status_transition');
END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0002_trip_mutation_proposals');
