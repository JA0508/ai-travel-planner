from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


IMPORT_EXTRACTION_SCHEMA_VERSION = "1.0"
IMPORT_EXTRACTOR_VERSION = "deterministic-text-v1"
IMPORT_RESOLVER_VERSION = "deterministic-place-v1"
URL_IMPORT_POLICY_VERSION = "secure-url-policy-v1"
URL_IMPORT_FETCHER_VERSION = "secure-url-fetcher-v1"
URL_DOCUMENT_TEXT_TRANSFORMER_VERSION = "document-text-v1"
ARTIFACT_INSPECTION_SCHEMA_VERSION = "1.0"
ARTIFACT_INSPECTOR_VERSION = "binary-inspector-v1"
IMAGE_SANITIZER_VERSION = "image-sanitizer-v1"
PDF_MANIFEST_TRANSFORMER_VERSION = "pdf-manifest-v1"
DOCUMENT_EXTRACTION_SCHEMA_VERSION = "1.0"
DOCUMENT_EXTRACTOR_VERSION = "document-extractor-v1"
DOCUMENT_TEXT_TRANSFORMER_VERSION = "document-text-v1"
MAX_CONTEXT_CHARS = 80


class ImportJobStatus(str, Enum):
    CREATED = "created"
    RECEIVING = "receiving"
    QUARANTINED = "quarantined"
    INSPECTING = "inspecting"
    ARTIFACT_READY = "artifact_ready"
    NEEDS_PASSWORD = "needs_password"
    REJECTED = "rejected"
    FETCHING = "fetching"
    EXTRACTING_CONTENT = "extracting_content"
    EXTRACTING = "extracting"
    EXTRACTING_MENTIONS = "extracting_mentions"
    RESOLVING = "resolving"
    REVIEW_READY = "review_ready"
    PARTIAL = "partial"
    FAILED = "failed"
    COMMITTED = "committed"
    CANCELLED = "cancelled"


class MentionEntityType(str, Enum):
    PLACE = "place"
    FIXED_EVENT = "fixed_event"
    TIME_CONSTRAINT = "time_constraint"
    NOTE = "note"


class ResolutionDataState(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"
    PROVIDER_FAILED = "provider_failed"
    CROSS_CITY = "cross_city"
    PARTIAL = "partial"


class ReviewAction(str, Enum):
    CONFIRM = "confirm"
    SELECT_CANDIDATE = "select_candidate"
    IGNORE = "ignore"
    MERGE = "merge"
    MARK_AS_NOTE = "mark_as_note"
    RESET = "reset"


LEGAL_IMPORT_TRANSITIONS: dict[str, set[str]] = {
    ImportJobStatus.CREATED.value: {
        ImportJobStatus.RECEIVING.value,
        ImportJobStatus.FETCHING.value,
        ImportJobStatus.EXTRACTING.value,
        ImportJobStatus.CANCELLED.value,
        ImportJobStatus.FAILED.value,
    },
    ImportJobStatus.RECEIVING.value: {
        ImportJobStatus.QUARANTINED.value,
        ImportJobStatus.FAILED.value,
        ImportJobStatus.CANCELLED.value,
    },
    ImportJobStatus.QUARANTINED.value: {
        ImportJobStatus.INSPECTING.value,
        ImportJobStatus.FAILED.value,
        ImportJobStatus.CANCELLED.value,
    },
    ImportJobStatus.INSPECTING.value: {
        ImportJobStatus.ARTIFACT_READY.value,
        ImportJobStatus.NEEDS_PASSWORD.value,
        ImportJobStatus.REJECTED.value,
        ImportJobStatus.FAILED.value,
    },
    ImportJobStatus.ARTIFACT_READY.value: set(),
    ImportJobStatus.NEEDS_PASSWORD.value: set(),
    ImportJobStatus.REJECTED.value: set(),
    ImportJobStatus.FETCHING.value: {
        ImportJobStatus.EXTRACTING_CONTENT.value,
        ImportJobStatus.PARTIAL.value,
        ImportJobStatus.FAILED.value,
    },
    ImportJobStatus.EXTRACTING_CONTENT.value: {
        ImportJobStatus.EXTRACTING.value,
        ImportJobStatus.EXTRACTING_MENTIONS.value,
        ImportJobStatus.PARTIAL.value,
        ImportJobStatus.FAILED.value,
    },
    ImportJobStatus.EXTRACTING.value: {
        ImportJobStatus.RESOLVING.value,
        ImportJobStatus.PARTIAL.value,
        ImportJobStatus.FAILED.value,
    },
    ImportJobStatus.EXTRACTING_MENTIONS.value: {
        ImportJobStatus.RESOLVING.value,
        ImportJobStatus.PARTIAL.value,
        ImportJobStatus.FAILED.value,
    },
    ImportJobStatus.RESOLVING.value: {
        ImportJobStatus.REVIEW_READY.value,
        ImportJobStatus.PARTIAL.value,
        ImportJobStatus.FAILED.value,
    },
    ImportJobStatus.REVIEW_READY.value: {
        ImportJobStatus.COMMITTED.value,
        ImportJobStatus.CANCELLED.value,
    },
    ImportJobStatus.PARTIAL.value: {
        ImportJobStatus.COMMITTED.value,
        ImportJobStatus.CANCELLED.value,
        ImportJobStatus.RESOLVING.value,
    },
    ImportJobStatus.FAILED.value: {ImportJobStatus.RESOLVING.value, ImportJobStatus.CANCELLED.value},
    ImportJobStatus.COMMITTED.value: set(),
    ImportJobStatus.CANCELLED.value: set(),
}


class TextImportCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=0)
    original_label: str | None = Field(default=None, max_length=160)


class URLImportCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., min_length=1, max_length=2048)
    refresh: bool = False


class ImportReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_review_version: int = Field(..., ge=0)
    action: ReviewAction
    selected_resolution_candidate_id: str | None = Field(default=None, max_length=120)
    merge_target_mention_id: str | None = Field(default=None, max_length=120)
    note_text: str | None = Field(default=None, max_length=240)
    reason_code: str | None = Field(default=None, max_length=80)
    cross_city_confirmed: bool = False


class ImportCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_review_version: int = Field(..., ge=0)


class SourceArtifactResponse(BaseModel):
    id: str
    trip_id: str
    artifact_type: str
    mime_type: str
    content_checksum: str
    byte_size: int
    charset: str
    privacy_level: str
    original_label: str | None = None
    created_at: str


class ImportJobResponse(BaseModel):
    id: str
    trip_id: str
    artifact_id: str
    input_type: str
    status: str
    extraction_schema_version: str
    extractor_version: str
    resolver_version: str
    review_version: int
    mention_count: int
    warning_codes: list[str] = Field(default_factory=list)
    error_code: str | None = None
    committed_at: str | None = None
    created_at: str
    updated_at: str


class ResolvedPlaceCandidateResponse(BaseModel):
    id: str
    mention_id: str
    provider: str
    provider_place_id: str | None = None
    canonical_name: str
    address_summary: str | None = None
    administrative_area: str | None = None
    city_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    category: str | None = None
    confidence: float
    resolution_reason_codes: list[str] = Field(default_factory=list)
    data_state: str
    candidate_digest: str
    created_at: str


class ImportReviewDecisionResponse(BaseModel):
    id: str
    import_job_id: str
    mention_id: str
    review_version: int
    action: str
    selected_resolution_candidate_id: str | None = None
    merge_target_mention_id: str | None = None
    note_text: str | None = None
    reason_code: str | None = None
    created_at: str
    idempotent_replay: bool = False


class ExtractedMentionResponse(BaseModel):
    id: str
    import_job_id: str
    artifact_id: str
    entity_type: str
    raw_text: str
    normalized_text: str | None = None
    start_offset: int
    end_offset: int
    context_before: str
    context_after: str
    city_hint: str | None = None
    date_hint: str | None = None
    time_hint: str | None = None
    recommendation_reason: str | None = None
    confidence: float
    extraction_warning_codes: list[str] = Field(default_factory=list)
    content_digest: str
    review_state: str
    selected_resolution_candidate_id: str | None = None
    latest_decision: ImportReviewDecisionResponse | None = None
    resolution_candidates: list[ResolvedPlaceCandidateResponse] = Field(default_factory=list)
    created_at: str


class TextImportCreateResponse(BaseModel):
    artifact: SourceArtifactResponse
    job: ImportJobResponse
    mentions: list[ExtractedMentionResponse]
    duplicate_artifact: bool = False
    idempotent_replay: bool = False


class SafeRedirectHopResponse(BaseModel):
    from_url: str
    to_url: str
    status_code: int
    validation: str


class URLFetchSnapshotResponse(BaseModel):
    id: str
    import_job_id: str
    raw_artifact_id: str
    request_url_sanitized: str
    normalized_request_url: str
    final_url_sanitized: str
    redirect_chain: list[SafeRedirectHopResponse] = Field(default_factory=list)
    robots_status: str
    robots_checked_at: str
    status_code: int
    content_type: str
    declared_charset: str | None = None
    effective_charset: str | None = None
    content_language: str | None = None
    compressed_bytes: int
    decoded_bytes: int
    body_checksum: str
    fetcher_version: str
    policy_version: str
    fetched_at: str
    warning_codes: list[str] = Field(default_factory=list)
    cache_status: str
    page_title: str | None = None
    source_host: str | None = None
    final_host: str | None = None
    recovery_actions: list[str] = Field(default_factory=list)


