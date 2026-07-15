from __future__ import annotations

import copy
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import replace
from typing import Any, Protocol

from app.imports.domain import (
    ExtractedMentionRecord,
    ImportCommitRecord,
    ImportJobRecord,
    ImportProcessingAttemptRecord,
    ImportReviewDecisionRecord,
    ResolvedPlaceCandidateRecord,
    SourceArtifactRecord,
    validate_import_transition,
)
from app.trips.errors import IdempotencyConflictError, TripError


class ImportRepository(Protocol):
    def get_artifact(self, *, trip_id: str, artifact_id: str) -> SourceArtifactRecord:
        ...

    def find_artifact_by_checksum(
        self,
        *,
        trip_id: str,
        artifact_type: str,
        checksum: str,
    ) -> SourceArtifactRecord | None:
        ...

    def create_artifact(self, artifact: SourceArtifactRecord) -> SourceArtifactRecord:
        ...

    def create_job(self, job: ImportJobRecord) -> ImportJobRecord:
        ...

    def get_job(self, *, trip_id: str, import_job_id: str) -> ImportJobRecord:
        ...

    def find_latest_job_for_artifact(
        self,
        *,
        trip_id: str,
        artifact_id: str,
    ) -> ImportJobRecord | None:
        ...

    def update_job(
        self,
        *,
        trip_id: str,
        import_job_id: str,
        status: str | None,
        updated_at: str,
        mention_count: int | None = None,
        warning_codes: list[str] | None = None,
        error_code: str | None = None,
        committed_at: str | None = None,
    ) -> ImportJobRecord:
        ...

    def create_attempt(self, attempt: ImportProcessingAttemptRecord) -> None:
        ...

    def complete_attempt(
        self,
        *,
        attempt_id: str,
        import_job_id: str,
        status: str,
        warning_codes: list[str],
        error_code: str | None,
        completed_at: str,
    ) -> None:
        ...

    def add_mentions_and_resolutions(
        self,
        *,
        mentions: list[ExtractedMentionRecord],
        resolutions: list[ResolvedPlaceCandidateRecord],
    ) -> None:
        ...

    def list_mentions(self, *, import_job_id: str) -> list[ExtractedMentionRecord]:
        ...

    def get_mention(self, *, import_job_id: str, mention_id: str) -> ExtractedMentionRecord:
        ...

    def list_resolution_candidates(
        self,
        *,
        import_job_id: str,
    ) -> list[ResolvedPlaceCandidateRecord]:
        ...

    def get_resolution_candidate(
        self,
        *,
        import_job_id: str,
        mention_id: str,
        candidate_id: str,
    ) -> ResolvedPlaceCandidateRecord:
        ...

    def create_review_decision(
        self,
        *,
        decision: ImportReviewDecisionRecord,
        base_review_version: int,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> tuple[ImportReviewDecisionRecord, ImportJobRecord, bool]:
        ...

    def list_review_decisions(self, *, import_job_id: str) -> list[ImportReviewDecisionRecord]:
        ...

    def get_idempotent_job(
        self,
        *,
        trip_id: str,
        scope: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> ImportJobRecord | None:
        ...

    def remember_idempotent_job(
        self,
        *,
        trip_id: str,
        scope: str,
        request_digest: str,
        idempotency_key_hash: str,
        job_id: str,
        created_at: str,
    ) -> None:
        ...

    def get_idempotent_commit(
        self,
        *,
        trip_id: str,
        scope: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> ImportCommitRecord | None:
        ...

    def get_commit_for_job(self, *, import_job_id: str) -> ImportCommitRecord | None:
        ...

    def create_commit_record(
        self,
        *,
        record: ImportCommitRecord,
        trip_id: str,
        request_digest: str,
        idempotency_key_hash: str,
        committed_at: str,
    ) -> ImportCommitRecord:
        ...


class SQLiteImportRepository:
    def __init__(self, connection_factory: Callable[[], sqlite3.Connection]) -> None:
        self.connection_factory = connection_factory

    def get_artifact(self, *, trip_id: str, artifact_id: str) -> SourceArtifactRecord:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                "SELECT * FROM source_artifacts WHERE trip_id = ? AND id = ?",
                (trip_id, artifact_id),
            ).fetchone()
        if row is None:
            raise TripError("import_artifact_not_found", "Import artifact was not found.", 404)
        return row_to_artifact(row)

    def find_artifact_by_checksum(
        self,
        *,
        trip_id: str,
        artifact_type: str,
        checksum: str,
    ) -> SourceArtifactRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT * FROM source_artifacts
                WHERE trip_id = ? AND artifact_type = ? AND content_checksum = ?
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (trip_id, artifact_type, checksum),
            ).fetchone()
        return row_to_artifact(row) if row else None

    def create_artifact(self, artifact: SourceArtifactRecord) -> SourceArtifactRecord:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO source_artifacts(
                  id, trip_id, artifact_type, mime_type, content_checksum,
                  byte_size, charset, privacy_level, storage_key, original_label, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.id,
                    artifact.trip_id,
                    artifact.artifact_type,
                    artifact.mime_type,
                    artifact.content_checksum,
                    artifact.byte_size,
                    artifact.charset,
                    artifact.privacy_level,
                    artifact.storage_key,
                    artifact.original_label,
                    artifact.created_at,
                ),
            )
        return artifact

    def create_job(self, job: ImportJobRecord) -> ImportJobRecord:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO import_jobs(
                  id, trip_id, artifact_id, input_type, status,
                  extraction_schema_version, extractor_version, resolver_version,
                  review_version, mention_count, warning_codes_json, error_code,
                  committed_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.trip_id,
                    job.artifact_id,
                    job.input_type,
                    job.status,
                    job.extraction_schema_version,
                    job.extractor_version,
                    job.resolver_version,
                    job.review_version,
                    job.mention_count,
                    json_dumps(job.warning_codes),
                    job.error_code,
                    job.committed_at,
                    job.created_at,
                    job.updated_at,
                ),
            )
        return job

    def get_job(self, *, trip_id: str, import_job_id: str) -> ImportJobRecord:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                "SELECT * FROM import_jobs WHERE trip_id = ? AND id = ?",
                (trip_id, import_job_id),
            ).fetchone()
        if row is None:
            raise TripError("import_not_found", "Import job was not found.", 404)
        return row_to_job(row)

    def find_latest_job_for_artifact(
        self,
        *,
        trip_id: str,
        artifact_id: str,
    ) -> ImportJobRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT * FROM import_jobs
                WHERE trip_id = ? AND artifact_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (trip_id, artifact_id),
            ).fetchone()
        return row_to_job(row) if row else None

    def update_job(
        self,
        *,
        trip_id: str,
        import_job_id: str,
        status: str | None,
        updated_at: str,
        mention_count: int | None = None,
        warning_codes: list[str] | None = None,
        error_code: str | None = None,
        committed_at: str | None = None,
    ) -> ImportJobRecord:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM import_jobs WHERE trip_id = ? AND id = ?",
                (trip_id, import_job_id),
            ).fetchone()
            if row is None:
                raise TripError("import_not_found", "Import job was not found.", 404)
            current = row_to_job(row)
            next_status = status or current.status
            if status is not None and status != current.status and not validate_import_transition(current.status, status):
                raise TripError("import_job_not_reviewable", "Import job status transition is not allowed.", 409)
            connection.execute(
                """
                UPDATE import_jobs
                SET status = ?, updated_at = ?, mention_count = ?,
                    warning_codes_json = ?, error_code = ?, committed_at = COALESCE(?, committed_at)
                WHERE trip_id = ? AND id = ?
                """,
                (
                    next_status,
                    updated_at,
                    mention_count if mention_count is not None else current.mention_count,
                    json_dumps(warning_codes if warning_codes is not None else current.warning_codes),
                    error_code,
                    committed_at,
                    trip_id,
                    import_job_id,
                ),
            )
            updated = connection.execute(
                "SELECT * FROM import_jobs WHERE trip_id = ? AND id = ?",
                (trip_id, import_job_id),
            ).fetchone()
        return row_to_job(updated)

    def create_attempt(self, attempt: ImportProcessingAttemptRecord) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO import_processing_attempts(
                  id, import_job_id, stage, extractor_version, resolver_version,
                  status, warning_codes_json, error_code, started_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.id,
                    attempt.import_job_id,
                    attempt.stage,
                    attempt.extractor_version,
                    attempt.resolver_version,
                    attempt.status,
                    json_dumps(attempt.warning_codes),
                    attempt.error_code,
                    attempt.started_at,
                    attempt.completed_at,
                ),
            )

    def complete_attempt(
        self,
        *,
        attempt_id: str,
        import_job_id: str,
        status: str,
        warning_codes: list[str],
        error_code: str | None,
        completed_at: str,
    ) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE import_processing_attempts
                SET status = ?, warning_codes_json = ?, error_code = ?, completed_at = ?
                WHERE id = ? AND import_job_id = ?
                """,
                (status, json_dumps(warning_codes), error_code, completed_at, attempt_id, import_job_id),
            )

    def add_mentions_and_resolutions(
        self,
        *,
        mentions: list[ExtractedMentionRecord],
        resolutions: list[ResolvedPlaceCandidateRecord],
    ) -> None:
        with self._transaction() as connection:
            for mention in mentions:
                connection.execute(
                    """
                    INSERT INTO extracted_mentions(
                      id, import_job_id, artifact_id, entity_type, raw_text, normalized_text,
                      start_offset, end_offset, context_before, context_after, city_hint,
                      date_hint, time_hint, recommendation_reason, confidence,
                      extraction_warning_codes_json, content_digest, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mention.id,
                        mention.import_job_id,
                        mention.artifact_id,
                        mention.entity_type,
                        mention.raw_text,
                        mention.normalized_text,
                        mention.start_offset,
                        mention.end_offset,
                        mention.context_before,
                        mention.context_after,
                        mention.city_hint,
                        mention.date_hint,
                        mention.time_hint,
                        mention.recommendation_reason,
                        mention.confidence,
                        json_dumps(mention.extraction_warning_codes),
                        mention.content_digest,
                        mention.created_at,
                    ),
                )
            for candidate in resolutions:
                connection.execute(
                    """
                    INSERT INTO resolved_place_candidates(
                      id, mention_id, provider, provider_place_id, canonical_name,
                      address_summary, administrative_area, city_code, latitude, longitude,
                      category, confidence, resolution_reason_codes_json, data_state,
                      candidate_digest, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate.id,
                        candidate.mention_id,
                        candidate.provider,
                        candidate.provider_place_id,
                        candidate.canonical_name,
                        candidate.address_summary,
                        candidate.administrative_area,
                        candidate.city_code,
                        candidate.latitude,
                        candidate.longitude,
                        candidate.category,
                        candidate.confidence,
                        json_dumps(candidate.resolution_reason_codes),
                        candidate.data_state,
                        candidate.candidate_digest,
                        candidate.created_at,
                    ),
                )

    def list_mentions(self, *, import_job_id: str) -> list[ExtractedMentionRecord]:
        with closing(self.connection_factory()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM extracted_mentions
                WHERE import_job_id = ?
                ORDER BY start_offset ASC, end_offset ASC, id ASC
                """,
                (import_job_id,),
            ).fetchall()
        return [row_to_mention(row) for row in rows]

    def get_mention(self, *, import_job_id: str, mention_id: str) -> ExtractedMentionRecord:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                "SELECT * FROM extracted_mentions WHERE import_job_id = ? AND id = ?",
                (import_job_id, mention_id),
            ).fetchone()
        if row is None:
            raise TripError("import_mention_not_found", "Import mention was not found.", 404)
        return row_to_mention(row)

    def list_resolution_candidates(
        self,
        *,
        import_job_id: str,
    ) -> list[ResolvedPlaceCandidateRecord]:
        with closing(self.connection_factory()) as connection:
            rows = connection.execute(
                """
                SELECT rpc.*
                FROM resolved_place_candidates rpc
                JOIN extracted_mentions em ON em.id = rpc.mention_id
                WHERE em.import_job_id = ?
                ORDER BY em.start_offset ASC, rpc.confidence DESC, rpc.canonical_name ASC, rpc.id ASC
                """,
                (import_job_id,),
            ).fetchall()
        return [row_to_resolution(row) for row in rows]

    def get_resolution_candidate(
        self,
        *,
        import_job_id: str,
        mention_id: str,
        candidate_id: str,
    ) -> ResolvedPlaceCandidateRecord:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT rpc.*
                FROM resolved_place_candidates rpc
                JOIN extracted_mentions em ON em.id = rpc.mention_id
                WHERE em.import_job_id = ? AND rpc.mention_id = ? AND rpc.id = ?
                """,
                (import_job_id, mention_id, candidate_id),
            ).fetchone()
        if row is None:
            raise TripError(
                "import_resolution_candidate_not_found",
                "Import resolution candidate was not found.",
                404,
            )
        return row_to_resolution(row)

    def create_review_decision(
        self,
        *,
        decision: ImportReviewDecisionRecord,
        base_review_version: int,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> tuple[ImportReviewDecisionRecord, ImportJobRecord, bool]:
        with self._transaction() as connection:
            job = self._get_job_in_connection(connection, decision.import_job_id)
            existing = connection.execute(
                """
                SELECT * FROM import_idempotency_records
                WHERE trip_id = ? AND scope = ? AND idempotency_key_hash = ?
                """,
                (job.trip_id, "review_decision", idempotency_key_hash),
            ).fetchone()
            if existing is not None:
                if existing["request_digest"] != request_digest:
                    raise IdempotencyConflictError()
                stored = self._get_decision_in_connection(connection, existing["result_ref"])
                return stored, job, True
            if job.review_version != base_review_version:
                raise TripError("stale_import_review", "Import review is based on a stale version.", 409)
            next_version = job.review_version + 1
            stored_decision = replace(decision, review_version=next_version)
            connection.execute(
                """
                INSERT INTO import_review_decisions(
                  id, import_job_id, mention_id, review_version, action,
                  selected_resolution_candidate_id, merge_target_mention_id,
                  note_text, reason_code, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored_decision.id,
                    stored_decision.import_job_id,
                    stored_decision.mention_id,
                    stored_decision.review_version,
                    stored_decision.action,
                    stored_decision.selected_resolution_candidate_id,
                    stored_decision.merge_target_mention_id,
                    stored_decision.note_text,
                    stored_decision.reason_code,
                    stored_decision.created_at,
                ),
            )
            connection.execute(
                """
                UPDATE import_jobs
                SET review_version = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_version, stored_decision.created_at, job.id),
            )
            connection.execute(
                """
                INSERT INTO import_idempotency_records(
                  trip_id, scope, idempotency_key_hash, request_digest, result_ref, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    job.trip_id,
                    "review_decision",
                    idempotency_key_hash,
                    request_digest,
                    stored_decision.id,
                    stored_decision.created_at,
                ),
            )
            updated_job = self._get_job_in_connection(connection, job.id)
        return stored_decision, updated_job, False

    def list_review_decisions(self, *, import_job_id: str) -> list[ImportReviewDecisionRecord]:
        with closing(self.connection_factory()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM import_review_decisions
                WHERE import_job_id = ?
                ORDER BY review_version ASC, created_at ASC, id ASC
                """,
                (import_job_id,),
            ).fetchall()
        return [row_to_decision(row) for row in rows]

    def get_idempotent_job(
        self,
        *,
        trip_id: str,
        scope: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> ImportJobRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT * FROM import_idempotency_records
                WHERE trip_id = ? AND scope = ? AND idempotency_key_hash = ?
                """,
                (trip_id, scope, idempotency_key_hash),
            ).fetchone()
            if row is None:
                return None
            if row["request_digest"] != request_digest:
                raise IdempotencyConflictError()
            job_row = connection.execute(
                "SELECT * FROM import_jobs WHERE trip_id = ? AND id = ?",
                (trip_id, row["result_ref"]),
            ).fetchone()
        return row_to_job(job_row) if job_row else None

    def remember_idempotent_job(
        self,
        *,
        trip_id: str,
        scope: str,
        request_digest: str,
        idempotency_key_hash: str,
        job_id: str,
        created_at: str,
    ) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO import_idempotency_records(
                  trip_id, scope, idempotency_key_hash, request_digest, result_ref, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (trip_id, scope, idempotency_key_hash, request_digest, job_id, created_at),
            )

    def get_idempotent_commit(
        self,
        *,
        trip_id: str,
        scope: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> ImportCommitRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT * FROM import_idempotency_records
                WHERE trip_id = ? AND scope = ? AND idempotency_key_hash = ?
                """,
                (trip_id, scope, idempotency_key_hash),
            ).fetchone()
            if row is None:
                return None
            if row["request_digest"] != request_digest:
                raise IdempotencyConflictError()
            commit_row = connection.execute(
                "SELECT * FROM import_commit_records WHERE id = ?",
                (row["result_ref"],),
            ).fetchone()
        return row_to_commit(commit_row) if commit_row else None

    def get_commit_for_job(self, *, import_job_id: str) -> ImportCommitRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                "SELECT * FROM import_commit_records WHERE import_job_id = ?",
                (import_job_id,),
            ).fetchone()
        return row_to_commit(row) if row else None

    def create_commit_record(
        self,
        *,
        record: ImportCommitRecord,
        trip_id: str,
        request_digest: str,
        idempotency_key_hash: str,
        committed_at: str,
    ) -> ImportCommitRecord:
        with self._transaction() as connection:
            existing_commit = connection.execute(
                "SELECT * FROM import_commit_records WHERE import_job_id = ?",
                (record.import_job_id,),
            ).fetchone()
            if existing_commit is not None:
                return row_to_commit(existing_commit)
            connection.execute(
                """
                INSERT INTO import_commit_records(
                  id, import_job_id, review_version, result_json, commit_digest, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.import_job_id,
                    record.review_version,
                    json_dumps(record.result_json),
                    record.commit_digest,
                    record.created_at,
                ),
            )
            connection.execute(
                """
                UPDATE import_jobs
                SET status = 'committed', committed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (committed_at, committed_at, record.import_job_id),
            )
            connection.execute(
                """
                INSERT INTO import_idempotency_records(
                  trip_id, scope, idempotency_key_hash, request_digest, result_ref, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (trip_id, "commit", idempotency_key_hash, request_digest, record.id, committed_at),
            )
        return record

    @contextmanager
    def _transaction(self):
        connection = self.connection_factory()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            if "UNIQUE" in str(exc):
                raise IdempotencyConflictError() from exc
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise TripError("persistence_temporarily_unavailable", "Persistence is temporarily unavailable.", 503) from exc
        finally:
            connection.close()

    def _get_job_in_connection(self, connection: sqlite3.Connection, import_job_id: str) -> ImportJobRecord:
        row = connection.execute("SELECT * FROM import_jobs WHERE id = ?", (import_job_id,)).fetchone()
        if row is None:
            raise TripError("import_not_found", "Import job was not found.", 404)
        return row_to_job(row)

    def _get_decision_in_connection(self, connection: sqlite3.Connection, decision_id: str) -> ImportReviewDecisionRecord:
        row = connection.execute("SELECT * FROM import_review_decisions WHERE id = ?", (decision_id,)).fetchone()
        if row is None:
            raise TripError("import_review_action_invalid", "Import review decision was not found.", 404)
        return row_to_decision(row)


class MemoryImportRepository:
    def __init__(self) -> None:
        self.artifacts: dict[str, SourceArtifactRecord] = {}
        self.jobs: dict[str, ImportJobRecord] = {}
        self.attempts: dict[str, ImportProcessingAttemptRecord] = {}
        self.mentions: dict[str, ExtractedMentionRecord] = {}
        self.resolutions: dict[str, ResolvedPlaceCandidateRecord] = {}
        self.decisions: dict[str, ImportReviewDecisionRecord] = {}
        self.idempotency: dict[tuple[str, str, str], tuple[str, str]] = {}
        self.commits: dict[str, ImportCommitRecord] = {}

    def get_artifact(self, *, trip_id: str, artifact_id: str) -> SourceArtifactRecord:
        artifact = self.artifacts.get(artifact_id)
        if artifact is None or artifact.trip_id != trip_id:
            raise TripError("import_artifact_not_found", "Import artifact was not found.", 404)
        return copy.deepcopy(artifact)

    def find_artifact_by_checksum(self, *, trip_id: str, artifact_type: str, checksum: str) -> SourceArtifactRecord | None:
        for artifact in sorted(self.artifacts.values(), key=lambda item: (item.created_at, item.id)):
            if artifact.trip_id == trip_id and artifact.artifact_type == artifact_type and artifact.content_checksum == checksum:
                return copy.deepcopy(artifact)
        return None

    def create_artifact(self, artifact: SourceArtifactRecord) -> SourceArtifactRecord:
        self.artifacts[artifact.id] = copy.deepcopy(artifact)
        return copy.deepcopy(artifact)

    def create_job(self, job: ImportJobRecord) -> ImportJobRecord:
        self.jobs[job.id] = copy.deepcopy(job)
        return copy.deepcopy(job)

    def get_job(self, *, trip_id: str, import_job_id: str) -> ImportJobRecord:
        job = self.jobs.get(import_job_id)
        if job is None or job.trip_id != trip_id:
            raise TripError("import_not_found", "Import job was not found.", 404)
        return copy.deepcopy(job)

    def find_latest_job_for_artifact(self, *, trip_id: str, artifact_id: str) -> ImportJobRecord | None:
        jobs = [job for job in self.jobs.values() if job.trip_id == trip_id and job.artifact_id == artifact_id]
        if not jobs:
            return None
        return copy.deepcopy(sorted(jobs, key=lambda item: (item.created_at, item.id), reverse=True)[0])

    def update_job(self, *, trip_id: str, import_job_id: str, status: str | None, updated_at: str, mention_count: int | None = None, warning_codes: list[str] | None = None, error_code: str | None = None, committed_at: str | None = None) -> ImportJobRecord:
        job = self.get_job(trip_id=trip_id, import_job_id=import_job_id)
        next_status = status or job.status
        if status is not None and status != job.status and not validate_import_transition(job.status, status):
            raise TripError("import_job_not_reviewable", "Import job status transition is not allowed.", 409)
        updated = replace(
            job,
            status=next_status,
            updated_at=updated_at,
            mention_count=mention_count if mention_count is not None else job.mention_count,
            warning_codes=list(warning_codes if warning_codes is not None else job.warning_codes),
            error_code=error_code,
            committed_at=committed_at or job.committed_at,
        )
        self.jobs[updated.id] = copy.deepcopy(updated)
        return copy.deepcopy(updated)

    def create_attempt(self, attempt: ImportProcessingAttemptRecord) -> None:
        self.attempts[attempt.id] = copy.deepcopy(attempt)

    def complete_attempt(self, *, attempt_id: str, import_job_id: str, status: str, warning_codes: list[str], error_code: str | None, completed_at: str) -> None:
        attempt = self.attempts[attempt_id]
        self.attempts[attempt_id] = replace(
            attempt,
            status=status,
            warning_codes=list(warning_codes),
            error_code=error_code,
            completed_at=completed_at,
        )

    def add_mentions_and_resolutions(self, *, mentions: list[ExtractedMentionRecord], resolutions: list[ResolvedPlaceCandidateRecord]) -> None:
        for mention in mentions:
            self.mentions[mention.id] = copy.deepcopy(mention)
        for resolution in resolutions:
            self.resolutions[resolution.id] = copy.deepcopy(resolution)

    def list_mentions(self, *, import_job_id: str) -> list[ExtractedMentionRecord]:
        return sorted(
            [copy.deepcopy(mention) for mention in self.mentions.values() if mention.import_job_id == import_job_id],
            key=lambda item: (item.start_offset, item.end_offset, item.id),
        )

    def get_mention(self, *, import_job_id: str, mention_id: str) -> ExtractedMentionRecord:
        mention = self.mentions.get(mention_id)
        if mention is None or mention.import_job_id != import_job_id:
            raise TripError("import_mention_not_found", "Import mention was not found.", 404)
        return copy.deepcopy(mention)

    def list_resolution_candidates(self, *, import_job_id: str) -> list[ResolvedPlaceCandidateRecord]:
        mention_ids = {mention.id for mention in self.mentions.values() if mention.import_job_id == import_job_id}
        return sorted(
            [copy.deepcopy(candidate) for candidate in self.resolutions.values() if candidate.mention_id in mention_ids],
            key=lambda item: (item.mention_id, -item.confidence, item.canonical_name, item.id),
        )

    def get_resolution_candidate(self, *, import_job_id: str, mention_id: str, candidate_id: str) -> ResolvedPlaceCandidateRecord:
        self.get_mention(import_job_id=import_job_id, mention_id=mention_id)
        candidate = self.resolutions.get(candidate_id)
        if candidate is None or candidate.mention_id != mention_id:
            raise TripError("import_resolution_candidate_not_found", "Import resolution candidate was not found.", 404)
        return copy.deepcopy(candidate)

    def create_review_decision(self, *, decision: ImportReviewDecisionRecord, base_review_version: int, request_digest: str, idempotency_key_hash: str) -> tuple[ImportReviewDecisionRecord, ImportJobRecord, bool]:
        job = self.jobs[decision.import_job_id]
        key = (job.trip_id, "review_decision", idempotency_key_hash)
        existing = self.idempotency.get(key)
        if existing is not None:
            stored_digest, result_ref = existing
            if stored_digest != request_digest:
                raise IdempotencyConflictError()
            return copy.deepcopy(self.decisions[result_ref]), copy.deepcopy(job), True
        if job.review_version != base_review_version:
            raise TripError("stale_import_review", "Import review is based on a stale version.", 409)
        next_version = job.review_version + 1
        stored = replace(decision, review_version=next_version)
        self.decisions[stored.id] = copy.deepcopy(stored)
        updated_job = replace(job, review_version=next_version, updated_at=stored.created_at)
        self.jobs[job.id] = copy.deepcopy(updated_job)
        self.idempotency[key] = (request_digest, stored.id)
        return copy.deepcopy(stored), copy.deepcopy(updated_job), False

    def list_review_decisions(self, *, import_job_id: str) -> list[ImportReviewDecisionRecord]:
        return sorted(
            [copy.deepcopy(decision) for decision in self.decisions.values() if decision.import_job_id == import_job_id],
            key=lambda item: (item.review_version, item.created_at, item.id),
        )

    def get_idempotent_job(self, *, trip_id: str, scope: str, request_digest: str, idempotency_key_hash: str) -> ImportJobRecord | None:
        existing = self.idempotency.get((trip_id, scope, idempotency_key_hash))
        if existing is None:
            return None
        stored_digest, job_id = existing
        if stored_digest != request_digest:
            raise IdempotencyConflictError()
        return self.get_job(trip_id=trip_id, import_job_id=job_id)

    def remember_idempotent_job(self, *, trip_id: str, scope: str, request_digest: str, idempotency_key_hash: str, job_id: str, created_at: str) -> None:
        self.idempotency[(trip_id, scope, idempotency_key_hash)] = (request_digest, job_id)

    def get_idempotent_commit(self, *, trip_id: str, scope: str, request_digest: str, idempotency_key_hash: str) -> ImportCommitRecord | None:
        existing = self.idempotency.get((trip_id, scope, idempotency_key_hash))
        if existing is None:
            return None
        stored_digest, commit_id = existing
        if stored_digest != request_digest:
            raise IdempotencyConflictError()
        return copy.deepcopy(self.commits[commit_id])

    def get_commit_for_job(self, *, import_job_id: str) -> ImportCommitRecord | None:
        existing = next((commit for commit in self.commits.values() if commit.import_job_id == import_job_id), None)
        return copy.deepcopy(existing) if existing else None

    def create_commit_record(self, *, record: ImportCommitRecord, trip_id: str, request_digest: str, idempotency_key_hash: str, committed_at: str) -> ImportCommitRecord:
        existing = next((commit for commit in self.commits.values() if commit.import_job_id == record.import_job_id), None)
        if existing is not None:
            return copy.deepcopy(existing)
        self.commits[record.id] = copy.deepcopy(record)
        job = self.jobs[record.import_job_id]
        self.jobs[job.id] = replace(job, status="committed", committed_at=committed_at, updated_at=committed_at)
        self.idempotency[(trip_id, "commit", idempotency_key_hash)] = (request_digest, record.id)
        return copy.deepcopy(record)


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_loads(raw: str | None, fallback: Any) -> Any:
    if raw is None:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def row_to_artifact(row) -> SourceArtifactRecord:
    return SourceArtifactRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        artifact_type=row["artifact_type"],
        mime_type=row["mime_type"],
        content_checksum=row["content_checksum"],
        byte_size=row["byte_size"],
        charset=row["charset"],
        privacy_level=row["privacy_level"],
        storage_key=row["storage_key"],
        original_label=row["original_label"],
        created_at=row["created_at"],
    )


