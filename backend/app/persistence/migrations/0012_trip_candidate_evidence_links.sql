CREATE TABLE IF NOT EXISTS trip_candidate_evidence_links (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  trip_candidate_id TEXT NOT NULL REFERENCES trip_candidates(id) ON DELETE CASCADE,
  source_artifact_id TEXT NOT NULL REFERENCES source_artifacts(id) ON DELETE RESTRICT,
  import_job_id TEXT NOT NULL REFERENCES import_jobs(id) ON DELETE RESTRICT,
  mention_id TEXT NOT NULL REFERENCES extracted_mentions(id) ON DELETE RESTRICT,
  review_decision_id TEXT NOT NULL REFERENCES import_review_decisions(id) ON DELETE RESTRICT,
  resolution_candidate_id TEXT NOT NULL REFERENCES resolved_place_candidates(id) ON DELETE RESTRICT,
  document_generation_id TEXT REFERENCES document_extraction_generations(id) ON DELETE RESTRICT,
  document_page_number INTEGER,
  document_span_id TEXT REFERENCES document_text_spans(id) ON DELETE RESTRICT,
  bounding_boxes_json TEXT NOT NULL,
  source_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(trip_candidate_id, mention_id, review_decision_id)
);

CREATE INDEX IF NOT EXISTS idx_candidate_evidence_links_candidate
  ON trip_candidate_evidence_links(trip_id, trip_candidate_id, created_at, id);

CREATE TRIGGER IF NOT EXISTS trip_candidate_evidence_links_are_append_only
BEFORE UPDATE ON trip_candidate_evidence_links
BEGIN
  SELECT RAISE(ABORT, 'immutable_candidate_evidence_link_violation');
END;

CREATE TRIGGER IF NOT EXISTS trip_candidate_evidence_links_cannot_be_deleted
BEFORE DELETE ON trip_candidate_evidence_links
BEGIN
  SELECT RAISE(ABORT, 'immutable_candidate_evidence_link_violation');
END;

CREATE TRIGGER IF NOT EXISTS trip_candidate_evidence_links_validate_lineage
BEFORE INSERT ON trip_candidate_evidence_links
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM trip_candidates WHERE id = NEW.trip_candidate_id AND trip_id = NEW.trip_id
  ) THEN RAISE(ABORT, 'candidate_evidence_candidate_trip_mismatch') END;
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM import_jobs WHERE id = NEW.import_job_id AND trip_id = NEW.trip_id AND artifact_id = NEW.source_artifact_id
  ) THEN RAISE(ABORT, 'candidate_evidence_import_job_lineage_invalid') END;
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM extracted_mentions WHERE id = NEW.mention_id AND import_job_id = NEW.import_job_id AND artifact_id = NEW.source_artifact_id
  ) THEN RAISE(ABORT, 'candidate_evidence_mention_lineage_invalid') END;
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM import_review_decisions
    WHERE id = NEW.review_decision_id AND import_job_id = NEW.import_job_id
      AND mention_id = NEW.mention_id AND selected_resolution_candidate_id = NEW.resolution_candidate_id
      AND action IN ('confirm', 'select_candidate')
  ) THEN RAISE(ABORT, 'candidate_evidence_review_lineage_invalid') END;
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM resolved_place_candidates WHERE id = NEW.resolution_candidate_id AND mention_id = NEW.mention_id
  ) THEN RAISE(ABORT, 'candidate_evidence_resolution_lineage_invalid') END;
  SELECT CASE WHEN NEW.document_generation_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM document_extraction_generations
    WHERE id = NEW.document_generation_id
      AND (source_artifact_id = NEW.source_artifact_id OR derived_artifact_id = NEW.source_artifact_id)
  ) THEN RAISE(ABORT, 'candidate_evidence_document_generation_invalid') END;
  SELECT CASE WHEN NEW.document_span_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM document_text_spans
    WHERE id = NEW.document_span_id AND generation_id = NEW.document_generation_id
      AND (NEW.document_page_number IS NULL OR page_number = NEW.document_page_number)
  ) THEN RAISE(ABORT, 'candidate_evidence_document_span_invalid') END;
END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0012_trip_candidate_evidence_links');