class ArtifactDerivationResponse(BaseModel):
    id: str
    parent_artifact_id: str
    child_artifact_id: str
    derivation_type: str
    transformer_version: str
    input_checksum: str
    output_checksum: str
    created_at: str


class ArtifactInspectionFindingResponse(BaseModel):
    id: str
    inspection_id: str
    code: str
    severity: Literal["info", "warning", "block"]
    category: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ArtifactInspectionResponse(BaseModel):
    id: str
    trip_id: str
    import_job_id: str
    artifact_id: str
    attempt: int
    schema_version: str
    inspector_version: str
    declared_kind: str
    detected_kind: str
    declared_mime_type: str | None = None
    detected_mime_type: str
    status: str
    classification: str
    byte_size: int
    content_checksum: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    sanitized_artifact_id: str | None = None
    manifest_artifact_id: str | None = None
    findings: list[ArtifactInspectionFindingResponse] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    error_code: str | None = None
    started_at: str
    completed_at: str


class BinaryImportCreateResponse(BaseModel):
    artifact: SourceArtifactResponse
    job: ImportJobResponse
    inspection: ArtifactInspectionResponse
    derivation: ArtifactDerivationResponse | None = None
    duplicate_artifact: bool = False
    idempotent_replay: bool = False


class URLImportCreateResponse(TextImportCreateResponse):
    source_fetch: URLFetchSnapshotResponse | None = None
    derivation: ArtifactDerivationResponse | None = None


class ImportReviewResponse(BaseModel):
    artifact: SourceArtifactResponse
    job: ImportJobResponse
    mentions: list[ExtractedMentionResponse]
    source_fetch: URLFetchSnapshotResponse | None = None
    derivation: ArtifactDerivationResponse | None = None


class ImportCommitResponse(BaseModel):
    import_job_id: str
    review_version: int
    place_candidates_created: int
    place_candidates_reused: int
    candidate_ids: list[str]
    notes_preserved: int
    constraint_mentions_preserved: int
    ignored_mentions: int
    unresolved_mentions: int
    committed_at: str
    idempotent_replay: bool = False


class DocumentTextSpanResponse(BaseModel):
    id: str
    generation_id: str
    span_start: int
    span_end: int
    page_number: int
    block_index: int
    line_index: int
    token_index: int | None = None
    block_id: str
    line_id: str
    token_id: str | None = None
    reading_order: int
    bbox: dict[str, Any] = Field(default_factory=dict)
    source_kind: str
    confidence: float | None = None
    text_digest: str
    warning_codes: list[str] = Field(default_factory=list)
    created_at: str


class DocumentExtractionGenerationResponse(BaseModel):
    id: str
    trip_id: str
    source_import_job_id: str
    source_artifact_id: str
    inspection_id: str
    derived_import_job_id: str | None = None
    derived_artifact_id: str | None = None
    layout_artifact_id: str | None = None
    span_map_artifact_id: str | None = None
    generation: int
    schema_version: str
    extractor_version: str
    strategy: str
    status: str
    page_count: int
    extracted_text_chars: int
    warning_codes: list[str] = Field(default_factory=list)
    error_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class DocumentExtractionPageResponse(BaseModel):
    id: str
    generation_id: str
    page_number: int
    extraction_method: str
    status: str
    native_text_quality: float | None = None
    text_chars: int
    span_count: int
    rendered_artifact_id: str | None = None
    preview_artifact_id: str | None = None
    retryable: bool
    error_code: str | None = None
    warning_codes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class DocumentExtractionCreateResponse(BaseModel):
    generation: DocumentExtractionGenerationResponse
    artifact: SourceArtifactResponse | None = None
    job: ImportJobResponse | None = None
    mentions: list[ExtractedMentionResponse] = Field(default_factory=list)
    derivation: ArtifactDerivationResponse | None = None
    spans: list[DocumentTextSpanResponse] = Field(default_factory=list)
    pages: list[DocumentExtractionPageResponse] = Field(default_factory=list)
    duplicate_artifact: bool = False
    idempotent_replay: bool = False


class DocumentMentionBoxEvidenceResponse(BaseModel):
    page_number: int
    span_id: str
    block_id: str
    line_id: str
    token_id: str | None = None
    bbox: dict[str, Any]
    extraction_method: str
    reading_order: int


