from __future__ import annotations

import hashlib
import json
import tempfile
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.imports.artifacts import ArtifactStore, make_storage_key
from app.imports.binary_detection import detect_binary_file
from app.imports.binary_upload import delete_staged_file, stream_upload_to_staging
from app.imports.document_extraction import DocumentTextExtractor, FetchedDocument
from app.imports.domain import (
    ARTIFACT_INSPECTION_SCHEMA_VERSION,
    ARTIFACT_INSPECTOR_VERSION,
    DOCUMENT_EXTRACTION_SCHEMA_VERSION,
    DOCUMENT_EXTRACTOR_VERSION,
    DOCUMENT_TEXT_TRANSFORMER_VERSION,
    IMAGE_SANITIZER_VERSION,
    ArtifactDerivationRecord,
    ArtifactDerivationResponse,
    ArtifactInspectionFindingRecord,
    ArtifactInspectionFindingResponse,
    ArtifactInspectionRecord,
    ArtifactInspectionResponse,
    BinaryImportCreateResponse,
    DocumentExtractionCreateResponse,
    DocumentExtractionGenerationRecord,
    DocumentExtractionGenerationResponse,
    DocumentTextSpanRecord,
    DocumentTextSpanResponse,
    IMPORT_EXTRACTION_SCHEMA_VERSION,
    IMPORT_EXTRACTOR_VERSION,
    IMPORT_RESOLVER_VERSION,
    MAX_CONTEXT_CHARS,
    PDF_MANIFEST_TRANSFORMER_VERSION,
    URL_DOCUMENT_TEXT_TRANSFORMER_VERSION,
    URL_IMPORT_FETCHER_VERSION,
    URL_IMPORT_POLICY_VERSION,
    ExtractedMentionRecord,
    ExtractedMentionResponse,
    ImportCommitRecord,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportJobRecord,
    ImportJobResponse,
    ImportJobStatus,
    ImportProcessingAttemptRecord,
    ImportReviewDecisionRecord,
    ImportReviewDecisionRequest,
    ImportReviewDecisionResponse,
    ImportReviewResponse,
    MentionEntityType,
    ResolutionDataState,
    ResolvedPlaceCandidateRecord,
    ResolvedPlaceCandidateResponse,
    ReviewAction,
    SourceArtifactRecord,
    SourceArtifactResponse,
    TextImportCreateRequest,
    TextImportCreateResponse,
    URLFetchSnapshotRecord,
    URLFetchSnapshotResponse,
    URLImportCreateRequest,
    URLImportCreateResponse,
    generate_artifact_id,
    generate_artifact_derivation_id,
    generate_artifact_inspection_finding_id,
    generate_artifact_inspection_id,
    generate_document_extraction_generation_id,
    generate_document_text_span_id,
    generate_import_attempt_id,
    generate_import_commit_id,
    generate_import_job_id,
    generate_mention_id,
    generate_review_decision_id,
    generate_url_fetch_snapshot_id,
    mention_content_digest,
    normalize_mention_text,
    source_checksum,
)
from app.imports.extraction import TextImportExtractor
from app.imports.document_extraction_runner import DocumentExtractionRunner, WorkerDocumentExtractionResult, WorkerDocumentSpan
from app.imports.inspection_runner import ArtifactInspectionRunner, WorkerInspectionResult
from app.imports.repository import ImportRepository
from app.imports.resolution import PlaceMentionResolver
from app.imports.url_fetcher import SecureURLFetcher
from app.trips.access import hash_capability, hash_idempotency_key
from app.trips.candidates import (
    CandidateCoordinate,
    CandidateSourceKind,
    CandidateType,
    TripCandidateCreateRequest,
)
from app.trips.digests import request_digest, sha256_digest
from app.trips.errors import IdempotencyConflictError, InvalidRevisionOperationError, TripError
from app.trips.repository import TripRepository
from app.trips.service import TripPersistenceService
from app.services.itinerary_completion_recommendation import CITY_CANDIDATES, normalize_city_name


