CREATE TABLE IF NOT EXISTS document_extraction_generations (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  source_import_job_id TEXT NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
  source_artifact_id TEXT NOT NULL REFERENCES source_artifacts(id) ON DELETE CASCADE,
  inspection_id TEXT NOT NULL REFERENCES artifact_inspections(id) ON DELETE RESTRICT,
  derived_import_job_id TEXT REFERENCES import_jobs(id) ON DELETE SET NULL,
  derived_artifact_id TEXT REFERENCES source_artifacts(id) ON DELETE SET NULL,
  generation INTEGER NOT NULL,
  schema_version TEXT NOT NULL,
  extractor_version TEXT NOT NULL,
  strategy TEXT NOT NULL,
  status TEXT NOT NULL,
  page_count INTEGER NOT NULL,
  extracted_text_chars INTEGER NOT NULL,
  warning_codes_json TEXT NOT NULL,
  error_code TEXT,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(source_import_job_id, extractor_version, generation),
  CHECK(status IN ('review_ready', 'partial', 'failed')),
  CHECK(strategy IN ('pdf_native_text', 'image_ocr', 'pdf_native_plus_selective_ocr'))
);

CREATE TABLE IF NOT EXISTS document_text_spans (
  id TEXT PRIMARY KEY,
  generation_id TEXT NOT NULL REFERENCES document_extraction_generations(id) ON DELETE CASCADE,
  span_start INTEGER NOT NULL,
  span_end INTEGER NOT NULL,
  page_number INTEGER NOT NULL,
  block_index INTEGER NOT NULL,
  line_index INTEGER NOT NULL,
  token_index INTEGER,
  bbox_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  confidence REAL,
  text_digest TEXT NOT NULL,
  warning_codes_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  CHECK(span_start >= 0),
  CHECK(span_end > span_start),
  CHECK(page_number >= 1),
  CHECK(block_index >= 0),
  CHECK(line_index >= 0),
  CHECK(token_index IS NULL OR token_index >= 0),
  CHECK(source_kind IN ('native_pdf_text', 'ocr_token', 'ocr_line'))
);

CREATE INDEX IF NOT EXISTS idx_document_extractions_source_job
  ON document_extraction_generations(source_import_job_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_document_extractions_derived_job
  ON document_extraction_generations(derived_import_job_id);

CREATE INDEX IF NOT EXISTS idx_document_text_spans_generation
  ON document_text_spans(generation_id, page_number, block_index, line_index, COALESCE(token_index, -1), span_start);

CREATE TRIGGER IF NOT EXISTS document_extraction_generations_immutable_core
BEFORE UPDATE ON document_extraction_generations
BEGIN
  SELECT RAISE(ABORT, 'immutable_document_extraction_generation_violation');
END;

CREATE TRIGGER IF NOT EXISTS document_text_spans_immutable_core
BEFORE UPDATE ON document_text_spans
BEGIN
  SELECT RAISE(ABORT, 'immutable_document_text_span_violation');
END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0008_document_extraction_generations');