class DocumentMentionEvidenceResponse(BaseModel):
    mention_id: str
    mention_text: str
    start_offset: int
    end_offset: int
    page_numbers: list[int] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    line_ids: list[str] = Field(default_factory=list)
    token_ids: list[str] = Field(default_factory=list)
    bounding_boxes: list[dict[str, Any]] = Field(default_factory=list)
    box_evidence: list[DocumentMentionBoxEvidenceResponse] = Field(default_factory=list)
    extraction_methods: list[str] = Field(default_factory=list)
    geometry_available: bool


class DocumentExtractionEvidenceResponse(BaseModel):
    generation: DocumentExtractionGenerationResponse
    artifact: SourceArtifactResponse
    job: ImportJobResponse
    pages: list[DocumentExtractionPageResponse] = Field(default_factory=list)
    layout_manifest: dict[str, Any] = Field(default_factory=dict)
    span_map: list[dict[str, Any]] = Field(default_factory=list)
    mentions: list[ExtractedMentionResponse] = Field(default_factory=list)
    mention_evidence: list[DocumentMentionEvidenceResponse] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SourceArtifactRecord:
    id: str
    trip_id: str
    artifact_type: str
    mime_type: str
    content_checksum: str
    byte_size: int
    charset: str
    privacy_level: str
    storage_key: str
    original_label: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class ImportJobRecord:
    id: str
    trip_id: str
    artifact_id: str
    input_type: str
    status: str
    extraction_schema_version: str
    extractor_version: str
    resolver_version: str
    review_version: int
    mention_count: int
    warning_codes: list[str]
    error_code: str | None
    committed_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ImportProcessingAttemptRecord:
    id: str
    import_job_id: str
    stage: str
    extractor_version: str | None
    resolver_version: str | None
    status: str
    warning_codes: list[str]
    error_code: str | None
    started_at: str
    completed_at: str | None


class ExtractedMentionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: MentionEntityType
    raw_text: str = Field(..., min_length=1, max_length=240)
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., gt=0)
    normalized_text: str | None = Field(default=None, max_length=240)
    city_hint: str | None = Field(default=None, max_length=80)
    date_hint: str | None = Field(default=None, max_length=80)
    time_hint: str | None = Field(default=None, max_length=80)
    recommendation_reason: str | None = Field(default=None, max_length=240)
    confidence: float = Field(..., ge=0, le=1)
    confidence_basis: str = Field(..., min_length=1, max_length=160)
    extraction_warning_codes: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_offsets(self) -> "ExtractedMentionDraft":
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset.")
        return self


@dataclass(frozen=True, slots=True)
class ExtractedMentionRecord:
    id: str
    import_job_id: str
    artifact_id: str
    entity_type: str
    raw_text: str
    normalized_text: str | None
    start_offset: int
    end_offset: int
    context_before: str
    context_after: str
    city_hint: str | None
    date_hint: str | None
    time_hint: str | None
    recommendation_reason: str | None
    confidence: float
    extraction_warning_codes: list[str]
    content_digest: str
    created_at: str


class TextExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mentions: list[ExtractedMentionDraft] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    extractor_version: str
    processing_summary: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResolvedPlaceCandidateRecord:
    id: str
    mention_id: str
    provider: str
    provider_place_id: str | None
    canonical_name: str
    address_summary: str | None
    administrative_area: str | None
    city_code: str | None
    latitude: float | None
    longitude: float | None
    category: str | None
    confidence: float
    resolution_reason_codes: list[str]
    data_state: str
    candidate_digest: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ImportReviewDecisionRecord:
    id: str
    import_job_id: str
    mention_id: str
    review_version: int
    action: str
    selected_resolution_candidate_id: str | None
    merge_target_mention_id: str | None
    note_text: str | None
    reason_code: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class ImportCommitRecord:
    id: str
    import_job_id: str
    review_version: int
    result_json: dict[str, Any]
    commit_digest: str
    created_at: str


@dataclass(frozen=True, slots=True)
class URLFetchSnapshotRecord:
    id: str
    import_job_id: str
    raw_artifact_id: str
    request_url_sanitized: str
    normalized_request_url: str
    final_url_sanitized: str
    final_url: str
    redirect_chain: list[dict[str, Any]]
    robots_status: str
    robots_checked_at: str
    status_code: int
    content_type: str
    declared_charset: str | None
    effective_charset: str | None
    content_language: str | None
    compressed_bytes: int
    decoded_bytes: int
    body_checksum: str
    header_metadata: dict[str, Any]
    fetcher_version: str
    policy_version: str
    fetched_at: str
    warning_codes: list[str]
    cache_status: str