def row_to_job(row) -> ImportJobRecord:
    return ImportJobRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        artifact_id=row["artifact_id"],
        input_type=row["input_type"],
        status=row["status"],
        extraction_schema_version=row["extraction_schema_version"],
        extractor_version=row["extractor_version"],
        resolver_version=row["resolver_version"],
        review_version=row["review_version"],
        mention_count=row["mention_count"],
        warning_codes=list(json_loads(row["warning_codes_json"], [])),
        error_code=row["error_code"],
        committed_at=row["committed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_mention(row) -> ExtractedMentionRecord:
    return ExtractedMentionRecord(
        id=row["id"],
        import_job_id=row["import_job_id"],
        artifact_id=row["artifact_id"],
        entity_type=row["entity_type"],
        raw_text=row["raw_text"],
        normalized_text=row["normalized_text"],
        start_offset=row["start_offset"],
        end_offset=row["end_offset"],
        context_before=row["context_before"],
        context_after=row["context_after"],
        city_hint=row["city_hint"],
        date_hint=row["date_hint"],
        time_hint=row["time_hint"],
        recommendation_reason=row["recommendation_reason"],
        confidence=row["confidence"],
        extraction_warning_codes=list(json_loads(row["extraction_warning_codes_json"], [])),
        content_digest=row["content_digest"],
        created_at=row["created_at"],
    )


def row_to_resolution(row) -> ResolvedPlaceCandidateRecord:
    return ResolvedPlaceCandidateRecord(
        id=row["id"],
        mention_id=row["mention_id"],
        provider=row["provider"],
        provider_place_id=row["provider_place_id"],
        canonical_name=row["canonical_name"],
        address_summary=row["address_summary"],
        administrative_area=row["administrative_area"],
        city_code=row["city_code"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        category=row["category"],
        confidence=row["confidence"],
        resolution_reason_codes=list(json_loads(row["resolution_reason_codes_json"], [])),
        data_state=row["data_state"],
        candidate_digest=row["candidate_digest"],
        created_at=row["created_at"],
    )


def row_to_decision(row) -> ImportReviewDecisionRecord:
    return ImportReviewDecisionRecord(
        id=row["id"],
        import_job_id=row["import_job_id"],
        mention_id=row["mention_id"],
        review_version=row["review_version"],
        action=row["action"],
        selected_resolution_candidate_id=row["selected_resolution_candidate_id"],
        merge_target_mention_id=row["merge_target_mention_id"],
        note_text=row["note_text"],
        reason_code=row["reason_code"],
        created_at=row["created_at"],
    )


def row_to_commit(row) -> ImportCommitRecord:
    return ImportCommitRecord(
        id=row["id"],
        import_job_id=row["import_job_id"],
        review_version=row["review_version"],
        result_json=dict(json_loads(row["result_json"], {})),
        commit_digest=row["commit_digest"],
        created_at=row["created_at"],
    )
