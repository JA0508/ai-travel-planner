CREATE TABLE IF NOT EXISTS document_extraction_pages (
  id TEXT PRIMARY KEY,
  generation_id TEXT NOT NULL REFERENCES document_extraction_generations(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  extraction_method TEXT NOT NULL,
  status TEXT NOT NULL,
  native_text_quality REAL,
  text_chars INTEGER NOT NULL,
  span_count INTEGER NOT NULL,
  rendered_artifact_id TEXT REFERENCES source_artifacts(id) ON DELETE SET NULL,
  preview_artifact_id TEXT REFERENCES source_artifacts(id) ON DELETE SET NULL,
  retryable INTEGER NOT NULL,
  error_code TEXT,
  warning_codes_json TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(generation_id, page_number),
  CHECK(page_number >= 1),
  CHECK(status IN ('extracted', 'partial', 'failed', 'skipped')),
  CHECK(extraction_method IN ('native_pdf_text', 'pdf_page_ocr', 'image_ocr', 'none')),
  CHECK(native_text_quality IS NULL OR (native_text_quality >= 0 AND native_text_quality <= 1)),
  CHECK(text_chars >= 0),
  CHECK(span_count >= 0),
  CHECK(retryable IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_document_extraction_pages_generation
  ON document_extraction_pages(generation_id, page_number);

CREATE TRIGGER IF NOT EXISTS document_extraction_pages_immutable_core
BEFORE UPDATE ON document_extraction_pages
BEGIN
  SELECT RAISE(ABORT, 'immutable_document_extraction_page_violation');
END;

INSERT OR IGNORE INTO schema_migrations(version) VALUES ('0009_document_extraction_pages');