@dataclass(frozen=True, slots=True)
class ArtifactDerivationRecord:
    id: str
    parent_artifact_id: str
    child_artifact_id: str
    derivation_type: str
    transformer_version: str
    input_checksum: str
    output_checksum: str
    metadata: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class ArtifactInspectionRecord:
    id: str
    trip_id: str
    import_job_id: str
    artifact_id: str
    attempt: int
    schema_version: str
    inspector_version: str
    declared_kind: str
    detected_kind: str
    declared_mime_type: str | None
    detected_mime_type: str
    status: str
    classification: str
    byte_size: int
    content_checksum: str
    metadata: dict[str, Any]
    sanitized_artifact_id: str | None
    manifest_artifact_id: str | None
    warning_codes: list[str]
    error_code: str | None
    started_at: str
    completed_at: str


@dataclass(frozen=True, slots=True)
class ArtifactInspectionFindingRecord:
    id: str
    inspection_id: str
    code: str
    severity: str
    category: str
    evidence: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class DocumentExtractionGenerationRecord:
    id: str
    trip_id: str
    source_import_job_id: str
    source_artifact_id: str
    inspection_id: str
    derived_import_job_id: str | None
    derived_artifact_id: str | None
    layout_artifact_id: str | None
    span_map_artifact_id: str | None
    generation: int
    schema_version: str
    extractor_version: str
    strategy: str
    status: str
    page_count: int
    extracted_text_chars: int
    warning_codes: list[str]
    error_code: str | None
    metadata: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class DocumentExtractionPageRecord:
    id: str
    generation_id: str
    page_number: int
    extraction_method: str
    status: str
    native_text_quality: float | None
    text_chars: int
    span_count: int
    rendered_artifact_id: str | None
    preview_artifact_id: str | None
    retryable: bool
    error_code: str | None
    warning_codes: list[str]
    metadata: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class DocumentTextSpanRecord:
    id: str
    generation_id: str
    span_start: int
    span_end: int
    page_number: int
    block_index: int
    line_index: int
    token_index: int | None
    block_id: str
    line_id: str
    token_id: str | None
    reading_order: int
    bbox: dict[str, Any]
    source_kind: str
    confidence: float | None
    text_digest: str
    warning_codes: list[str]
    created_at: str


def generate_artifact_id() -> str:
    return f"src_{uuid4().hex}"


def generate_import_job_id() -> str:
    return f"imp_{uuid4().hex}"


def generate_import_attempt_id() -> str:
    return f"imp_att_{uuid4().hex}"


def generate_mention_id() -> str:
    return f"men_{uuid4().hex}"


def generate_resolution_candidate_id() -> str:
    return f"res_{uuid4().hex}"


def generate_review_decision_id() -> str:
    return f"imp_dec_{uuid4().hex}"


def generate_import_commit_id() -> str:
    return f"imp_commit_{uuid4().hex}"


def generate_url_fetch_snapshot_id() -> str:
    return f"url_fetch_{uuid4().hex}"


def generate_artifact_derivation_id() -> str:
    return f"art_der_{uuid4().hex}"


def generate_artifact_inspection_id() -> str:
    return f"art_ins_{uuid4().hex}"


def generate_artifact_inspection_finding_id() -> str:
    return f"art_find_{uuid4().hex}"


def generate_document_extraction_generation_id() -> str:
    return f"doc_ext_{uuid4().hex}"


def generate_document_text_span_id() -> str:
    return f"doc_span_{uuid4().hex}"


def generate_document_extraction_page_id() -> str:
    return f"doc_page_{uuid4().hex}"


def source_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalize_mention_text(value: str) -> str:
    return "".join(value.strip().casefold().split())


def mention_content_digest(
    *,
    artifact_id: str,
    entity_type: str,
    raw_text: str,
    start_offset: int,
    end_offset: int,
) -> str:
    return hashlib.sha256(
        f"{artifact_id}|{entity_type}|{raw_text}|{start_offset}|{end_offset}".encode("utf-8")
    ).hexdigest()


def resolution_candidate_digest(
    *,
    provider: str,
    provider_place_id: str | None,
    canonical_name: str,
    latitude: float | None,
    longitude: float | None,
) -> str:
    payload = f"{provider}|{provider_place_id or ''}|{normalize_mention_text(canonical_name)}|{latitude}|{longitude}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_import_transition(current: str, next_status: str) -> bool:
    return next_status in LEGAL_IMPORT_TRANSITIONS.get(current, set())
