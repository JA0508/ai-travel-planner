ALTER TABLE trip_mutation_proposals
  ADD COLUMN execution_kind TEXT;

ALTER TABLE trip_mutation_proposals
  ADD COLUMN command_schema_version TEXT;

ALTER TABLE trip_mutation_proposals
  ADD COLUMN mutation_engine_version TEXT;

ALTER TABLE trip_mutation_proposals
  ADD COLUMN mutation_kind TEXT;

ALTER TABLE trip_mutation_proposals
  ADD COLUMN commands_json TEXT;

ALTER TABLE trip_mutation_proposals
  ADD COLUMN command_digest TEXT;

ALTER TABLE trip_mutation_proposals
  ADD COLUMN impact_summary_json TEXT;

ALTER TABLE trip_mutation_proposals
  ADD COLUMN invalidated_surfaces_json TEXT;

ALTER TABLE revision_operations
  ADD COLUMN operation_metadata_json TEXT NOT NULL DEFAULT '{}';

DROP TRIGGER IF EXISTS trip_mutation_proposals_immutable_fields;

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
  OR COALESCE(OLD.execution_kind, '') <> COALESCE(NEW.execution_kind, '')
  OR COALESCE(OLD.command_schema_version, '') <> COALESCE(NEW.command_schema_version, '')
  OR COALESCE(OLD.mutation_engine_version, '') <> COALESCE(NEW.mutation_engine_version, '')
  OR COALESCE(OLD.mutation_kind, '') <> COALESCE(NEW.mutation_kind, '')
  OR COALESCE(OLD.commands_json, '') <> COALESCE(NEW.commands_json, '')
  OR COALESCE(OLD.command_digest, '') <> COALESCE(NEW.command_digest, '')
  OR COALESCE(OLD.impact_summary_json, '') <> COALESCE(NEW.impact_summary_json, '')
  OR COALESCE(OLD.invalidated_surfaces_json, '') <> COALESCE(NEW.invalidated_surfaces_json, '')
  OR OLD.expires_at <> NEW.expires_at
  OR OLD.created_at <> NEW.created_at
BEGIN
  SELECT RAISE(ABORT, 'immutable_proposal_violation');
END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0003_typed_mutation_commands');
