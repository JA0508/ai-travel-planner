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
MAX_CONTEXT_CHARS = 80


class ImportJobStatus(str, Enum):
    CREATED = "created"
    EXTRACTING = "extracting"
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
    ImportJobStatus.CREATED.value: {ImportJobStatus.EXTRACTING.value, ImportJobStatus.CANCELLED.value},
    ImportJobStatus.EXTRACTING.value: {
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
    artifact_type: Literal["text"]
    mime_type: Literal["text/plain"]
    content_checksum: str
    byte_size: int
    charset: Literal["utf-8"]
    privacy_level: str
    original_label: str | None = None
    created_at: str


class ImportJobResponse(BaseModel):
    id: str
    trip_id: str
    artifact_id: str
    input_type: Literal["text"]
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


class ImportReviewResponse(BaseModel):
    artifact: SourceArtifactResponse
    job: ImportJobResponse
    mentions: list[ExtractedMentionResponse]


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
