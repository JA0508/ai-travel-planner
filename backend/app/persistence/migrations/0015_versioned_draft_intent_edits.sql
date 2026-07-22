ALTER TABLE trips ADD COLUMN draft_version INTEGER NOT NULL DEFAULT 0 CHECK (draft_version >= 0);

ALTER TABLE draft_intent_idempotency_records ADD COLUMN changed INTEGER NOT NULL DEFAULT 1 CHECK (changed IN (0, 1));
ALTER TABLE draft_intent_idempotency_records ADD COLUMN result_draft_version INTEGER NOT NULL DEFAULT 0 CHECK (result_draft_version >= 0);

INSERT INTO schema_migrations(version, applied_at)
VALUES ('0015_versioned_draft_intent_edits', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