class TextImportService:
    def __init__(
        self,
        *,
        import_repository: ImportRepository,
        trip_repository: TripRepository,
        trip_service: TripPersistenceService,
        artifact_store: ArtifactStore,
        extractor: TextImportExtractor,
        resolver: PlaceMentionResolver,
        url_fetcher: SecureURLFetcher | None = None,
        document_extractor: DocumentTextExtractor | None = None,
        clock=datetime.now,
    ) -> None:
        self.import_repository = import_repository
        self.trip_repository = trip_repository
        self.trip_service = trip_service
        self.artifact_store = artifact_store
        self.extractor = extractor
        self.resolver = resolver
        self.url_fetcher = url_fetcher
        self.document_extractor = document_extractor
        self.clock = clock

    def create_text_import(
        self,
        *,
        trip_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: TextImportCreateRequest,
    ) -> TextImportCreateResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        self._require_trip_access(trip_id, capability)
        content = validate_text_payload(payload.text)
        content_bytes = content.encode("utf-8")
        checksum = source_checksum(content_bytes)
        req_digest = request_digest(
            {
                "operation": "create_text_import",
                "trip_id": trip_id,
                "checksum": checksum,
                "byte_size": len(content_bytes),
                "original_label": payload.original_label,
            }
        )
        key_hash = hash_idempotency_key(idempotency_key.strip())
        idempotent_job = self.import_repository.get_idempotent_job(
            trip_id=trip_id,
            scope="create_text_import",
            request_digest=req_digest,
            idempotency_key_hash=key_hash,
        )
        if idempotent_job is not None:
            artifact = self.import_repository.get_artifact(
                trip_id=trip_id,
                artifact_id=idempotent_job.artifact_id,
            )
            return TextImportCreateResponse(
                artifact=artifact_to_response(artifact),
                job=job_to_response(idempotent_job),
                mentions=self._mention_responses(idempotent_job),
                duplicate_artifact=True,
                idempotent_replay=True,
            )

        now = format_utc(self.clock(timezone.utc))
        artifact, duplicate_artifact = self._get_or_create_artifact(
            trip_id=trip_id,
            content_bytes=content_bytes,
            checksum=checksum,
            original_label=payload.original_label,
            now=now,
        )
        existing_job = self.import_repository.find_latest_job_for_artifact(
            trip_id=trip_id,
            artifact_id=artifact.id,
        )
        if existing_job is not None and existing_job.status in {
            ImportJobStatus.REVIEW_READY.value,
            ImportJobStatus.PARTIAL.value,
            ImportJobStatus.COMMITTED.value,
        }:
            self.import_repository.remember_idempotent_job(
                trip_id=trip_id,
                scope="create_text_import",
                request_digest=req_digest,
                idempotency_key_hash=key_hash,
                job_id=existing_job.id,
                created_at=now,
            )
            return TextImportCreateResponse(
                artifact=artifact_to_response(artifact),
                job=job_to_response(existing_job),
                mentions=self._mention_responses(existing_job),
                duplicate_artifact=True,
            )

        job = self.import_repository.create_job(
            ImportJobRecord(
                id=generate_import_job_id(),
                trip_id=trip_id,
                artifact_id=artifact.id,
                input_type="text",
                status=ImportJobStatus.CREATED.value,
                extraction_schema_version=IMPORT_EXTRACTION_SCHEMA_VERSION,
                extractor_version=IMPORT_EXTRACTOR_VERSION,
                resolver_version=IMPORT_RESOLVER_VERSION,
                review_version=0,
                mention_count=0,
                warning_codes=[],
                error_code=None,
                committed_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        self.import_repository.remember_idempotent_job(
            trip_id=trip_id,
            scope="create_text_import",
            request_digest=req_digest,
            idempotency_key_hash=key_hash,
            job_id=job.id,
            created_at=now,
        )
        processed = self._process_inline(job=job, source_text=content)
        return TextImportCreateResponse(
            artifact=artifact_to_response(artifact),
            job=job_to_response(processed),
            mentions=self._mention_responses(processed),
            duplicate_artifact=duplicate_artifact,
        )

    def create_url_import(
        self,
        *,
        trip_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: URLImportCreateRequest,
    ) -> URLImportCreateResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        if self.url_fetcher is None or self.document_extractor is None:
            raise TripError("import_url_disabled", "URL import is not configured.", 503)
        if not get_import_url_enabled_inline():
            raise TripError("import_url_disabled", "URL import is disabled.", 503)
        self._require_trip_access(trip_id, capability)
        normalized = self.url_fetcher.policy.normalize_url(payload.url)
        req_digest = request_digest(
            {
                "operation": "create_url_import",
                "trip_id": trip_id,
                "normalized_url": normalized.normalized_url,
                "refresh": payload.refresh,
            }
        )
        key_hash = hash_idempotency_key(idempotency_key.strip())
        idempotent_job = self.import_repository.get_idempotent_job(
            trip_id=trip_id,
            scope="create_url_import",
            request_digest=req_digest,
            idempotency_key_hash=key_hash,
        )
        if idempotent_job is not None:
            artifact = self.import_repository.get_artifact(trip_id=trip_id, artifact_id=idempotent_job.artifact_id)
            return URLImportCreateResponse(
                artifact=artifact_to_response(artifact),
                job=job_to_response(idempotent_job),
                mentions=self._mention_responses(idempotent_job),
                duplicate_artifact=True,
                idempotent_replay=True,
                source_fetch=snapshot_to_response(self.import_repository.get_url_fetch_snapshot_for_job(import_job_id=idempotent_job.id)),
                derivation=derivation_to_response(self.import_repository.get_artifact_derivation_for_child(child_artifact_id=artifact.id)),
            )

        fetched = self.url_fetcher.fetch(normalized.normalized_url)
        now = format_utc(self.clock(timezone.utc))
        raw_artifact, raw_duplicate = self._get_or_create_artifact(
            trip_id=trip_id,
            content_bytes=fetched.body,
            checksum=fetched.body_checksum,
            original_label=fetched.final_url_sanitized,
            now=now,
            artifact_type="url_document",
            mime_type=fetched.content_type,
            charset=fetched.declared_charset or "binary",
            storage_type="url-document",
            extension=extension_for_content_type(fetched.content_type),
        )
        text_result = self.document_extractor.extract(
            FetchedDocument(
                content=fetched.body,
                content_type=fetched.content_type,
                declared_charset=fetched.declared_charset,
                max_text_bytes=get_import_url_max_text_bytes_inline(),
            )
        )
        derived_bytes = text_result.normalized_text.encode("utf-8")
        derived_artifact, derived_duplicate = self._get_or_create_artifact(
            trip_id=trip_id,
            content_bytes=derived_bytes,
            checksum=source_checksum(derived_bytes),
            original_label=text_result.title or fetched.final_url_sanitized,
            now=now,
            artifact_type="derived_text",
            mime_type="text/plain",
            charset="utf-8",
            storage_type="derived-text",
            extension="txt",
        )
        existing_job = self.import_repository.find_latest_job_for_artifact(
            trip_id=trip_id,
            artifact_id=derived_artifact.id,
        )
        if existing_job is not None and existing_job.input_type == "url" and existing_job.status in {
            ImportJobStatus.REVIEW_READY.value,
            ImportJobStatus.PARTIAL.value,
            ImportJobStatus.COMMITTED.value,
        }:
            self.import_repository.remember_idempotent_job(
                trip_id=trip_id,
                scope="create_url_import",
                request_digest=req_digest,
                idempotency_key_hash=key_hash,
                job_id=existing_job.id,
                created_at=now,
            )
            return URLImportCreateResponse(
                artifact=artifact_to_response(derived_artifact),
                job=job_to_response(existing_job),
                mentions=self._mention_responses(existing_job),
                duplicate_artifact=True,
                source_fetch=snapshot_to_response(self.import_repository.get_url_fetch_snapshot_for_job(import_job_id=existing_job.id)),
                derivation=derivation_to_response(self.import_repository.get_artifact_derivation_for_child(child_artifact_id=derived_artifact.id)),
            )

        job = self.import_repository.create_job(
            ImportJobRecord(
                id=generate_import_job_id(),
                trip_id=trip_id,
                artifact_id=derived_artifact.id,
                input_type="url",
                status=ImportJobStatus.CREATED.value,
                extraction_schema_version=IMPORT_EXTRACTION_SCHEMA_VERSION,
                extractor_version=IMPORT_EXTRACTOR_VERSION,
                resolver_version=IMPORT_RESOLVER_VERSION,
                review_version=0,
                mention_count=0,
                warning_codes=[],
                error_code=None,
                committed_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        self.import_repository.remember_idempotent_job(
            trip_id=trip_id,
            scope="create_url_import",
            request_digest=req_digest,
            idempotency_key_hash=key_hash,
            job_id=job.id,
            created_at=now,
        )
        fetching_attempt = self._start_attempt(job.id, stage="fetch", extractor_version=None, resolver_version=None)
        fetching = self.import_repository.update_job(
            trip_id=trip_id,
            import_job_id=job.id,
            status=ImportJobStatus.FETCHING.value,
            updated_at=now,
        )
        self._complete_attempt(fetching_attempt.id, job.id, warning_codes=[], error_code=None)
        snapshot = self.import_repository.create_url_fetch_snapshot(
            URLFetchSnapshotRecord(
                id=generate_url_fetch_snapshot_id(),
                import_job_id=job.id,
                raw_artifact_id=raw_artifact.id,
                request_url_sanitized=fetched.request_url_sanitized,
                normalized_request_url=fetched.normalized_request_url,
                final_url_sanitized=fetched.final_url_sanitized,
                final_url=fetched.final_url,
                redirect_chain=[asdict(hop) for hop in fetched.redirect_chain],
                robots_status=fetched.robots_status,
                robots_checked_at=now,
                status_code=fetched.status_code,
                content_type=fetched.content_type,
                declared_charset=fetched.declared_charset,
                effective_charset=text_result.effective_charset,
                content_language=fetched.content_language,
                compressed_bytes=fetched.compressed_bytes,
                decoded_bytes=fetched.decoded_bytes,
                body_checksum=fetched.body_checksum,
                header_metadata={
                    **fetched.header_metadata,
                    "page_title": text_result.title or "",
                    "language_hint": text_result.language_hint or "",
                    "source_host": normalized.host,
                    "final_host": self.url_fetcher.policy.normalize_url(fetched.final_url).host,
                    "environment_proxy_disabled": str(self.url_fetcher.transport.environment_proxy_disabled).lower(),
                    "tls_verification_preserved": str(self.url_fetcher.transport.tls_verification_preserved).lower(),
                },
                fetcher_version=URL_IMPORT_FETCHER_VERSION,
                policy_version=URL_IMPORT_POLICY_VERSION,
                fetched_at=now,
                warning_codes=unique(fetched.warning_codes + text_result.warning_codes),
                cache_status="artifact_reused" if raw_duplicate or derived_duplicate else "fetched",
            )
        )
        content_attempt = self._start_attempt(job.id, stage="content_extraction", extractor_version=URL_DOCUMENT_TEXT_TRANSFORMER_VERSION, resolver_version=None)
        content_stage = self.import_repository.update_job(
            trip_id=trip_id,
            import_job_id=fetching.id,
            status=ImportJobStatus.EXTRACTING_CONTENT.value,
            updated_at=now,
            warning_codes=snapshot.warning_codes,
        )
        derivation = self.import_repository.create_artifact_derivation(
            ArtifactDerivationRecord(
                id=generate_artifact_derivation_id(),
                parent_artifact_id=raw_artifact.id,
                child_artifact_id=derived_artifact.id,
                derivation_type=text_result.derivation_type,
                transformer_version=text_result.transformer_version,
                input_checksum=raw_artifact.content_checksum,
                output_checksum=derived_artifact.content_checksum,
                metadata={
                    "title": text_result.title,
                    "language_hint": text_result.language_hint,
                    "declared_canonical_url": text_result.declared_canonical_url,
                    "metrics": {
                        "raw_bytes": text_result.extraction_metrics.raw_bytes,
                        "text_bytes": text_result.extraction_metrics.text_bytes,
                        "script_bytes": text_result.extraction_metrics.script_bytes,
                        "visible_text_chars": text_result.extraction_metrics.visible_text_chars,
                    },
                },
                created_at=now,
            )
        )
        self._complete_attempt(content_attempt.id, job.id, warning_codes=text_result.warning_codes, error_code=None)
        processed = self._process_inline(job=content_stage, source_text=text_result.normalized_text)
        return URLImportCreateResponse(
            artifact=artifact_to_response(derived_artifact),
            job=job_to_response(processed),
            mentions=self._mention_responses(processed),
            duplicate_artifact=raw_duplicate or derived_duplicate,
            source_fetch=snapshot_to_response(snapshot),
            derivation=derivation_to_response(derivation),
        )

    async def create_binary_import(
        self,
        *,
        trip_id: str,
        capability: str | None,
        idempotency_key: str | None,
        upload_file: UploadFile,
        declared_kind: str,
        original_label: str | None,
    ) -> BinaryImportCreateResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        if not get_import_binary_enabled_inline():
            raise TripError("import_binary_type_unsupported", "Binary artifact import is disabled.", 503)
        self._require_trip_access(trip_id, capability)
        max_stream_bytes = max(get_import_binary_max_image_bytes_inline(), get_import_binary_max_pdf_bytes_inline())
        staging_root = Path(get_import_binary_staging_root_inline()) / trip_id / generate_import_attempt_id()
        staged = await stream_upload_to_staging(
            upload_file=upload_file,
            staging_root=staging_root,
            max_bytes=max_stream_bytes,
            chunk_bytes=get_import_binary_upload_chunk_bytes_inline(),
            original_label=original_label,
        )
        try:
            detection = detect_binary_file(
                path=staged.path,
                declared_kind=declared_kind,
                content_type=upload_file.content_type,
                original_label=original_label or upload_file.filename,
            )
            if detection.detected_kind == "image" and staged.byte_size > get_import_binary_max_image_bytes_inline():
                raise TripError("import_binary_too_large", "Image artifact exceeds the configured byte limit.", 413)
            if detection.detected_kind == "pdf" and staged.byte_size > get_import_binary_max_pdf_bytes_inline():
                raise TripError("import_binary_too_large", "PDF artifact exceeds the configured byte limit.", 413)
            req_digest = request_digest(
                {
                    "operation": "create_binary_import",
                    "trip_id": trip_id,
                    "checksum": staged.checksum,
                    "byte_size": staged.byte_size,
                    "declared_kind": detection.declared_kind,
                }
            )
            key_hash = hash_idempotency_key(idempotency_key.strip())
            idempotent_job = self.import_repository.get_idempotent_job(
                trip_id=trip_id,
                scope="create_binary_import",
                request_digest=req_digest,
                idempotency_key_hash=key_hash,
            )
            if idempotent_job is not None:
                artifact = self.import_repository.get_artifact(trip_id=trip_id, artifact_id=idempotent_job.artifact_id)
                inspection = self._get_binary_inspection_or_raise(trip_id=trip_id, import_job_id=idempotent_job.id)
                return BinaryImportCreateResponse(
                    artifact=artifact_to_response(artifact),
                    job=job_to_response(idempotent_job),
                    inspection=self._inspection_response(inspection),
                    derivation=derivation_to_response(self._binary_derivation(inspection)),
                    duplicate_artifact=True,
                    idempotent_replay=True,
                )

            now = format_utc(self.clock(timezone.utc))
            artifact, duplicate_artifact = self._get_or_create_artifact_from_file(
                trip_id=trip_id,
                source_path=staged.path,
                checksum=staged.checksum,
                byte_size=staged.byte_size,
                original_label=staged.sanitized_label,
                now=now,
                artifact_type="uploaded_image" if detection.detected_kind == "image" else "uploaded_pdf",
                mime_type=detection.detected_mime_type,
                storage_type="uploaded-image" if detection.detected_kind == "image" else "uploaded-pdf",
                extension=detection.extension,
            )
            existing_job = self.import_repository.find_latest_job_for_artifact(
                trip_id=trip_id,
                artifact_id=artifact.id,
            )
            if existing_job is not None and existing_job.input_type == detection.detected_kind and existing_job.status in {
                ImportJobStatus.ARTIFACT_READY.value,
                ImportJobStatus.NEEDS_PASSWORD.value,
                ImportJobStatus.REJECTED.value,
                ImportJobStatus.FAILED.value,
            }:
                self.import_repository.remember_idempotent_job(
                    trip_id=trip_id,
                    scope="create_binary_import",
                    request_digest=req_digest,
                    idempotency_key_hash=key_hash,
                    job_id=existing_job.id,
                    created_at=now,
                )
                inspection = self._get_binary_inspection_or_raise(trip_id=trip_id, import_job_id=existing_job.id)
                return BinaryImportCreateResponse(
                    artifact=artifact_to_response(artifact),
                    job=job_to_response(existing_job),
                    inspection=self._inspection_response(inspection),
                    derivation=derivation_to_response(self._binary_derivation(inspection)),
                    duplicate_artifact=True,
                )

            job = self.import_repository.create_job(
                ImportJobRecord(
                    id=generate_import_job_id(),
                    trip_id=trip_id,
                    artifact_id=artifact.id,
                    input_type=detection.detected_kind,
                    status=ImportJobStatus.CREATED.value,
                    extraction_schema_version=ARTIFACT_INSPECTION_SCHEMA_VERSION,
                    extractor_version=ARTIFACT_INSPECTOR_VERSION,
                    resolver_version="none",
                    review_version=0,
                    mention_count=0,
                    warning_codes=list(detection.warning_codes),
                    error_code=None,
                    committed_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            self.import_repository.remember_idempotent_job(
                trip_id=trip_id,
                scope="create_binary_import",
                request_digest=req_digest,
                idempotency_key_hash=key_hash,
                job_id=job.id,
                created_at=now,
            )
            receiving = self.import_repository.update_job(
                trip_id=trip_id,
                import_job_id=job.id,
                status=ImportJobStatus.RECEIVING.value,
                updated_at=now,
            )
            quarantined = self.import_repository.update_job(
                trip_id=trip_id,
                import_job_id=receiving.id,
                status=ImportJobStatus.QUARANTINED.value,
                updated_at=format_utc(self.clock(timezone.utc)),
            )
            inspecting = self.import_repository.update_job(
                trip_id=trip_id,
                import_job_id=quarantined.id,
                status=ImportJobStatus.INSPECTING.value,
                updated_at=format_utc(self.clock(timezone.utc)),
            )
            inspection, child_artifact, derivation = self._inspect_quarantined_artifact(
                job=inspecting,
                artifact=artifact,
                source_path=staged.path,
                detection=detection,
                declared_mime_type=upload_file.content_type,
            )
            final_job = self.import_repository.get_job(trip_id=trip_id, import_job_id=inspecting.id)
            return BinaryImportCreateResponse(
                artifact=artifact_to_response(artifact),
                job=job_to_response(final_job),
                inspection=self._inspection_response(inspection),
                derivation=derivation_to_response(derivation),
                duplicate_artifact=duplicate_artifact,
            )
        finally:
            delete_staged_file(staged.path)
            try:
                staging_root.rmdir()
            except OSError:
                pass

    def get_import(
        self,
        *,
        trip_id: str,
        import_job_id: str,
        capability: str | None,
    ) -> ImportReviewResponse:
        self._require_trip_access(trip_id, capability)
        job = self.import_repository.get_job(trip_id=trip_id, import_job_id=import_job_id)
        artifact = self.import_repository.get_artifact(trip_id=trip_id, artifact_id=job.artifact_id)
        if job.input_type in {"image", "pdf"}:
            inspection = self.import_repository.get_latest_artifact_inspection_for_job(
                trip_id=trip_id,
                import_job_id=job.id,
            )
            if inspection is not None:
                return ImportReviewResponse(
                    artifact=artifact_to_response(artifact),
                    job=job_to_response(job),
                    mentions=[],
                    source_fetch=None,
                    derivation=derivation_to_response(self._binary_derivation(inspection)),
                )
        return ImportReviewResponse(
            artifact=artifact_to_response(artifact),
            job=job_to_response(job),
            mentions=self._mention_responses(job),
            source_fetch=snapshot_to_response(self.import_repository.get_url_fetch_snapshot_for_job(import_job_id=job.id)),
            derivation=derivation_to_response(self.import_repository.get_artifact_derivation_for_child(child_artifact_id=artifact.id)),
        )

    def get_artifact_text(
        self,
        *,
        trip_id: str,
        import_job_id: str,
        capability: str | None,
    ) -> str:
        self._require_trip_access(trip_id, capability)
        job = self.import_repository.get_job(trip_id=trip_id, import_job_id=import_job_id)
        if job.input_type in {"image", "pdf"}:
            raise TripError("import_artifact_original_not_inlineable", "Original binary artifacts are not inlineable.", 409)
        artifact = self.import_repository.get_artifact(trip_id=trip_id, artifact_id=job.artifact_id)
        try:
            return self.artifact_store.get(storage_key=artifact.storage_key).decode("utf-8")
        except (FileNotFoundError, UnicodeDecodeError) as exc:
            raise TripError("import_artifact_not_found", "Import artifact text was not found.", 404) from exc

    def get_binary_inspection(
        self,
        *,
        trip_id: str,
        import_job_id: str,
        capability: str | None,
    ) -> ArtifactInspectionResponse:
        self._require_trip_access(trip_id, capability)
        return self._inspection_response(self._get_binary_inspection_or_raise(trip_id=trip_id, import_job_id=import_job_id))

    def get_sanitized_image_bytes(
        self,
        *,
        trip_id: str,
        import_job_id: str,
        capability: str | None,
    ) -> tuple[bytes, str]:
        self._require_trip_access(trip_id, capability)
        inspection = self._get_binary_inspection_or_raise(trip_id=trip_id, import_job_id=import_job_id)
        if inspection.status != ImportJobStatus.ARTIFACT_READY.value or not inspection.sanitized_artifact_id:
            raise TripError("import_artifact_not_ready", "Sanitized image artifact is not ready.", 409)
        artifact = self.import_repository.get_artifact(trip_id=trip_id, artifact_id=inspection.sanitized_artifact_id)
        try:
            return self.artifact_store.get(storage_key=artifact.storage_key), artifact.mime_type
        except FileNotFoundError as exc:
            raise TripError("import_artifact_not_found", "Sanitized image artifact was not found.", 404) from exc

    def extract_document_import(
        self,
        *,
        trip_id: str,
        import_job_id: str,
        capability: str | None,
        idempotency_key: str | None,
    ) -> DocumentExtractionCreateResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        if not get_import_document_extraction_enabled_inline():
            raise TripError("import_document_extraction_disabled", "Document extraction is disabled.", 503)
        self._require_trip_access(trip_id, capability)
        source_job = self.import_repository.get_job(trip_id=trip_id, import_job_id=import_job_id)
        if source_job.input_type not in {"image", "pdf"}:
            raise TripError("import_document_source_not_binary", "Only inspected image/PDF artifacts can be extracted.", 409)
        inspection = self._get_binary_inspection_or_raise(trip_id=trip_id, import_job_id=import_job_id)
        if inspection.status != ImportJobStatus.ARTIFACT_READY.value:
            raise TripError("import_document_source_not_ready", "Document extraction requires an artifact_ready binary inspection.", 409)
        source_artifact = self.import_repository.get_artifact(trip_id=trip_id, artifact_id=source_job.artifact_id)
        readable_artifact = source_artifact
        if inspection.detected_kind == "image":
            if not inspection.sanitized_artifact_id:
                raise TripError("import_document_source_not_ready", "Image extraction requires a sanitized image derivative.", 409)
            readable_artifact = self.import_repository.get_artifact(trip_id=trip_id, artifact_id=inspection.sanitized_artifact_id)
        req_digest = request_digest(
            {
                "operation": "extract_document_import",
                "trip_id": trip_id,
                "source_import_job_id": source_job.id,
                "source_artifact_id": source_artifact.id,
                "source_checksum": source_artifact.content_checksum,
                "inspection_id": inspection.id,
                "extractor_version": DOCUMENT_EXTRACTOR_VERSION,
            }
        )
        key_hash = hash_idempotency_key(idempotency_key.strip())
        idempotent_job = self.import_repository.get_idempotent_job(
            trip_id=trip_id,
            scope="extract_document_import",
            request_digest=req_digest,
            idempotency_key_hash=key_hash,
        )
        if idempotent_job is not None:
            generation = self.import_repository.get_document_extraction_for_derived_job(derived_import_job_id=idempotent_job.id)
            artifact = self.import_repository.get_artifact(trip_id=trip_id, artifact_id=idempotent_job.artifact_id)
            return DocumentExtractionCreateResponse(
                generation=generation_to_response(generation) if generation else empty_generation_response(trip_id=trip_id, source_job=source_job, inspection=inspection),
                artifact=artifact_to_response(artifact),
                job=job_to_response(idempotent_job),
                mentions=self._mention_responses(idempotent_job),
                derivation=derivation_to_response(self.import_repository.get_artifact_derivation_for_child(child_artifact_id=artifact.id)),
                spans=self._span_responses(generation.id) if generation else [],
                duplicate_artifact=True,
                idempotent_replay=True,
            )
        existing_generation = self.import_repository.get_latest_document_extraction_for_source(
            trip_id=trip_id,
            source_import_job_id=source_job.id,
        )
        if existing_generation is not None and existing_generation.derived_import_job_id:
            existing_job = self.import_repository.get_job(
                trip_id=trip_id,
                import_job_id=existing_generation.derived_import_job_id,
            )
            self.import_repository.remember_idempotent_job(
                trip_id=trip_id,
                scope="extract_document_import",
                request_digest=req_digest,
                idempotency_key_hash=key_hash,
                job_id=existing_job.id,
                created_at=format_utc(self.clock(timezone.utc)),
            )
            artifact = self.import_repository.get_artifact(trip_id=trip_id, artifact_id=existing_job.artifact_id)
            return DocumentExtractionCreateResponse(
                generation=generation_to_response(existing_generation),
                artifact=artifact_to_response(artifact),
                job=job_to_response(existing_job),
                mentions=self._mention_responses(existing_job),
                derivation=derivation_to_response(self.import_repository.get_artifact_derivation_for_child(child_artifact_id=artifact.id)),
                spans=self._span_responses(existing_generation.id),
                duplicate_artifact=True,
            )

        try:
            source_bytes = self.artifact_store.get(storage_key=readable_artifact.storage_key)
        except FileNotFoundError as exc:
            raise TripError("import_artifact_not_found", "Readable document artifact was not found.", 404) from exc
        with tempfile.TemporaryDirectory() as temp_dir:
            suffix = ".pdf" if inspection.detected_kind == "pdf" else ".img"
            source_path = Path(temp_dir) / f"document-source{suffix}"
            source_path.write_bytes(source_bytes)
            runner = DocumentExtractionRunner(
                timeout_seconds=get_import_document_extraction_timeout_seconds_inline(),
                max_memory_mb=get_import_document_extraction_max_memory_mb_inline(),
                max_output_bytes=get_import_document_extraction_max_output_bytes_inline(),
            )
            try:
                extraction = runner.extract(
                    path=source_path,
                    kind=inspection.detected_kind,
                    mime_type=readable_artifact.mime_type,
                    limits=document_extraction_limits(),
                )
            except TripError:
                raise
        if extraction.status == "failed" or not extraction.normalized_text.strip():
            raise TripError(
                extraction.error_code or "import_document_extraction_no_text",
                "Document extraction did not produce reviewable text.",
                422,
            )
        normalized = validate_document_extracted_text(extraction.normalized_text)
        now = format_utc(self.clock(timezone.utc))
        derived_bytes = normalized.encode("utf-8")
        derived_artifact = self._stage_child_artifact_bytes(
            trip_id=trip_id,
            content_bytes=derived_bytes,
            checksum=source_checksum(derived_bytes),
            now=now,
            artifact_type="document_text",
            mime_type="text/plain",
            charset="utf-8",
            storage_type="document-text",
            extension="txt",
        )
        derived_job = ImportJobRecord(
            id=generate_import_job_id(),
            trip_id=trip_id,
            artifact_id=derived_artifact.id,
            input_type="document",
            status=ImportJobStatus.CREATED.value,
            extraction_schema_version=IMPORT_EXTRACTION_SCHEMA_VERSION,
            extractor_version=IMPORT_EXTRACTOR_VERSION,
            resolver_version=IMPORT_RESOLVER_VERSION,
            review_version=0,
            mention_count=0,
            warning_codes=list(extraction.warning_codes),
            error_code=None,
            committed_at=None,
            created_at=now,
            updated_at=now,
        )
        generation_id = generate_document_extraction_generation_id()
        generation = DocumentExtractionGenerationRecord(
            id=generation_id,
            trip_id=trip_id,
            source_import_job_id=source_job.id,
            source_artifact_id=source_artifact.id,
            inspection_id=inspection.id,
            derived_import_job_id=derived_job.id,
            derived_artifact_id=derived_artifact.id,
            generation=1,
            schema_version=extraction.schema_version,
            extractor_version=extraction.extractor_version,
            strategy=extraction.strategy,
            status=ImportJobStatus.PARTIAL.value if extraction.status == "partial" else ImportJobStatus.REVIEW_READY.value,
            page_count=extraction.page_count,
            extracted_text_chars=len(normalized),
            warning_codes=list(extraction.warning_codes),
            error_code=None,
            metadata=safe_document_extraction_metadata(extraction.metadata),
            created_at=now,
        )
        spans = [
            span_from_worker(generation_id=generation_id, span=span, source_text=normalized, created_at=now)
            for span in extraction.spans
            if span.span_end <= len(normalized) and normalized[span.span_start:span.span_end].strip()
        ]
        derivation = ArtifactDerivationRecord(
            id=generate_artifact_derivation_id(),
            parent_artifact_id=readable_artifact.id,
            child_artifact_id=derived_artifact.id,
            derivation_type="document_text_extraction",
            transformer_version=DOCUMENT_TEXT_TRANSFORMER_VERSION,
            input_checksum=readable_artifact.content_checksum,
            output_checksum=derived_artifact.content_checksum,
            metadata={
                "source_import_job_id": source_job.id,
                "source_artifact_id": source_artifact.id,
                "inspection_id": inspection.id,
                "strategy": extraction.strategy,
                "schema_version": extraction.schema_version,
                "page_count": extraction.page_count,
                "span_count": len(spans),
                "source_kind": inspection.detected_kind,
            },
            created_at=now,
        )
        try:
            self.import_repository.create_document_extraction_result(
                generation=generation,
                spans=spans,
                child_artifact=derived_artifact,
                derivation=derivation,
                derived_job=derived_job,
            )
        except Exception as exc:
            self.artifact_store.delete(storage_key=derived_artifact.storage_key)
            if isinstance(exc, TripError):
                raise
            raise TripError("import_document_extraction_persist_failed", "Document extraction result could not be persisted.", 500) from exc
        self.import_repository.remember_idempotent_job(
            trip_id=trip_id,
            scope="extract_document_import",
            request_digest=req_digest,
            idempotency_key_hash=key_hash,
            job_id=derived_job.id,
            created_at=now,
        )
        processed = self._process_inline(job=derived_job, source_text=normalized)
        persisted_generation = self.import_repository.get_document_extraction_for_derived_job(
            derived_import_job_id=processed.id,
        ) or generation
        return DocumentExtractionCreateResponse(
            generation=generation_to_response(persisted_generation),
            artifact=artifact_to_response(derived_artifact),
            job=job_to_response(processed),
            mentions=self._mention_responses(processed),
            derivation=derivation_to_response(derivation),
            spans=self._span_responses(persisted_generation.id),
            duplicate_artifact=False,
        )

    def _get_binary_inspection_or_raise(self, *, trip_id: str, import_job_id: str) -> ArtifactInspectionRecord:
        job = self.import_repository.get_job(trip_id=trip_id, import_job_id=import_job_id)
        if job.input_type not in {"image", "pdf"}:
            raise TripError("import_artifact_not_ready", "Import job is not a binary artifact job.", 409)
        inspection = self.import_repository.get_latest_artifact_inspection_for_job(
            trip_id=trip_id,
            import_job_id=import_job_id,
        )
        if inspection is None:
            raise TripError("import_artifact_not_ready", "Artifact inspection is not complete.", 409)
        return inspection

    def _binary_derivation(self, inspection: ArtifactInspectionRecord) -> ArtifactDerivationRecord | None:
        child_id = inspection.sanitized_artifact_id or inspection.manifest_artifact_id
        if child_id is None:
            return None
        return self.import_repository.get_artifact_derivation_for_child(child_artifact_id=child_id)

    def _inspection_response(self, inspection: ArtifactInspectionRecord) -> ArtifactInspectionResponse:
        findings = self.import_repository.list_artifact_inspection_findings(inspection_id=inspection.id)
        return inspection_to_response(inspection, findings=findings)

    def record_decision(
        self,
        *,
        trip_id: str,
        import_job_id: str,
        mention_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: ImportReviewDecisionRequest,
    ) -> ImportReviewResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        self._require_trip_access(trip_id, capability)
        job = self.import_repository.get_job(trip_id=trip_id, import_job_id=import_job_id)
        if job.status not in {ImportJobStatus.REVIEW_READY.value, ImportJobStatus.PARTIAL.value}:
            raise TripError("import_job_not_reviewable", "Import job is not reviewable.", 409)
        mention = self.import_repository.get_mention(import_job_id=import_job_id, mention_id=mention_id)
        self._validate_review_decision(job=job, mention=mention, payload=payload)
        req_digest = request_digest(
            {
                "operation": "import_review_decision",
                "import_job_id": import_job_id,
                "mention_id": mention_id,
                "payload": payload.model_dump(mode="json"),
            }
        )
        decision = ImportReviewDecisionRecord(
            id=generate_review_decision_id(),
            import_job_id=import_job_id,
            mention_id=mention_id,
            review_version=0,
            action=payload.action.value,
            selected_resolution_candidate_id=payload.selected_resolution_candidate_id,
            merge_target_mention_id=payload.merge_target_mention_id,
            note_text=payload.note_text,
            reason_code=payload.reason_code,
            created_at=format_utc(self.clock(timezone.utc)),
        )
        _stored, updated_job, _replay = self.import_repository.create_review_decision(
            decision=decision,
            base_review_version=payload.base_review_version,
            request_digest=req_digest,
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
        )
        artifact = self.import_repository.get_artifact(trip_id=trip_id, artifact_id=updated_job.artifact_id)
        return ImportReviewResponse(
            artifact=artifact_to_response(artifact),
            job=job_to_response(updated_job),
            mentions=self._mention_responses(updated_job),
            source_fetch=snapshot_to_response(self.import_repository.get_url_fetch_snapshot_for_job(import_job_id=updated_job.id)),
            derivation=derivation_to_response(self.import_repository.get_artifact_derivation_for_child(child_artifact_id=artifact.id)),
        )

    def commit_import(
        self,
        *,
        trip_id: str,
        import_job_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: ImportCommitRequest,
    ) -> ImportCommitResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        self._require_trip_access(trip_id, capability)
        job = self.import_repository.get_job(trip_id=trip_id, import_job_id=import_job_id)
        if job.review_version != payload.base_review_version:
            raise TripError("stale_import_review", "Import review is based on a stale version.", 409)
        decisions = self.import_repository.list_review_decisions(import_job_id=import_job_id)
        decisions_by_mention = latest_decision_by_mention(decisions)
        mentions = self.import_repository.list_mentions(import_job_id=import_job_id)
        resolutions_by_id = {
            candidate.id: candidate
            for candidate in self.import_repository.list_resolution_candidates(import_job_id=import_job_id)
        }
        confirmed_groups: dict[str, list[tuple[ExtractedMentionRecord, ResolvedPlaceCandidateRecord]]] = defaultdict(list)
        ignored = 0
        notes = 0
        constraints = 0
        unresolved = 0
        for mention in mentions:
            decision = decisions_by_mention.get(mention.id)
            if mention.entity_type in {MentionEntityType.FIXED_EVENT.value, MentionEntityType.TIME_CONSTRAINT.value}:
                constraints += 1
            if mention.entity_type == MentionEntityType.NOTE.value:
                notes += 1
            if decision is None:
                if mention.entity_type == MentionEntityType.PLACE.value:
                    unresolved += 1
                continue
            if decision.action in {ReviewAction.IGNORE.value, ReviewAction.MARK_AS_NOTE.value}:
                ignored += 1
                continue
            if decision.action == ReviewAction.MERGE.value:
                continue
            if decision.action not in {ReviewAction.CONFIRM.value, ReviewAction.SELECT_CANDIDATE.value}:
                continue
            if not decision.selected_resolution_candidate_id:
                unresolved += 1
                continue
            selected = resolutions_by_id.get(decision.selected_resolution_candidate_id)
            if selected is None:
                raise TripError("import_resolution_candidate_not_found", "Import resolution candidate was not found.", 404)
            if selected.data_state in {ResolutionDataState.MISSING.value, ResolutionDataState.PROVIDER_FAILED.value}:
                unresolved += 1
                continue
            group_key = selected.provider_place_id or selected.candidate_digest
            confirmed_groups[group_key].append((mention, selected))
        if not confirmed_groups:
            raise TripError("import_commit_has_no_confirmed_places", "No confirmed place mentions are available to commit.", 422)

        commit_digest = sha256_digest(
            {
                "import_job_id": import_job_id,
                "review_version": job.review_version,
                "confirmed": sorted(confirmed_groups),
            }
        )
        req_digest = request_digest(
            {
                "operation": "import_commit",
                "import_job_id": import_job_id,
                "review_version": job.review_version,
                "commit_digest": commit_digest,
            }
        )
        existing_commit = self.import_repository.get_idempotent_commit(
            trip_id=trip_id,
            scope="commit",
            request_digest=req_digest,
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
        )
        if existing_commit is not None:
            return commit_response_from_record(existing_commit, idempotent_replay=True)
        if job.status == ImportJobStatus.COMMITTED.value:
            existing_for_job = self.import_repository.get_commit_for_job(import_job_id=import_job_id)
            if existing_for_job is not None:
                return commit_response_from_record(existing_for_job, idempotent_replay=True)
        if job.status not in {ImportJobStatus.REVIEW_READY.value, ImportJobStatus.PARTIAL.value}:
            raise TripError("import_job_not_reviewable", "Import job is not reviewable.", 409)

        candidate_ids: list[str] = []
        created_count = 0
        reused_count = 0
        for group_key, group_items in sorted(confirmed_groups.items()):
            first_mention, selected = group_items[0]
            evidence_refs = [
                evidence_ref(job.artifact_id, mention.id)
                for mention, _candidate in group_items
            ][:8]
            snapshot = self.import_repository.get_url_fetch_snapshot_for_job(import_job_id=import_job_id)
            if snapshot is not None:
                evidence_refs = (evidence_refs + [f"fetch:{snapshot.id}"])[:8]
            response = self.trip_service.register_candidate(
                trip_id=trip_id,
                capability=capability,
                idempotency_key=f"import-candidate:{import_job_id}:{group_key}",
                payload=TripCandidateCreateRequest(
                    candidate_type=CandidateType.MEAL if selected.category == "restaurant" else CandidateType.PLACE,
                    display_name=selected.canonical_name,
                    canonical_place_id=selected.candidate_digest,
                    provider_place_id=selected.provider_place_id,
                    category=selected.category,
                    coordinates=(
                        CandidateCoordinate(latitude=selected.latitude, longitude=selected.longitude)
                        if selected.latitude is not None and selected.longitude is not None
                        else None
                    ),
                    address_summary=selected.address_summary,
                    source_kind=candidate_source_kind_for_import(job.input_type),
                    source_ref=f"import:{import_job_id}",
                    evidence_refs=evidence_refs,
                ),
            )
            candidate_ids.append(response.candidate.id)
            if response.deduplicated or response.idempotent_replay:
                reused_count += 1
            else:
                created_count += 1

        committed_at = format_utc(self.clock(timezone.utc))
        result = {
            "import_job_id": import_job_id,
            "review_version": job.review_version,
            "place_candidates_created": created_count,
            "place_candidates_reused": reused_count,
            "candidate_ids": candidate_ids,
            "notes_preserved": notes,
            "constraint_mentions_preserved": constraints,
            "ignored_mentions": ignored,
            "unresolved_mentions": unresolved,
            "committed_at": committed_at,
        }
        record = self.import_repository.create_commit_record(
            record=ImportCommitRecord(
                id=generate_import_commit_id(),
                import_job_id=import_job_id,
                review_version=job.review_version,
                result_json=result,
                commit_digest=commit_digest,
                created_at=committed_at,
            ),
            trip_id=trip_id,
            request_digest=req_digest,
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
            committed_at=committed_at,
        )
        return commit_response_from_record(record)

    def _get_or_create_artifact(
        self,
        *,
        trip_id: str,
        content_bytes: bytes,
        checksum: str,
        original_label: str | None,
        now: str,
        artifact_type: str = "text",
        mime_type: str = "text/plain",
        charset: str = "utf-8",
        storage_type: str = "text",
        extension: str = "txt",
    ) -> tuple[SourceArtifactRecord, bool]:
        existing = self.import_repository.find_artifact_by_checksum(
            trip_id=trip_id,
            artifact_type=artifact_type,
            checksum=checksum,
        )
        if existing is not None:
            return existing, True
        storage_key = make_storage_key(artifact_type=storage_type, extension=extension)
        self.artifact_store.put(storage_key=storage_key, content=content_bytes)
        artifact = SourceArtifactRecord(
            id=generate_artifact_id(),
            trip_id=trip_id,
            artifact_type=artifact_type,
            mime_type=mime_type,
            content_checksum=checksum,
            byte_size=len(content_bytes),
            charset=charset,
            privacy_level="private",
            storage_key=storage_key,
            original_label=original_label,
            created_at=now,
        )
        return self.import_repository.create_artifact(artifact), False

    def _get_or_create_artifact_from_file(
        self,
        *,
        trip_id: str,
        source_path: Path,
        checksum: str,
        byte_size: int,
        original_label: str | None,
        now: str,
        artifact_type: str,
        mime_type: str,
        storage_type: str,
        extension: str,
    ) -> tuple[SourceArtifactRecord, bool]:
        existing = self.import_repository.find_artifact_by_checksum(
            trip_id=trip_id,
            artifact_type=artifact_type,
            checksum=checksum,
        )
        if existing is not None:
            return existing, True
        storage_key = make_storage_key(artifact_type=storage_type, extension=extension)
        self.artifact_store.put_file(storage_key=storage_key, source_path=source_path)
        artifact = SourceArtifactRecord(
            id=generate_artifact_id(),
            trip_id=trip_id,
            artifact_type=artifact_type,
            mime_type=mime_type,
            content_checksum=checksum,
            byte_size=byte_size,
            charset="binary",
            privacy_level="private",
            storage_key=storage_key,
            original_label=original_label,
            created_at=now,
        )
        return self.import_repository.create_artifact(artifact), False

    def _stage_child_artifact_from_file(
        self,
        *,
        trip_id: str,
        source_path: Path,
        checksum: str,
        byte_size: int,
        now: str,
        artifact_type: str,
        mime_type: str,
        storage_type: str,
        extension: str,
    ) -> SourceArtifactRecord:
        storage_key = make_storage_key(artifact_type=storage_type, extension=extension)
        self.artifact_store.put_file(storage_key=storage_key, source_path=source_path)
        return SourceArtifactRecord(
            id=generate_artifact_id(),
            trip_id=trip_id,
            artifact_type=artifact_type,
            mime_type=mime_type,
            content_checksum=checksum,
            byte_size=byte_size,
            charset="binary",
            privacy_level="private",
            storage_key=storage_key,
            original_label=None,
            created_at=now,
        )

    def _stage_child_artifact_bytes(
        self,
        *,
        trip_id: str,
        content_bytes: bytes,
        checksum: str,
        now: str,
        artifact_type: str,
        mime_type: str,
        charset: str,
        storage_type: str,
        extension: str,
    ) -> SourceArtifactRecord:
        storage_key = make_storage_key(artifact_type=storage_type, extension=extension)
        self.artifact_store.put(storage_key=storage_key, content=content_bytes)
        return SourceArtifactRecord(
            id=generate_artifact_id(),
            trip_id=trip_id,
            artifact_type=artifact_type,
            mime_type=mime_type,
            content_checksum=checksum,
            byte_size=len(content_bytes),
            charset=charset,
            privacy_level="private",
            storage_key=storage_key,
            original_label=None,
            created_at=now,
        )

    def _inspect_quarantined_artifact(
        self,
        *,
        job: ImportJobRecord,
        artifact: SourceArtifactRecord,
        source_path: Path,
        detection,
        declared_mime_type: str | None,
    ) -> tuple[ArtifactInspectionRecord, SourceArtifactRecord | None, ArtifactDerivationRecord | None]:
        started_at = format_utc(self.clock(timezone.utc))
        sanitized_tmp = Path(tempfile.gettempdir()) / f"sanitized-{job.id}.bin" if detection.detected_kind == "image" else None
        runner = ArtifactInspectionRunner(
            timeout_seconds=get_import_inspection_timeout_seconds_inline(),
            max_memory_mb=get_import_inspection_max_memory_mb_inline(),
            max_output_bytes=get_import_inspection_max_output_bytes_inline(),
        )
        try:
            worker_result = runner.inspect(
                path=source_path,
                declared_kind=detection.declared_kind,
                detected_mime_type=detection.detected_mime_type,
                sanitized_output_path=sanitized_tmp,
                limits=binary_inspection_limits(),
            )
        except TripError as exc:
            worker_result = WorkerInspectionResult(
                schema_version=ARTIFACT_INSPECTION_SCHEMA_VERSION,
                inspector_version=ARTIFACT_INSPECTOR_VERSION,
                status="inspection_failed",
                classification="inspection_failed",
                error_code=exc.code,
                metadata={},
                findings=[],
            )
        completed_at = format_utc(self.clock(timezone.utc))
        child_artifact: SourceArtifactRecord | None = None
        derivation: ArtifactDerivationRecord | None = None
        try:
            if worker_result.status == ImportJobStatus.ARTIFACT_READY.value and detection.detected_kind == "image":
                if sanitized_tmp is None or not sanitized_tmp.exists():
                    raise TripError("import_image_metadata_sanitization_failed", "Sanitized image derivative was not created.", 422)
                child_artifact = self._stage_child_artifact_from_file(
                    trip_id=job.trip_id,
                    source_path=sanitized_tmp,
                    checksum=file_checksum(sanitized_tmp),
                    byte_size=sanitized_tmp.stat().st_size,
                    now=completed_at,
                    artifact_type="sanitized_image",
                    mime_type=str(worker_result.metadata.get("sanitized_derivative_mime_type") or "image/jpeg"),
                    storage_type="sanitized-image",
                    extension="png" if worker_result.metadata.get("sanitized_derivative_mime_type") == "image/png" else "jpg",
                )
                derivation = ArtifactDerivationRecord(
                    id=generate_artifact_derivation_id(),
                    parent_artifact_id=artifact.id,
                    child_artifact_id=child_artifact.id,
                    derivation_type="image_metadata_stripping",
                    transformer_version=IMAGE_SANITIZER_VERSION,
                    input_checksum=artifact.content_checksum,
                    output_checksum=child_artifact.content_checksum,
                    metadata={"metadata_stripped": True, "orientation_normalized": bool(worker_result.metadata.get("orientation_present"))},
                    created_at=completed_at,
                )
            elif worker_result.status == ImportJobStatus.ARTIFACT_READY.value and detection.detected_kind == "pdf":
                manifest = build_pdf_manifest_payload(
                    artifact=artifact,
                    worker_result=worker_result,
                    detection=detection,
                )
                manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                child_artifact = self._stage_child_artifact_bytes(
                    trip_id=job.trip_id,
                    content_bytes=manifest_bytes,
                    checksum=source_checksum(manifest_bytes),
                    now=completed_at,
                    artifact_type="document_manifest",
                    mime_type="application/json",
                    charset="utf-8",
                    storage_type="document-manifest",
                    extension="json",
                )
                derivation = ArtifactDerivationRecord(
                    id=generate_artifact_derivation_id(),
                    parent_artifact_id=artifact.id,
                    child_artifact_id=child_artifact.id,
                    derivation_type="pdf_structural_inspection",
                    transformer_version=PDF_MANIFEST_TRANSFORMER_VERSION,
                    input_checksum=artifact.content_checksum,
                    output_checksum=child_artifact.content_checksum,
                    metadata={"manifest_schema_version": ARTIFACT_INSPECTION_SCHEMA_VERSION},
                    created_at=completed_at,
                )
            inspection_id = generate_artifact_inspection_id()
            findings = [
                ArtifactInspectionFindingRecord(
                    id=generate_artifact_inspection_finding_id(),
                    inspection_id=inspection_id,
                    code=item.code,
                    severity=item.severity,
                    category=item.category,
                    evidence=safe_evidence(item.evidence),
                    created_at=completed_at,
                )
                for item in worker_result.findings
            ]
            inspection = ArtifactInspectionRecord(
                id=inspection_id,
                trip_id=job.trip_id,
                import_job_id=job.id,
                artifact_id=artifact.id,
                attempt=1,
                schema_version=worker_result.schema_version,
                inspector_version=worker_result.inspector_version,
                declared_kind=detection.declared_kind,
                detected_kind=detection.detected_kind,
                declared_mime_type=declared_mime_type,
                detected_mime_type=detection.detected_mime_type,
                status=worker_result.status,
                classification=worker_result.classification,
                byte_size=artifact.byte_size,
                content_checksum=artifact.content_checksum,
                metadata=safe_inspection_metadata(worker_result.metadata),
                sanitized_artifact_id=child_artifact.id if child_artifact and detection.detected_kind == "image" else None,
                manifest_artifact_id=child_artifact.id if child_artifact and detection.detected_kind == "pdf" else None,
                warning_codes=sorted({item.code for item in findings if item.severity == "warning"}),
                error_code=worker_result.error_code,
                started_at=started_at,
                completed_at=completed_at,
            )
            final_status = worker_result.status if worker_result.status in {
                ImportJobStatus.ARTIFACT_READY.value,
                ImportJobStatus.NEEDS_PASSWORD.value,
                ImportJobStatus.REJECTED.value,
            } else ImportJobStatus.FAILED.value
            self.import_repository.create_completed_artifact_inspection(
                inspection=inspection,
                findings=findings,
                child_artifact=child_artifact,
                derivation=derivation,
                final_job_status=final_status,
                updated_at=completed_at,
            )
            return inspection, child_artifact, derivation
        except Exception as exc:
            if child_artifact is not None:
                self.artifact_store.delete(storage_key=child_artifact.storage_key)
            if isinstance(exc, TripError):
                raise
            raise TripError("import_binary_quarantine_failed", "Artifact inspection result could not be persisted.", 500) from exc
        finally:
            if sanitized_tmp is not None:
                delete_staged_file(sanitized_tmp)

    def _process_inline(self, *, job: ImportJobRecord, source_text: str) -> ImportJobRecord:
        started = format_utc(self.clock(timezone.utc))
        extraction_attempt = ImportProcessingAttemptRecord(
            id=generate_import_attempt_id(),
            import_job_id=job.id,
            stage="extraction",
            extractor_version=IMPORT_EXTRACTOR_VERSION,
            resolver_version=None,
            status="running",
            warning_codes=[],
            error_code=None,
            started_at=started,
            completed_at=None,
        )
        self.import_repository.create_attempt(extraction_attempt)
        extracting = self.import_repository.update_job(
            trip_id=job.trip_id,
            import_job_id=job.id,
            status=ImportJobStatus.EXTRACTING.value,
            updated_at=started,
        )
        try:
            trip_context = self._trip_context(job.trip_id)
            extraction = self.extractor.extract(text=source_text, trip_context=trip_context)
            mentions = self._build_mentions(job=job, source_text=source_text, drafts=extraction.mentions)
        except Exception as exc:
            completed = format_utc(self.clock(timezone.utc))
            self.import_repository.complete_attempt(
                attempt_id=extraction_attempt.id,
                import_job_id=job.id,
                status="failed",
                warning_codes=[],
                error_code="import_extraction_schema_invalid",
                completed_at=completed,
            )
            return self.import_repository.update_job(
                trip_id=job.trip_id,
                import_job_id=job.id,
                status=ImportJobStatus.FAILED.value,
                updated_at=completed,
                warning_codes=["import_extraction_schema_invalid"],
                error_code="import_extraction_schema_invalid",
            )

        completed = format_utc(self.clock(timezone.utc))
        self.import_repository.complete_attempt(
            attempt_id=extraction_attempt.id,
            import_job_id=job.id,
            status="completed",
            warning_codes=extraction.warning_codes,
            error_code=None,
            completed_at=completed,
        )
        resolving = self.import_repository.update_job(
            trip_id=job.trip_id,
            import_job_id=extracting.id,
            status=ImportJobStatus.RESOLVING.value,
            updated_at=completed,
            mention_count=len(mentions),
            warning_codes=extraction.warning_codes,
        )

        resolution_attempt = ImportProcessingAttemptRecord(
            id=generate_import_attempt_id(),
            import_job_id=job.id,
            stage="resolution",
            extractor_version=None,
            resolver_version=IMPORT_RESOLVER_VERSION,
            status="running",
            warning_codes=[],
            error_code=None,
            started_at=completed,
            completed_at=None,
        )
        self.import_repository.create_attempt(resolution_attempt)
        resolutions: list[ResolvedPlaceCandidateRecord] = []
        warning_codes = list(job.warning_codes) + list(extraction.warning_codes)
        for mention in mentions:
            if mention.entity_type != MentionEntityType.PLACE.value:
                continue
            try:
                for candidate in self.resolver.resolve(mention=mention, trip_context=self._trip_context(job.trip_id)):
                    resolutions.append(replace(candidate, created_at=format_utc(self.clock(timezone.utc))))
            except Exception:
                warning_codes.append("import_provider_unavailable")
                resolutions.append(
                    ResolvedPlaceCandidateRecord(
                        id=f"res_failed_{mention.id}",
                        mention_id=mention.id,
                        provider="local_candidate_catalog",
                        provider_place_id=None,
                        canonical_name=mention.raw_text,
                        address_summary=None,
                        administrative_area=None,
                        city_code=None,
                        latitude=None,
                        longitude=None,
                        category=None,
                        confidence=0.0,
                        resolution_reason_codes=["provider_failed"],
                        data_state=ResolutionDataState.PROVIDER_FAILED.value,
                        candidate_digest=hashlib.sha256(f"provider_failed:{mention.id}".encode("utf-8")).hexdigest(),
                        created_at=format_utc(self.clock(timezone.utc)),
                    )
                )
        self.import_repository.add_mentions_and_resolutions(mentions=mentions, resolutions=resolutions)
        final_status = ImportJobStatus.REVIEW_READY.value
        if warning_codes or any(candidate.data_state in {ResolutionDataState.MISSING.value, ResolutionDataState.PROVIDER_FAILED.value, ResolutionDataState.PARTIAL.value} for candidate in resolutions):
            final_status = ImportJobStatus.PARTIAL.value
        finished = format_utc(self.clock(timezone.utc))
        self.import_repository.complete_attempt(
            attempt_id=resolution_attempt.id,
            import_job_id=job.id,
            status="completed",
            warning_codes=warning_codes,
            error_code=None,
            completed_at=finished,
        )
        return self.import_repository.update_job(
            trip_id=job.trip_id,
            import_job_id=resolving.id,
            status=final_status,
            updated_at=finished,
            mention_count=len(mentions),
            warning_codes=unique(warning_codes),
        )

    def _start_attempt(
        self,
        import_job_id: str,
        *,
        stage: str,
        extractor_version: str | None,
        resolver_version: str | None,
    ) -> ImportProcessingAttemptRecord:
        attempt = ImportProcessingAttemptRecord(
            id=generate_import_attempt_id(),
            import_job_id=import_job_id,
            stage=stage,
            extractor_version=extractor_version,
            resolver_version=resolver_version,
            status="running",
            warning_codes=[],
            error_code=None,
            started_at=format_utc(self.clock(timezone.utc)),
            completed_at=None,
        )
        self.import_repository.create_attempt(attempt)
        return attempt

    def _complete_attempt(
        self,
        attempt_id: str,
        import_job_id: str,
        *,
        warning_codes: list[str],
        error_code: str | None,
    ) -> None:
        self.import_repository.complete_attempt(
            attempt_id=attempt_id,
            import_job_id=import_job_id,
            status="failed" if error_code else "completed",
            warning_codes=warning_codes,
            error_code=error_code,
            completed_at=format_utc(self.clock(timezone.utc)),
        )

    def _build_mentions(
        self,
        *,
        job: ImportJobRecord,
        source_text: str,
        drafts,
    ) -> list[ExtractedMentionRecord]:
        mentions: list[ExtractedMentionRecord] = []
        seen_digest: set[str] = set()
        max_mentions = 60
        for draft in drafts[:max_mentions]:
            if draft.end_offset > len(source_text):
                raise TripError("import_span_invalid", "Import mention span is invalid.", 422)
            if source_text[draft.start_offset:draft.end_offset] != draft.raw_text:
                raise TripError("import_span_invalid", "Import mention span does not match source text.", 422)
            digest = mention_content_digest(
                artifact_id=job.artifact_id,
                entity_type=draft.entity_type.value,
                raw_text=draft.raw_text,
                start_offset=draft.start_offset,
                end_offset=draft.end_offset,
            )
            if digest in seen_digest:
                continue
            seen_digest.add(digest)
            mentions.append(
                ExtractedMentionRecord(
                    id=generate_mention_id(),
                    import_job_id=job.id,
                    artifact_id=job.artifact_id,
                    entity_type=draft.entity_type.value,
                    raw_text=draft.raw_text,
                    normalized_text=draft.normalized_text,
                    start_offset=draft.start_offset,
                    end_offset=draft.end_offset,
                    context_before=source_text[max(0, draft.start_offset - MAX_CONTEXT_CHARS):draft.start_offset],
                    context_after=source_text[draft.end_offset:draft.end_offset + MAX_CONTEXT_CHARS],
                    city_hint=draft.city_hint,
                    date_hint=draft.date_hint,
                    time_hint=draft.time_hint,
                    recommendation_reason=draft.recommendation_reason,
                    confidence=draft.confidence,
                    extraction_warning_codes=list(draft.extraction_warning_codes),
                    content_digest=digest,
                    created_at=format_utc(self.clock(timezone.utc)),
                )
            )
        return mentions

    def _validate_review_decision(
        self,
        *,
        job: ImportJobRecord,
        mention: ExtractedMentionRecord,
        payload: ImportReviewDecisionRequest,
    ) -> None:
        if payload.action in {ReviewAction.CONFIRM, ReviewAction.SELECT_CANDIDATE}:
            if mention.entity_type != MentionEntityType.PLACE.value:
                raise TripError("import_review_action_invalid", "Only place mentions can be confirmed as candidates.", 422)
            if not payload.selected_resolution_candidate_id:
                raise TripError("import_resolution_candidate_not_found", "Selected resolution candidate is required.", 422)
            candidate = self.import_repository.get_resolution_candidate(
                import_job_id=job.id,
                mention_id=mention.id,
                candidate_id=payload.selected_resolution_candidate_id,
            )
            if candidate.data_state in {ResolutionDataState.PROVIDER_FAILED.value, ResolutionDataState.MISSING.value}:
                raise TripError("import_resolution_candidate_not_found", "Selected resolution candidate is not usable.", 422)
            if candidate.data_state == ResolutionDataState.CROSS_CITY.value and not payload.cross_city_confirmed:
                raise TripError("import_cross_city_confirmation_required", "Cross-city candidate requires explicit confirmation.", 409)
        if payload.action == ReviewAction.MERGE:
            if not payload.merge_target_mention_id or payload.merge_target_mention_id == mention.id:
                raise TripError("import_merge_invalid", "Merge target is invalid.", 422)
            target = self.import_repository.get_mention(
                import_job_id=job.id,
                mention_id=payload.merge_target_mention_id,
            )
            if target.entity_type != MentionEntityType.PLACE.value or mention.entity_type != MentionEntityType.PLACE.value:
                raise TripError("import_merge_invalid", "Only place mentions can be merged.", 422)

    def _mention_responses(self, job: ImportJobRecord) -> list[ExtractedMentionResponse]:
        mentions = self.import_repository.list_mentions(import_job_id=job.id)
        resolutions_by_mention: dict[str, list[ResolvedPlaceCandidateRecord]] = defaultdict(list)
        for candidate in self.import_repository.list_resolution_candidates(import_job_id=job.id):
            resolutions_by_mention[candidate.mention_id].append(candidate)
        decisions_by_mention = latest_decision_by_mention(
            self.import_repository.list_review_decisions(import_job_id=job.id)
        )
        return [
            mention_to_response(
                mention,
                job=job,
                resolutions=resolutions_by_mention.get(mention.id, []),
                decision=decisions_by_mention.get(mention.id),
            )
            for mention in mentions
        ]

    def _span_responses(self, generation_id: str) -> list[DocumentTextSpanResponse]:
        return [span_to_response(span) for span in self.import_repository.list_document_text_spans(generation_id=generation_id)]

    def _trip_context(self, trip_id: str) -> dict[str, Any]:
        try:
            revision = self.trip_repository.get_current_revision(trip_id)
            snapshot = revision.itinerary_snapshot
        except Exception:
            return {}
        return {"city": infer_city_from_snapshot(snapshot)}

    def _require_trip_access(self, trip_id: str, capability: str | None) -> None:
        if not capability:
            raise TripError("trip_access_denied", "Trip access denied.", 403)
        self.trip_repository.get_trip_for_access(trip_id, hash_capability(capability))

def validate_text_payload(text: str) -> str:
    if "\x00" in text:
        raise TripError("import_text_invalid_encoding", "Text import contains invalid NUL bytes.", 422)
    normalized = text.replace("\r\n", "\n")
    if not normalized.strip():
        raise TripError("import_text_empty", "Text import is empty.", 422)
    byte_size = len(normalized.encode("utf-8"))
    if byte_size > get_import_text_max_bytes_inline():
        raise TripError("import_text_too_large", "Text import exceeds the configured byte limit.", 413)
    control_chars = sum(1 for char in normalized if ord(char) < 32 and char not in "\n\t\r")
    if control_chars / max(1, len(normalized)) > 0.02:
        raise TripError("import_text_unsafe_content", "Text import contains too many control characters.", 422)
    return normalized


def get_import_text_max_bytes_inline() -> int:
    # Late import avoids a config import cycle during tests that construct services directly.
    from app.core.runtime_config import get_import_text_max_bytes

    return get_import_text_max_bytes()


def get_import_url_enabled_inline() -> bool:
    from app.core.runtime_config import get_import_url_enabled

    return get_import_url_enabled()


def get_import_url_max_text_bytes_inline() -> int:
    from app.core.runtime_config import get_import_url_max_text_bytes

    return get_import_url_max_text_bytes()


def get_import_binary_enabled_inline() -> bool:
    from app.core.runtime_config import get_import_binary_enabled

    return get_import_binary_enabled()


def get_import_binary_max_image_bytes_inline() -> int:
    from app.core.runtime_config import get_import_binary_max_image_bytes

    return get_import_binary_max_image_bytes()


def get_import_binary_max_pdf_bytes_inline() -> int:
    from app.core.runtime_config import get_import_binary_max_pdf_bytes

    return get_import_binary_max_pdf_bytes()


def get_import_binary_upload_chunk_bytes_inline() -> int:
    from app.core.runtime_config import get_import_binary_upload_chunk_bytes

    return get_import_binary_upload_chunk_bytes()


def get_import_binary_staging_root_inline() -> str:
    from app.core.runtime_config import get_import_binary_staging_root

    return get_import_binary_staging_root()


def get_import_inspection_timeout_seconds_inline() -> float:
    from app.core.runtime_config import get_import_inspection_timeout_seconds

    return get_import_inspection_timeout_seconds()


def get_import_inspection_max_memory_mb_inline() -> int:
    from app.core.runtime_config import get_import_inspection_max_memory_mb

    return get_import_inspection_max_memory_mb()


def get_import_inspection_max_output_bytes_inline() -> int:
    from app.core.runtime_config import get_import_inspection_max_output_bytes

    return get_import_inspection_max_output_bytes()


def get_import_document_extraction_enabled_inline() -> bool:
    from app.core.runtime_config import get_import_document_extraction_enabled

    return get_import_document_extraction_enabled()


def get_import_document_extraction_timeout_seconds_inline() -> float:
    from app.core.runtime_config import get_import_document_extraction_timeout_seconds

    return get_import_document_extraction_timeout_seconds()


def get_import_document_extraction_max_memory_mb_inline() -> int:
    from app.core.runtime_config import get_import_document_extraction_max_memory_mb

    return get_import_document_extraction_max_memory_mb()


def get_import_document_extraction_max_output_bytes_inline() -> int:
    from app.core.runtime_config import get_import_document_extraction_max_output_bytes

    return get_import_document_extraction_max_output_bytes()


def get_import_document_max_text_bytes_inline() -> int:
    from app.core.runtime_config import get_import_document_max_text_bytes

    return get_import_document_max_text_bytes()


def binary_inspection_limits() -> dict[str, Any]:
    from app.core.runtime_config import (
        get_import_image_max_dimension,
        get_import_image_max_pixels,
        get_import_pdf_max_objects,
        get_import_pdf_max_pages,
    )

    return {
        "max_image_pixels": get_import_image_max_pixels(),
        "max_image_dimension": get_import_image_max_dimension(),
        "max_aspect_ratio": 20.0,
        "max_pdf_pages": get_import_pdf_max_pages(),
        "max_pdf_objects": get_import_pdf_max_objects(),
        "max_pdf_scan_nodes": 3000,
    }


def document_extraction_limits() -> dict[str, Any]:
    from app.core.runtime_config import (
        get_import_document_ocr_command,
        get_import_document_ocr_languages,
        get_import_document_ocr_timeout_seconds,
        get_import_pdf_page_ocr_enabled,
        get_import_pdf_max_pages,
    )

    return {
        "max_pdf_pages": get_import_pdf_max_pages(),
        "max_text_bytes": get_import_document_max_text_bytes_inline(),
        "ocr_command": get_import_document_ocr_command(),
        "ocr_languages": get_import_document_ocr_languages(),
        "ocr_timeout_seconds": get_import_document_ocr_timeout_seconds(),
        "enable_pdf_page_ocr": get_import_pdf_page_ocr_enabled(),
        "pdf_render_scale": 2.0,
    }


def validate_document_extracted_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in normalized:
        raise TripError("import_document_text_invalid_encoding", "Extracted document text contains invalid NUL bytes.", 422)
    if not normalized.strip():
        raise TripError("import_document_extraction_no_text", "Document extraction did not produce reviewable text.", 422)
    encoded = normalized.encode("utf-8")
    max_bytes = get_import_document_max_text_bytes_inline()
    if len(encoded) > max_bytes:
        return encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip()
    return normalized


def span_from_worker(
    *,
    generation_id: str,
    span: WorkerDocumentSpan,
    source_text: str,
    created_at: str,
) -> DocumentTextSpanRecord:
    value = source_text[span.span_start:span.span_end]
    return DocumentTextSpanRecord(
        id=generate_document_text_span_id(),
        generation_id=generation_id,
        span_start=span.span_start,
        span_end=span.span_end,
        page_number=span.page_number,
        block_index=span.block_index,
        line_index=span.line_index,
        token_index=span.token_index,
        bbox=safe_document_bbox(span.bbox),
        source_kind=span.source_kind,
        confidence=span.confidence,
        text_digest=sha256_digest({"text": value, "span_start": span.span_start, "span_end": span.span_end}),
        warning_codes=list(span.warning_codes),
        created_at=created_at,
    )


def safe_document_bbox(value: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in ("x0", "y0", "x1", "y1"):
        raw = value.get(key)
        if isinstance(raw, (int, float)):
            safe[key] = round(float(raw), 3)
    unit = value.get("unit")
    if isinstance(unit, str) and unit in {"pt", "px"}:
        safe["unit"] = unit
    return safe


def safe_document_extraction_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in ("native_text_pages", "ocr_pages", "image_width", "image_height"):
        value = metadata.get(key)
        if isinstance(value, (int, float, bool)) or value is None:
            safe[key] = value
    page_failures = metadata.get("page_failures")
    if isinstance(page_failures, list):
        safe["page_failures"] = [
            {
                "page_number": int(item.get("page_number", 0)),
                "error_code": str(item.get("error_code", ""))[:80],
            }
            for item in page_failures
            if isinstance(item, dict)
        ][:80]
    capabilities = metadata.get("ocr_capabilities")
    if isinstance(capabilities, dict):
        safe["ocr_capabilities"] = {
            "engine": str(capabilities.get("engine") or "")[:40],
            "available": bool(capabilities.get("available")),
            "languages": str(capabilities.get("languages") or "")[:80],
            "silent_fallback": bool(capabilities.get("silent_fallback")),
        }
    return safe


def file_checksum(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def build_pdf_manifest_payload(*, artifact: SourceArtifactRecord, worker_result: WorkerInspectionResult, detection) -> dict[str, Any]:
    metadata = safe_inspection_metadata(worker_result.metadata)
    return {
        "schema_version": ARTIFACT_INSPECTION_SCHEMA_VERSION,
        "inspector_version": worker_result.inspector_version,
        "artifact_checksum": artifact.content_checksum,
        "classification": worker_result.classification,
        "detected_mime_type": detection.detected_mime_type,
        "page_count": metadata.get("page_count"),
        "encrypted": metadata.get("encrypted"),
        "presence_flags": {
            "acroform_present": metadata.get("acroform_present", False),
            "xfa_present": metadata.get("xfa_present", False),
            "external_uri_present": metadata.get("external_uri_present", False),
            "active_content_present": metadata.get("active_content_present", False),
            "embedded_files_present": metadata.get("embedded_files_present", False),
            "unusual_page_dimensions": metadata.get("unusual_page_dimensions", False),
        },
        "finding_codes": [item.code for item in worker_result.findings],
        "warning_codes": [item.code for item in worker_result.findings if item.severity == "warning"],
    }


def safe_inspection_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "detected_format",
        "width",
        "height",
        "pixel_count",
        "frame_count",
        "metadata_present",
        "gps_metadata_present",
        "orientation_present",
        "sanitized_derivative_mime_type",
        "encrypted",
        "page_count",
        "object_count",
        "acroform_present",
        "xfa_present",
        "external_uri_present",
        "active_content_present",
        "embedded_files_present",
        "unusual_page_dimensions",
    }
    safe: dict[str, Any] = {}
    for key in allowed_keys:
        value = metadata.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    return safe


def safe_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in evidence.items():
        if isinstance(value, (bool, int, float)):
            safe[key] = value
        elif isinstance(value, str) and len(value) <= 80 and "/" not in value and "\\" not in value:
            safe[key] = value
    return safe


def infer_city_from_snapshot(snapshot: dict[str, Any]) -> str | None:
    trip_intent = snapshot.get("trip_intent")
    if isinstance(trip_intent, dict):
        current = trip_intent.get("current_intent")
        if isinstance(current, dict) and isinstance(current.get("city"), str):
            return current["city"]
    anchor = snapshot.get("planning_anchor_source")
    if isinstance(anchor, dict) and isinstance(anchor.get("source_name"), str):
        anchor_city = normalize_city_name(anchor["source_name"])
        if anchor_city in CITY_CANDIDATES:
            return anchor_city
    return None


def latest_decision_by_mention(decisions: list[ImportReviewDecisionRecord]) -> dict[str, ImportReviewDecisionRecord]:
    latest: dict[str, ImportReviewDecisionRecord] = {}
    for decision in decisions:
        latest[decision.mention_id] = decision
    return latest


def evidence_ref(artifact_id: str, mention_id: str) -> str:
    return f"artifact:{artifact_id}#mention:{mention_id}"


def candidate_source_kind_for_import(input_type: str) -> CandidateSourceKind:
    if input_type == "url":
        return CandidateSourceKind.URL_IMPORT
    if input_type == "document":
        return CandidateSourceKind.DOCUMENT_IMPORT
    return CandidateSourceKind.TEXT_IMPORT


def mention_to_response(
    mention: ExtractedMentionRecord,
    *,
    job: ImportJobRecord,
    resolutions: list[ResolvedPlaceCandidateRecord],
    decision: ImportReviewDecisionRecord | None,
) -> ExtractedMentionResponse:
    review_state = infer_review_state(mention, resolutions, decision)
    return ExtractedMentionResponse(
        id=mention.id,
        import_job_id=mention.import_job_id,
        artifact_id=mention.artifact_id,
        entity_type=mention.entity_type,
        raw_text=mention.raw_text,
        normalized_text=mention.normalized_text,
        start_offset=mention.start_offset,
        end_offset=mention.end_offset,
        context_before=mention.context_before,
        context_after=mention.context_after,
        city_hint=mention.city_hint,
        date_hint=mention.date_hint,
        time_hint=mention.time_hint,
        recommendation_reason=mention.recommendation_reason,
        confidence=mention.confidence,
        extraction_warning_codes=mention.extraction_warning_codes,
        content_digest=mention.content_digest,
        review_state=review_state,
        selected_resolution_candidate_id=decision.selected_resolution_candidate_id if decision else default_selected_resolution(resolutions),
        latest_decision=decision_to_response(decision) if decision else None,
        resolution_candidates=[resolution_to_response(candidate) for candidate in resolutions],
        created_at=mention.created_at,
    )


def infer_review_state(
    mention: ExtractedMentionRecord,
    resolutions: list[ResolvedPlaceCandidateRecord],
    decision: ImportReviewDecisionRecord | None,
) -> str:
    if decision:
        if decision.action in {ReviewAction.CONFIRM.value, ReviewAction.SELECT_CANDIDATE.value}:
            return "confirmed"
        if decision.action == ReviewAction.IGNORE.value:
            return "ignored"
        if decision.action == ReviewAction.MARK_AS_NOTE.value:
            return "note"
        if decision.action == ReviewAction.MERGE.value:
            return "duplicate"
    if mention.entity_type != MentionEntityType.PLACE.value:
        return "note" if mention.entity_type == MentionEntityType.NOTE.value else "needs_review"
    if not resolutions:
        return "unresolved"
    if all(candidate.data_state in {ResolutionDataState.MISSING.value, ResolutionDataState.PROVIDER_FAILED.value} for candidate in resolutions):
        return "unresolved"
    if any(candidate.data_state in {ResolutionDataState.AMBIGUOUS.value, ResolutionDataState.CROSS_CITY.value} for candidate in resolutions):
        return "ambiguous"
    return "needs_review"


def default_selected_resolution(resolutions: list[ResolvedPlaceCandidateRecord]) -> str | None:
    usable = [
        candidate
        for candidate in resolutions
        if candidate.data_state not in {ResolutionDataState.MISSING.value, ResolutionDataState.PROVIDER_FAILED.value}
    ]
    if not usable:
        return None
    return sorted(usable, key=lambda item: (-item.confidence, item.canonical_name, item.id))[0].id


def artifact_to_response(artifact: SourceArtifactRecord) -> SourceArtifactResponse:
    return SourceArtifactResponse(
        id=artifact.id,
        trip_id=artifact.trip_id,
        artifact_type=artifact.artifact_type,
        mime_type=artifact.mime_type,
        content_checksum=artifact.content_checksum,
        byte_size=artifact.byte_size,
        charset=artifact.charset,
        privacy_level=artifact.privacy_level,
        original_label=artifact.original_label,
        created_at=artifact.created_at,
    )


def job_to_response(job: ImportJobRecord) -> ImportJobResponse:
    return ImportJobResponse(
        id=job.id,
        trip_id=job.trip_id,
        artifact_id=job.artifact_id,
        input_type=job.input_type,
        status=job.status,
        extraction_schema_version=job.extraction_schema_version,
        extractor_version=job.extractor_version,
        resolver_version=job.resolver_version,
        review_version=job.review_version,
        mention_count=job.mention_count,
        warning_codes=job.warning_codes,
        error_code=job.error_code,
        committed_at=job.committed_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def snapshot_to_response(snapshot: URLFetchSnapshotRecord | None) -> URLFetchSnapshotResponse | None:
    if snapshot is None:
        return None
    return URLFetchSnapshotResponse(
        id=snapshot.id,
        import_job_id=snapshot.import_job_id,
        raw_artifact_id=snapshot.raw_artifact_id,
        request_url_sanitized=snapshot.request_url_sanitized,
        normalized_request_url=snapshot.normalized_request_url,
        final_url_sanitized=snapshot.final_url_sanitized,
        redirect_chain=snapshot.redirect_chain,
        robots_status=snapshot.robots_status,
        robots_checked_at=snapshot.robots_checked_at,
        status_code=snapshot.status_code,
        content_type=snapshot.content_type,
        declared_charset=snapshot.declared_charset,
        effective_charset=snapshot.effective_charset,
        content_language=snapshot.content_language,
        compressed_bytes=snapshot.compressed_bytes,
        decoded_bytes=snapshot.decoded_bytes,
        body_checksum=snapshot.body_checksum,
        fetcher_version=snapshot.fetcher_version,
        policy_version=snapshot.policy_version,
        fetched_at=snapshot.fetched_at,
        warning_codes=snapshot.warning_codes,
        cache_status=snapshot.cache_status,
        page_title=str(snapshot.header_metadata.get("page_title") or "") or None,
        source_host=str(snapshot.header_metadata.get("source_host") or "") or None,
        final_host=str(snapshot.header_metadata.get("final_host") or "") or None,
        recovery_actions=["paste_text"],
    )


def derivation_to_response(derivation: ArtifactDerivationRecord | None) -> ArtifactDerivationResponse | None:
    if derivation is None:
        return None
    return ArtifactDerivationResponse(
        id=derivation.id,
        parent_artifact_id=derivation.parent_artifact_id,
        child_artifact_id=derivation.child_artifact_id,
        derivation_type=derivation.derivation_type,
        transformer_version=derivation.transformer_version,
        input_checksum=derivation.input_checksum,
        output_checksum=derivation.output_checksum,
        created_at=derivation.created_at,
    )


def inspection_to_response(
    inspection: ArtifactInspectionRecord,
    *,
    findings: list[ArtifactInspectionFindingRecord],
) -> ArtifactInspectionResponse:
    return ArtifactInspectionResponse(
        id=inspection.id,
        trip_id=inspection.trip_id,
        import_job_id=inspection.import_job_id,
        artifact_id=inspection.artifact_id,
        attempt=inspection.attempt,
        schema_version=inspection.schema_version,
        inspector_version=inspection.inspector_version,
        declared_kind=inspection.declared_kind,
        detected_kind=inspection.detected_kind,
        declared_mime_type=inspection.declared_mime_type,
        detected_mime_type=inspection.detected_mime_type,
        status=inspection.status,
        classification=inspection.classification,
        byte_size=inspection.byte_size,
        content_checksum=inspection.content_checksum,
        metadata=inspection.metadata,
        sanitized_artifact_id=inspection.sanitized_artifact_id,
        manifest_artifact_id=inspection.manifest_artifact_id,
        findings=[
            ArtifactInspectionFindingResponse(
                id=item.id,
                inspection_id=item.inspection_id,
                code=item.code,
                severity=item.severity,
                category=item.category,
                evidence=item.evidence,
                created_at=item.created_at,
            )
            for item in findings
        ],
        warning_codes=inspection.warning_codes,
        error_code=inspection.error_code,
        started_at=inspection.started_at,
        completed_at=inspection.completed_at,
    )


def generation_to_response(generation: DocumentExtractionGenerationRecord) -> DocumentExtractionGenerationResponse:
    return DocumentExtractionGenerationResponse(
        id=generation.id,
        trip_id=generation.trip_id,
        source_import_job_id=generation.source_import_job_id,
        source_artifact_id=generation.source_artifact_id,
        inspection_id=generation.inspection_id,
        derived_import_job_id=generation.derived_import_job_id,
        derived_artifact_id=generation.derived_artifact_id,
        generation=generation.generation,
        schema_version=generation.schema_version,
        extractor_version=generation.extractor_version,
        strategy=generation.strategy,
        status=generation.status,
        page_count=generation.page_count,
        extracted_text_chars=generation.extracted_text_chars,
        warning_codes=generation.warning_codes,
        error_code=generation.error_code,
        metadata=generation.metadata,
        created_at=generation.created_at,
    )


def empty_generation_response(
    *,
    trip_id: str,
    source_job: ImportJobRecord,
    inspection: ArtifactInspectionRecord,
) -> DocumentExtractionGenerationResponse:
    return DocumentExtractionGenerationResponse(
        id="",
        trip_id=trip_id,
        source_import_job_id=source_job.id,
        source_artifact_id=source_job.artifact_id,
        inspection_id=inspection.id,
        generation=0,
        schema_version=DOCUMENT_EXTRACTION_SCHEMA_VERSION,
        extractor_version=DOCUMENT_EXTRACTOR_VERSION,
        strategy="pdf_native_text" if source_job.input_type == "pdf" else "image_ocr",
        status="failed",
        page_count=0,
        extracted_text_chars=0,
        warning_codes=[],
        error_code=None,
        metadata={},
        created_at=inspection.completed_at,
    )


def span_to_response(span: DocumentTextSpanRecord) -> DocumentTextSpanResponse:
    return DocumentTextSpanResponse(
        id=span.id,
        generation_id=span.generation_id,
        span_start=span.span_start,
        span_end=span.span_end,
        page_number=span.page_number,
        block_index=span.block_index,
        line_index=span.line_index,
        token_index=span.token_index,
        bbox=span.bbox,
        source_kind=span.source_kind,
        confidence=span.confidence,
        text_digest=span.text_digest,
        warning_codes=span.warning_codes,
        created_at=span.created_at,
    )


def extension_for_content_type(content_type: str) -> str:
    if content_type == "text/plain":
        return "txt"
    if content_type == "application/xhtml+xml":
        return "xhtml"
    return "html"


def resolution_to_response(candidate: ResolvedPlaceCandidateRecord) -> ResolvedPlaceCandidateResponse:
    return ResolvedPlaceCandidateResponse(
        id=candidate.id,
        mention_id=candidate.mention_id,
        provider=candidate.provider,
        provider_place_id=candidate.provider_place_id,
        canonical_name=candidate.canonical_name,
        address_summary=candidate.address_summary,
        administrative_area=candidate.administrative_area,
        city_code=candidate.city_code,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        category=candidate.category,
        confidence=candidate.confidence,
        resolution_reason_codes=candidate.resolution_reason_codes,
        data_state=candidate.data_state,
        candidate_digest=candidate.candidate_digest,
        created_at=candidate.created_at,
    )


def decision_to_response(
    decision: ImportReviewDecisionRecord,
    *,
    idempotent_replay: bool = False,
) -> ImportReviewDecisionResponse:
    return ImportReviewDecisionResponse(
        id=decision.id,
        import_job_id=decision.import_job_id,
        mention_id=decision.mention_id,
        review_version=decision.review_version,
        action=decision.action,
        selected_resolution_candidate_id=decision.selected_resolution_candidate_id,
        merge_target_mention_id=decision.merge_target_mention_id,
        note_text=decision.note_text,
        reason_code=decision.reason_code,
        created_at=decision.created_at,
        idempotent_replay=idempotent_replay,
    )


def commit_response_from_record(
    record: ImportCommitRecord,
    *,
    idempotent_replay: bool = False,
) -> ImportCommitResponse:
    payload = dict(record.result_json)
    return ImportCommitResponse(
        import_job_id=str(payload["import_job_id"]),
        review_version=int(payload["review_version"]),
        place_candidates_created=int(payload["place_candidates_created"]),
        place_candidates_reused=int(payload["place_candidates_reused"]),
        candidate_ids=list(payload["candidate_ids"]),
        notes_preserved=int(payload["notes_preserved"]),
        constraint_mentions_preserved=int(payload["constraint_mentions_preserved"]),
        ignored_mentions=int(payload["ignored_mentions"]),
        unresolved_mentions=int(payload["unresolved_mentions"]),
        committed_at=str(payload["committed_at"]),
        idempotent_replay=idempotent_replay,
    )


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def format_utc(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")
