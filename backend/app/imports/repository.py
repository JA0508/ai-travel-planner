from __future__ import annotations

import copy
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import replace
from typing import Any, Protocol

from app.imports.domain import (
    ArtifactDerivationRecord,
    ArtifactInspectionFindingRecord,
    ArtifactInspectionRecord,
    DocumentExtractionGenerationRecord,
    DocumentTextSpanRecord,
    ExtractedMentionRecord,
    ImportCommitRecord,
    ImportJobRecord,
    ImportProcessingAttemptRecord,
    ImportReviewDecisionRecord,
    ResolvedPlaceCandidateRecord,
    SourceArtifactRecord,
    URLFetchSnapshotRecord,
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

    def create_url_fetch_snapshot(self, snapshot: URLFetchSnapshotRecord) -> URLFetchSnapshotRecord:
        ...

    def get_url_fetch_snapshot_for_job(self, *, import_job_id: str) -> URLFetchSnapshotRecord | None:
        ...

    def find_latest_url_fetch_snapshot(
        self,
        *,
        normalized_request_url: str,
    ) -> URLFetchSnapshotRecord | None:
        ...

    def create_artifact_derivation(self, derivation: ArtifactDerivationRecord) -> ArtifactDerivationRecord:
        ...

    def get_artifact_derivation_for_child(self, *, child_artifact_id: str) -> ArtifactDerivationRecord | None:
        ...

    def get_artifact_derivations_for_parent(self, *, parent_artifact_id: str) -> list[ArtifactDerivationRecord]:
        ...

    def create_completed_artifact_inspection(
        self,
        *,
        inspection: ArtifactInspectionRecord,
        findings: list[ArtifactInspectionFindingRecord],
        child_artifact: SourceArtifactRecord | None,
        derivation: ArtifactDerivationRecord | None,
        final_job_status: str,
        updated_at: str,
    ) -> ArtifactInspectionRecord:
        ...

    def get_latest_artifact_inspection_for_job(
        self,
        *,
        trip_id: str,
        import_job_id: str,
    ) -> ArtifactInspectionRecord | None:
        ...

    def list_artifact_inspection_findings(self, *, inspection_id: str) -> list[ArtifactInspectionFindingRecord]:
        ...

    def get_latest_document_extraction_for_source(
        self,
        *,
        trip_id: str,
        source_import_job_id: str,
    ) -> DocumentExtractionGenerationRecord | None:
        ...

    def get_document_extraction_for_derived_job(
        self,
        *,
        derived_import_job_id: str,
    ) -> DocumentExtractionGenerationRecord | None:
        ...

    def list_document_text_spans(self, *, generation_id: str) -> list[DocumentTextSpanRecord]:
        ...

    def create_document_extraction_result(
        self,
        *,
        generation: DocumentExtractionGenerationRecord,
        spans: list[DocumentTextSpanRecord],
        child_artifact: SourceArtifactRecord,
        derivation: ArtifactDerivationRecord,
        derived_job: ImportJobRecord,
        related_artifacts: list[SourceArtifactRecord] | None = None,
        related_derivations: list[ArtifactDerivationRecord] | None = None,
    ) -> DocumentExtractionGenerationRecord:
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

    def create_url_fetch_snapshot(self, snapshot: URLFetchSnapshotRecord) -> URLFetchSnapshotRecord:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO url_fetch_snapshots(
                  id, import_job_id, raw_artifact_id, request_url_sanitized,
                  normalized_request_url, final_url_sanitized, final_url,
                  redirect_chain_json, robots_status, robots_checked_at, status_code,
                  content_type, declared_charset, effective_charset, content_language,
                  compressed_bytes, decoded_bytes, body_checksum, header_metadata_json,
                  fetcher_version, policy_version, fetched_at, warning_codes_json,
                  cache_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    snapshot.import_job_id,
                    snapshot.raw_artifact_id,
                    snapshot.request_url_sanitized,
                    snapshot.normalized_request_url,
                    snapshot.final_url_sanitized,
                    snapshot.final_url,
                    json_dumps(snapshot.redirect_chain),
                    snapshot.robots_status,
                    snapshot.robots_checked_at,
                    snapshot.status_code,
                    snapshot.content_type,
                    snapshot.declared_charset,
                    snapshot.effective_charset,
                    snapshot.content_language,
                    snapshot.compressed_bytes,
                    snapshot.decoded_bytes,
                    snapshot.body_checksum,
                    json_dumps(snapshot.header_metadata),
                    snapshot.fetcher_version,
                    snapshot.policy_version,
                    snapshot.fetched_at,
                    json_dumps(snapshot.warning_codes),
                    snapshot.cache_status,
                ),
            )
        return snapshot

    def get_url_fetch_snapshot_for_job(self, *, import_job_id: str) -> URLFetchSnapshotRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT * FROM url_fetch_snapshots
                WHERE import_job_id = ?
                ORDER BY fetched_at DESC, id DESC
                LIMIT 1
                """,
                (import_job_id,),
            ).fetchone()
        return row_to_url_fetch_snapshot(row) if row else None

    def find_latest_url_fetch_snapshot(self, *, normalized_request_url: str) -> URLFetchSnapshotRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT * FROM url_fetch_snapshots
                WHERE normalized_request_url = ?
                ORDER BY fetched_at DESC, id DESC
                LIMIT 1
                """,
                (normalized_request_url,),
            ).fetchone()
        return row_to_url_fetch_snapshot(row) if row else None

    def create_artifact_derivation(self, derivation: ArtifactDerivationRecord) -> ArtifactDerivationRecord:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO artifact_derivations(
                  id, parent_artifact_id, child_artifact_id, derivation_type,
                  transformer_version, input_checksum, output_checksum,
                  metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    derivation.id,
                    derivation.parent_artifact_id,
                    derivation.child_artifact_id,
                    derivation.derivation_type,
                    derivation.transformer_version,
                    derivation.input_checksum,
                    derivation.output_checksum,
                    json_dumps(derivation.metadata),
                    derivation.created_at,
                ),
            )
        return derivation

    def get_artifact_derivation_for_child(self, *, child_artifact_id: str) -> ArtifactDerivationRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                "SELECT * FROM artifact_derivations WHERE child_artifact_id = ?",
                (child_artifact_id,),
            ).fetchone()
        return row_to_artifact_derivation(row) if row else None

    def get_artifact_derivations_for_parent(self, *, parent_artifact_id: str) -> list[ArtifactDerivationRecord]:
        with closing(self.connection_factory()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM artifact_derivations
                WHERE parent_artifact_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (parent_artifact_id,),
            ).fetchall()
        return [row_to_artifact_derivation(row) for row in rows]

    def create_completed_artifact_inspection(
        self,
        *,
        inspection: ArtifactInspectionRecord,
        findings: list[ArtifactInspectionFindingRecord],
        child_artifact: SourceArtifactRecord | None,
        derivation: ArtifactDerivationRecord | None,
        final_job_status: str,
        updated_at: str,
    ) -> ArtifactInspectionRecord:
        with self._transaction() as connection:
            job_row = connection.execute(
                "SELECT * FROM import_jobs WHERE trip_id = ? AND id = ?",
                (inspection.trip_id, inspection.import_job_id),
            ).fetchone()
            if job_row is None:
                raise TripError("import_not_found", "Import job was not found.", 404)
            job = row_to_job(job_row)
            if job.artifact_id != inspection.artifact_id or job.status != "inspecting":
                raise TripError("import_artifact_not_ready", "Artifact inspection cannot be completed from the current job state.", 409)
            if child_artifact is not None:
                connection.execute(
                    """
                    INSERT INTO source_artifacts(
                      id, trip_id, artifact_type, mime_type, content_checksum,
                      byte_size, charset, privacy_level, storage_key, original_label, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        child_artifact.id,
                        child_artifact.trip_id,
                        child_artifact.artifact_type,
                        child_artifact.mime_type,
                        child_artifact.content_checksum,
                        child_artifact.byte_size,
                        child_artifact.charset,
                        child_artifact.privacy_level,
                        child_artifact.storage_key,
                        child_artifact.original_label,
                        child_artifact.created_at,
                    ),
                )
            connection.execute(
                """
                INSERT INTO artifact_inspections(
                  id, trip_id, import_job_id, artifact_id, attempt, schema_version,
                  inspector_version, declared_kind, detected_kind, declared_mime_type,
                  detected_mime_type, status, classification, byte_size, content_checksum,
                  metadata_json, sanitized_artifact_id, manifest_artifact_id,
                  warning_codes_json, error_code, started_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inspection.id,
                    inspection.trip_id,
                    inspection.import_job_id,
                    inspection.artifact_id,
                    inspection.attempt,
                    inspection.schema_version,
                    inspection.inspector_version,
                    inspection.declared_kind,
                    inspection.detected_kind,
                    inspection.declared_mime_type,
                    inspection.detected_mime_type,
                    inspection.status,
                    inspection.classification,
                    inspection.byte_size,
                    inspection.content_checksum,
                    json_dumps(inspection.metadata),
                    inspection.sanitized_artifact_id,
                    inspection.manifest_artifact_id,
                    json_dumps(inspection.warning_codes),
                    inspection.error_code,
                    inspection.started_at,
                    inspection.completed_at,
                ),
            )
            for item in findings:
                connection.execute(
                    """
                    INSERT INTO artifact_inspection_findings(
                      id, inspection_id, code, severity, category, evidence_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.id,
                        item.inspection_id,
                        item.code,
                        item.severity,
                        item.category,
                        json_dumps(item.evidence),
                        item.created_at,
                    ),
                )
            if derivation is not None:
                connection.execute(
                    """
                    INSERT INTO artifact_derivations(
                      id, parent_artifact_id, child_artifact_id, derivation_type,
                      transformer_version, input_checksum, output_checksum,
                      metadata_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        derivation.id,
                        derivation.parent_artifact_id,
                        derivation.child_artifact_id,
                        derivation.derivation_type,
                        derivation.transformer_version,
                        derivation.input_checksum,
                        derivation.output_checksum,
                        json_dumps(derivation.metadata),
                        derivation.created_at,
                    ),
                )
            connection.execute(
                """
                UPDATE import_jobs
                SET status = ?, updated_at = ?, warning_codes_json = ?, error_code = ?
                WHERE trip_id = ? AND id = ?
                """,
                (
                    final_job_status,
                    updated_at,
                    json_dumps(inspection.warning_codes),
                    inspection.error_code,
                    inspection.trip_id,
                    inspection.import_job_id,
                ),
            )
        return inspection

    def get_latest_artifact_inspection_for_job(
        self,
        *,
        trip_id: str,
        import_job_id: str,
    ) -> ArtifactInspectionRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT * FROM artifact_inspections
                WHERE trip_id = ? AND import_job_id = ?
                ORDER BY completed_at DESC, attempt DESC, id DESC
                LIMIT 1
                """,
                (trip_id, import_job_id),
            ).fetchone()
        return row_to_artifact_inspection(row) if row else None

    def list_artifact_inspection_findings(self, *, inspection_id: str) -> list[ArtifactInspectionFindingRecord]:
        with closing(self.connection_factory()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM artifact_inspection_findings
                WHERE inspection_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (inspection_id,),
            ).fetchall()
        return [row_to_artifact_inspection_finding(row) for row in rows]

    def get_latest_document_extraction_for_source(
        self,
        *,
        trip_id: str,
        source_import_job_id: str,
    ) -> DocumentExtractionGenerationRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT * FROM document_extraction_generations
                WHERE trip_id = ? AND source_import_job_id = ?
                ORDER BY generation DESC, created_at DESC, id DESC
                LIMIT 1
                """,
                (trip_id, source_import_job_id),
            ).fetchone()
        return row_to_document_extraction_generation(row) if row else None

    def get_document_extraction_for_derived_job(
        self,
        *,
        derived_import_job_id: str,
    ) -> DocumentExtractionGenerationRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT * FROM document_extraction_generations
                WHERE derived_import_job_id = ?
                ORDER BY generation DESC, created_at DESC, id DESC
                LIMIT 1
                """,
                (derived_import_job_id,),
            ).fetchone()
        return row_to_document_extraction_generation(row) if row else None

    def list_document_text_spans(self, *, generation_id: str) -> list[DocumentTextSpanRecord]:
        with closing(self.connection_factory()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM document_text_spans
                WHERE generation_id = ?
                ORDER BY page_number ASC, block_index ASC, line_index ASC,
                         COALESCE(token_index, -1) ASC, span_start ASC, id ASC
                """,
                (generation_id,),
            ).fetchall()
        return [row_to_document_text_span(row) for row in rows]

    def create_document_extraction_result(
        self,
        *,
        generation: DocumentExtractionGenerationRecord,
        spans: list[DocumentTextSpanRecord],
        child_artifact: SourceArtifactRecord,
        derivation: ArtifactDerivationRecord,
        derived_job: ImportJobRecord,
        related_artifacts: list[SourceArtifactRecord] | None = None,
        related_derivations: list[ArtifactDerivationRecord] | None = None,
    ) -> DocumentExtractionGenerationRecord:
        with self._transaction() as connection:
            source_job = connection.execute(
                "SELECT * FROM import_jobs WHERE trip_id = ? AND id = ?",
                (generation.trip_id, generation.source_import_job_id),
            ).fetchone()
            if source_job is None:
                raise TripError("import_not_found", "Source import job was not found.", 404)
            connection.execute(
                """
                INSERT INTO source_artifacts(
                  id, trip_id, artifact_type, mime_type, content_checksum,
                  byte_size, charset, privacy_level, storage_key, original_label, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    child_artifact.id,
                    child_artifact.trip_id,
                    child_artifact.artifact_type,
                    child_artifact.mime_type,
                    child_artifact.content_checksum,
                    child_artifact.byte_size,
                    child_artifact.charset,
                    child_artifact.privacy_level,
                    child_artifact.storage_key,
                    child_artifact.original_label,
                    child_artifact.created_at,
                ),
            )
            for related_artifact in related_artifacts or []:
                connection.execute(
                    """
                    INSERT INTO source_artifacts(
                      id, trip_id, artifact_type, mime_type, content_checksum,
                      byte_size, charset, privacy_level, storage_key, original_label, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        related_artifact.id,
                        related_artifact.trip_id,
                        related_artifact.artifact_type,
                        related_artifact.mime_type,
                        related_artifact.content_checksum,
                        related_artifact.byte_size,
                        related_artifact.charset,
                        related_artifact.privacy_level,
                        related_artifact.storage_key,
                        related_artifact.original_label,
                        related_artifact.created_at,
                    ),
                )
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
                    derived_job.id,
                    derived_job.trip_id,
                    derived_job.artifact_id,
                    derived_job.input_type,
                    derived_job.status,
                    derived_job.extraction_schema_version,
                    derived_job.extractor_version,
                    derived_job.resolver_version,
                    derived_job.review_version,
                    derived_job.mention_count,
                    json_dumps(derived_job.warning_codes),
                    derived_job.error_code,
                    derived_job.committed_at,
                    derived_job.created_at,
                    derived_job.updated_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO artifact_derivations(
                  id, parent_artifact_id, child_artifact_id, derivation_type,
                  transformer_version, input_checksum, output_checksum,
                  metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    derivation.id,
                    derivation.parent_artifact_id,
                    derivation.child_artifact_id,
                    derivation.derivation_type,
                    derivation.transformer_version,
                    derivation.input_checksum,
                    derivation.output_checksum,
                    json_dumps(derivation.metadata),
                    derivation.created_at,
                ),
            )
            for related_derivation in related_derivations or []:
                connection.execute(
                    """
                    INSERT INTO artifact_derivations(
                      id, parent_artifact_id, child_artifact_id, derivation_type,
                      transformer_version, input_checksum, output_checksum,
                      metadata_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        related_derivation.id,
                        related_derivation.parent_artifact_id,
                        related_derivation.child_artifact_id,
                        related_derivation.derivation_type,
                        related_derivation.transformer_version,
                        related_derivation.input_checksum,
                        related_derivation.output_checksum,
                        json_dumps(related_derivation.metadata),
                        related_derivation.created_at,
                    ),
                )
            connection.execute(
                """
                INSERT INTO document_extraction_generations(
                  id, trip_id, source_import_job_id, source_artifact_id, inspection_id,
                  derived_import_job_id, derived_artifact_id, layout_artifact_id,
                  span_map_artifact_id, generation, schema_version,
                  extractor_version, strategy, status, page_count, extracted_text_chars,
                  warning_codes_json, error_code, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    generation.id,
                    generation.trip_id,
                    generation.source_import_job_id,
                    generation.source_artifact_id,
                    generation.inspection_id,
                    generation.derived_import_job_id,
                    generation.derived_artifact_id,
                    generation.layout_artifact_id,
                    generation.span_map_artifact_id,
                    generation.generation,
                    generation.schema_version,
                    generation.extractor_version,
                    generation.strategy,
                    generation.status,
                    generation.page_count,
                    generation.extracted_text_chars,
                    json_dumps(generation.warning_codes),
                    generation.error_code,
                    json_dumps(generation.metadata),
                    generation.created_at,
                ),
            )
            for span in spans:
                connection.execute(
                """
                    INSERT INTO document_text_spans(
                      id, generation_id, span_start, span_end, page_number,
                      block_index, line_index, token_index, block_id, line_id,
                      token_id, reading_order, bbox_json, source_kind, confidence,
                      text_digest, warning_codes_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        span.id,
                        span.generation_id,
                        span.span_start,
                        span.span_end,
                        span.page_number,
                        span.block_index,
                        span.line_index,
                        span.token_index,
                        span.block_id,
                        span.line_id,
                        span.token_id,
                        span.reading_order,
                        json_dumps(span.bbox),
                        span.source_kind,
                        span.confidence,
                        span.text_digest,
                        json_dumps(span.warning_codes),
                        span.created_at,
                    ),
                )
        return generation

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
        self.url_fetch_snapshots: dict[str, URLFetchSnapshotRecord] = {}
        self.artifact_derivations: dict[str, ArtifactDerivationRecord] = {}
        self.artifact_inspections: dict[str, ArtifactInspectionRecord] = {}
        self.artifact_inspection_findings: dict[str, ArtifactInspectionFindingRecord] = {}
        self.document_extractions: dict[str, DocumentExtractionGenerationRecord] = {}
        self.document_text_spans: dict[str, DocumentTextSpanRecord] = {}

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

    def create_url_fetch_snapshot(self, snapshot: URLFetchSnapshotRecord) -> URLFetchSnapshotRecord:
        self.url_fetch_snapshots[snapshot.id] = copy.deepcopy(snapshot)
        return copy.deepcopy(snapshot)

    def get_url_fetch_snapshot_for_job(self, *, import_job_id: str) -> URLFetchSnapshotRecord | None:
        snapshots = [
            snapshot for snapshot in self.url_fetch_snapshots.values()
            if snapshot.import_job_id == import_job_id
        ]
        if not snapshots:
            return None
        return copy.deepcopy(sorted(snapshots, key=lambda item: (item.fetched_at, item.id), reverse=True)[0])

    def find_latest_url_fetch_snapshot(self, *, normalized_request_url: str) -> URLFetchSnapshotRecord | None:
        snapshots = [
            snapshot for snapshot in self.url_fetch_snapshots.values()
            if snapshot.normalized_request_url == normalized_request_url
        ]
        if not snapshots:
            return None
        return copy.deepcopy(sorted(snapshots, key=lambda item: (item.fetched_at, item.id), reverse=True)[0])

    def create_artifact_derivation(self, derivation: ArtifactDerivationRecord) -> ArtifactDerivationRecord:
        self.artifact_derivations[derivation.child_artifact_id] = copy.deepcopy(derivation)
        return copy.deepcopy(derivation)

    def get_artifact_derivation_for_child(self, *, child_artifact_id: str) -> ArtifactDerivationRecord | None:
        derivation = self.artifact_derivations.get(child_artifact_id)
        return copy.deepcopy(derivation) if derivation else None

    def get_artifact_derivations_for_parent(self, *, parent_artifact_id: str) -> list[ArtifactDerivationRecord]:
        return sorted(
            [copy.deepcopy(item) for item in self.artifact_derivations.values() if item.parent_artifact_id == parent_artifact_id],
            key=lambda item: (item.created_at, item.id),
        )

    def create_completed_artifact_inspection(
        self,
        *,
        inspection: ArtifactInspectionRecord,
        findings: list[ArtifactInspectionFindingRecord],
        child_artifact: SourceArtifactRecord | None,
        derivation: ArtifactDerivationRecord | None,
        final_job_status: str,
        updated_at: str,
    ) -> ArtifactInspectionRecord:
        job = self.get_job(trip_id=inspection.trip_id, import_job_id=inspection.import_job_id)
        if job.artifact_id != inspection.artifact_id or job.status != "inspecting":
            raise TripError("import_artifact_not_ready", "Artifact inspection cannot be completed from the current job state.", 409)
        if child_artifact is not None:
            self.artifacts[child_artifact.id] = copy.deepcopy(child_artifact)
        self.artifact_inspections[inspection.id] = copy.deepcopy(inspection)
        for item in findings:
            self.artifact_inspection_findings[item.id] = copy.deepcopy(item)
        if derivation is not None:
            self.artifact_derivations[derivation.child_artifact_id] = copy.deepcopy(derivation)
        self.jobs[job.id] = replace(
            job,
            status=final_job_status,
            updated_at=updated_at,
            warning_codes=list(inspection.warning_codes),
            error_code=inspection.error_code,
        )
        return copy.deepcopy(inspection)

    def get_latest_artifact_inspection_for_job(self, *, trip_id: str, import_job_id: str) -> ArtifactInspectionRecord | None:
        inspections = [
            item for item in self.artifact_inspections.values()
            if item.trip_id == trip_id and item.import_job_id == import_job_id
        ]
        if not inspections:
            return None
        return copy.deepcopy(sorted(inspections, key=lambda item: (item.completed_at, item.attempt, item.id), reverse=True)[0])

    def list_artifact_inspection_findings(self, *, inspection_id: str) -> list[ArtifactInspectionFindingRecord]:
        return sorted(
            [copy.deepcopy(item) for item in self.artifact_inspection_findings.values() if item.inspection_id == inspection_id],
            key=lambda item: (item.created_at, item.id),
        )

    def get_latest_document_extraction_for_source(
        self,
        *,
        trip_id: str,
        source_import_job_id: str,
    ) -> DocumentExtractionGenerationRecord | None:
        generations = [
            item for item in self.document_extractions.values()
            if item.trip_id == trip_id and item.source_import_job_id == source_import_job_id
        ]
        if not generations:
            return None
        return copy.deepcopy(sorted(generations, key=lambda item: (item.generation, item.created_at, item.id), reverse=True)[0])

    def get_document_extraction_for_derived_job(
        self,
        *,
        derived_import_job_id: str,
    ) -> DocumentExtractionGenerationRecord | None:
        generation = next(
            (item for item in self.document_extractions.values() if item.derived_import_job_id == derived_import_job_id),
            None,
        )
        return copy.deepcopy(generation) if generation else None

    def list_document_text_spans(self, *, generation_id: str) -> list[DocumentTextSpanRecord]:
        return sorted(
            [copy.deepcopy(item) for item in self.document_text_spans.values() if item.generation_id == generation_id],
            key=lambda item: (item.page_number, item.block_index, item.line_index, item.token_index or -1, item.span_start, item.id),
        )

    def create_document_extraction_result(
        self,
        *,
        generation: DocumentExtractionGenerationRecord,
        spans: list[DocumentTextSpanRecord],
        child_artifact: SourceArtifactRecord,
        derivation: ArtifactDerivationRecord,
        derived_job: ImportJobRecord,
        related_artifacts: list[SourceArtifactRecord] | None = None,
        related_derivations: list[ArtifactDerivationRecord] | None = None,
    ) -> DocumentExtractionGenerationRecord:
        self.get_job(trip_id=generation.trip_id, import_job_id=generation.source_import_job_id)
        self.artifacts[child_artifact.id] = copy.deepcopy(child_artifact)
        for related_artifact in related_artifacts or []:
            self.artifacts[related_artifact.id] = copy.deepcopy(related_artifact)
        self.jobs[derived_job.id] = copy.deepcopy(derived_job)
        self.artifact_derivations[derivation.child_artifact_id] = copy.deepcopy(derivation)
        for related_derivation in related_derivations or []:
            self.artifact_derivations[related_derivation.child_artifact_id] = copy.deepcopy(related_derivation)
        self.document_extractions[generation.id] = copy.deepcopy(generation)
        for span in spans:
            self.document_text_spans[span.id] = copy.deepcopy(span)
        return copy.deepcopy(generation)

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


def row_to_url_fetch_snapshot(row) -> URLFetchSnapshotRecord:
    return URLFetchSnapshotRecord(
        id=row["id"],
        import_job_id=row["import_job_id"],
        raw_artifact_id=row["raw_artifact_id"],
        request_url_sanitized=row["request_url_sanitized"],
        normalized_request_url=row["normalized_request_url"],
        final_url_sanitized=row["final_url_sanitized"],
        final_url=row["final_url"],
        redirect_chain=list(json_loads(row["redirect_chain_json"], [])),
        robots_status=row["robots_status"],
        robots_checked_at=row["robots_checked_at"],
        status_code=row["status_code"],
        content_type=row["content_type"],
        declared_charset=row["declared_charset"],
        effective_charset=row["effective_charset"],
        content_language=row["content_language"],
        compressed_bytes=row["compressed_bytes"],
        decoded_bytes=row["decoded_bytes"],
        body_checksum=row["body_checksum"],
        header_metadata=dict(json_loads(row["header_metadata_json"], {})),
        fetcher_version=row["fetcher_version"],
        policy_version=row["policy_version"],
        fetched_at=row["fetched_at"],
        warning_codes=list(json_loads(row["warning_codes_json"], [])),
        cache_status=row["cache_status"],
    )


def row_to_artifact_derivation(row) -> ArtifactDerivationRecord:
    return ArtifactDerivationRecord(
        id=row["id"],
        parent_artifact_id=row["parent_artifact_id"],
        child_artifact_id=row["child_artifact_id"],
        derivation_type=row["derivation_type"],
        transformer_version=row["transformer_version"],
        input_checksum=row["input_checksum"],
        output_checksum=row["output_checksum"],
        metadata=dict(json_loads(row["metadata_json"], {})),
        created_at=row["created_at"],
    )


def row_to_artifact_inspection(row) -> ArtifactInspectionRecord:
    return ArtifactInspectionRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        import_job_id=row["import_job_id"],
        artifact_id=row["artifact_id"],
        attempt=row["attempt"],
        schema_version=row["schema_version"],
        inspector_version=row["inspector_version"],
        declared_kind=row["declared_kind"],
        detected_kind=row["detected_kind"],
        declared_mime_type=row["declared_mime_type"],
        detected_mime_type=row["detected_mime_type"],
        status=row["status"],
        classification=row["classification"],
        byte_size=row["byte_size"],
        content_checksum=row["content_checksum"],
        metadata=dict(json_loads(row["metadata_json"], {})),
        sanitized_artifact_id=row["sanitized_artifact_id"],
        manifest_artifact_id=row["manifest_artifact_id"],
        warning_codes=list(json_loads(row["warning_codes_json"], [])),
        error_code=row["error_code"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def row_to_artifact_inspection_finding(row) -> ArtifactInspectionFindingRecord:
    return ArtifactInspectionFindingRecord(
        id=row["id"],
        inspection_id=row["inspection_id"],
        code=row["code"],
        severity=row["severity"],
        category=row["category"],
        evidence=dict(json_loads(row["evidence_json"], {})),
        created_at=row["created_at"],
    )


def row_to_document_extraction_generation(row) -> DocumentExtractionGenerationRecord:
    return DocumentExtractionGenerationRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        source_import_job_id=row["source_import_job_id"],
        source_artifact_id=row["source_artifact_id"],
        inspection_id=row["inspection_id"],
        derived_import_job_id=row["derived_import_job_id"],
        derived_artifact_id=row["derived_artifact_id"],
        layout_artifact_id=row["layout_artifact_id"],
        span_map_artifact_id=row["span_map_artifact_id"],
        generation=row["generation"],
        schema_version=row["schema_version"],
        extractor_version=row["extractor_version"],
        strategy=row["strategy"],
        status=row["status"],
        page_count=row["page_count"],
        extracted_text_chars=row["extracted_text_chars"],
        warning_codes=list(json_loads(row["warning_codes_json"], [])),
        error_code=row["error_code"],
        metadata=dict(json_loads(row["metadata_json"], {})),
        created_at=row["created_at"],
    )


def row_to_document_text_span(row) -> DocumentTextSpanRecord:
    return DocumentTextSpanRecord(
        id=row["id"],
        generation_id=row["generation_id"],
        span_start=row["span_start"],
        span_end=row["span_end"],
        page_number=row["page_number"],
        block_index=row["block_index"],
        line_index=row["line_index"],
        token_index=row["token_index"],
        block_id=row["block_id"],
        line_id=row["line_id"],
        token_id=row["token_id"],
        reading_order=row["reading_order"],
        bbox=dict(json_loads(row["bbox_json"], {})),
        source_kind=row["source_kind"],
        confidence=row["confidence"],
        text_digest=row["text_digest"],
        warning_codes=list(json_loads(row["warning_codes_json"], [])),
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
