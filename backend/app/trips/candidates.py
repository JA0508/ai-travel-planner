from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .digests import sha256_digest


CANDIDATE_SCHEMA_VERSION = "1.0"
MAX_CANDIDATE_TEXT_LENGTH = 160
MAX_EVIDENCE_REFS = 8


class CandidateType(str, Enum):
    PLACE = "place"
    MEAL = "meal"
    ACTIVITY = "activity"


class CandidateSourceKind(str, Enum):
    MANUAL_ENTRY = "manual_entry"
    COMPLETION = "completion"
    PLACE_INTELLIGENCE = "place_intelligence"
    TEXT_IMPORT = "text_import"
    URL_IMPORT = "url_import"
    DOCUMENT_IMPORT = "document_import"


class CandidateDecisionType(str, Enum):
    PENDING = "pending"
    REJECT = "reject"
    DEFER = "defer"
    RESTORE_PENDING = "restore_pending"
    SCHEDULED = "scheduled"


class CandidateDataState(str, Enum):
    KNOWN = "known"
    MISSING = "missing"
    FAILED = "failed"
    ASSUMED = "assumed"
    NOT_REQUESTED = "not_requested"


class CandidateConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class CandidateDecisionReasonCode(str, Enum):
    USER_REJECTED = "USER_REJECTED"
    NOT_INTERESTED = "NOT_INTERESTED"
    DUPLICATE_OF_EXISTING_STOP = "DUPLICATE_OF_EXISTING_STOP"
    DOES_NOT_FIT_TRIP = "DOES_NOT_FIT_TRIP"
    LOCATION_UNCERTAIN = "LOCATION_UNCERTAIN"
    TIME_CONFLICT = "TIME_CONFLICT"
    TOO_FAR = "TOO_FAR"
    OTHER_UNSPECIFIED = "OTHER_UNSPECIFIED"
    USER_DEFERRED = "USER_DEFERRED"
    RESTORED_TO_PENDING = "RESTORED_TO_PENDING"
    SCHEDULED_IN_REVISION = "SCHEDULED_IN_REVISION"
    CANDIDATE_REGISTERED = "CANDIDATE_REGISTERED"


class CandidateCoordinate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class TripCandidateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_type: CandidateType = CandidateType.PLACE
    display_name: str = Field(..., min_length=1, max_length=MAX_CANDIDATE_TEXT_LENGTH)
    canonical_place_id: str | None = Field(default=None, max_length=160)
    provider_place_id: str | None = Field(default=None, max_length=160)
    category: str | None = Field(default=None, max_length=MAX_CANDIDATE_TEXT_LENGTH)
    coordinates: CandidateCoordinate | None = None
    address_summary: str | None = Field(default=None, max_length=MAX_CANDIDATE_TEXT_LENGTH)
    estimated_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    preferred_time_block: str | None = Field(default=None, max_length=32)
    explicit_day_reference: str | None = Field(default=None, max_length=32)
    source_kind: CandidateSourceKind = CandidateSourceKind.MANUAL_ENTRY
    source_ref: str | None = Field(default=None, max_length=160)
    evidence_refs: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_REFS)

    @model_validator(mode="after")
    def validate_text(self) -> "TripCandidateCreateRequest":
        if contains_markup(self.display_name):
            raise ValueError("display_name must be plain structured text.")
        if self.address_summary and contains_markup(self.address_summary):
            raise ValueError("address_summary must be plain structured text.")
        return self


class TripCandidateDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: CandidateDecisionType
    reason_code: CandidateDecisionReasonCode = CandidateDecisionReasonCode.OTHER_UNSPECIFIED
    base_revision_id: str | None = Field(default=None, min_length=1)


class TripCandidateResponse(BaseModel):
    id: str
    trip_id: str
    candidate_type: str
    display_name: str
    normalized_name: str
    canonical_place_id: str | None = None
    provider_place_id: str | None = None
    category: str | None = None
    coordinates: CandidateCoordinate | None = None
    address_summary: str | None = None
    estimated_duration_minutes: int | None = None
    preferred_time_block: str | None = None
    explicit_day_reference: str | None = None
    source_kind: str
    source_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    location_state: str
    route_state: str
    duration_state: str
    confidence: str
    content_digest: str
    workflow_state: str
    latest_decision_id: str | None = None
    created_at: str


class TripCandidateRegistrationResponse(BaseModel):
    candidate: TripCandidateResponse
    deduplicated: bool = False
    idempotent_replay: bool = False


class TripCandidateListResponse(BaseModel):
    candidates: list[TripCandidateResponse]


class TripCandidateDecisionResponse(BaseModel):
    decision: dict[str, Any]
    candidate: TripCandidateResponse
    idempotent_replay: bool = False


@dataclass(slots=True)
class TripCandidateRecord:
    id: str
    trip_id: str
    candidate_type: str
    display_name: str
    normalized_name: str
    canonical_place_id: str | None
    provider_place_id: str | None
    category: str | None
    coordinates: dict[str, float] | None
    address_summary: str | None
    estimated_duration_minutes: int | None
    preferred_time_block: str | None
    explicit_day_reference: str | None
    source_kind: str
    source_ref: str | None
    evidence_refs: list[str]
    location_state: str
    route_state: str
    duration_state: str
    confidence: str
    content_digest: str
    created_at: str


@dataclass(slots=True)
class TripCandidateDecisionRecord:
    id: str
    trip_id: str
    candidate_id: str
    decision_type: str
    reason_code: str
    base_revision_id: str | None
    related_revision_id: str | None
    source: str
    created_at: str


@dataclass(slots=True)
class CandidateRegistrationResult:
    candidate: TripCandidateRecord
    decision: TripCandidateDecisionRecord | None = None
    deduplicated: bool = False
    idempotent_replay: bool = False


@dataclass(slots=True)
class CandidateDecisionResult:
    candidate: TripCandidateRecord
    decision: TripCandidateDecisionRecord
    idempotent_replay: bool = False


def generate_candidate_id() -> str:
    return f"cand_{uuid4().hex}"


def generate_candidate_decision_id() -> str:
    return f"cand_dec_{uuid4().hex}"


def normalize_candidate_name(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().casefold())


def contains_markup(value: str) -> bool:
    return bool(re.search(r"<\s*/?\s*(script|iframe|img|svg|html|body)\b", value, re.I))


def candidate_content_digest(payload: TripCandidateCreateRequest) -> str:
    coordinates = payload.coordinates.model_dump(mode="json") if payload.coordinates else None
    return sha256_digest(
        {
            "normalized_name": normalize_candidate_name(payload.display_name),
            "canonical_place_id": payload.canonical_place_id,
            "provider_place_id": payload.provider_place_id,
            "coordinates": coordinates,
            "candidate_type": payload.candidate_type.value,
            "source_kind": payload.source_kind.value,
            "preferred_time_block": payload.preferred_time_block,
            "explicit_day_reference": payload.explicit_day_reference,
            "address_summary": payload.address_summary,
        }
    )


def build_candidate_record(
    *,
    trip_id: str,
    payload: TripCandidateCreateRequest,
    now: str,
) -> TripCandidateRecord:
    coordinates = payload.coordinates.model_dump(mode="json") if payload.coordinates else None
    duration_state = (
        CandidateDataState.KNOWN.value
        if payload.estimated_duration_minutes is not None
        else CandidateDataState.MISSING.value
    )
    location_state = (
        CandidateDataState.KNOWN.value
        if coordinates is not None
        else CandidateDataState.MISSING.value
    )
    confidence = (
        CandidateConfidence.MEDIUM.value
        if payload.source_kind == CandidateSourceKind.MANUAL_ENTRY
        else CandidateConfidence.HIGH.value
    )
    return TripCandidateRecord(
        id=generate_candidate_id(),
        trip_id=trip_id,
        candidate_type=payload.candidate_type.value,
        display_name=payload.display_name.strip(),
        normalized_name=normalize_candidate_name(payload.display_name),
        canonical_place_id=payload.canonical_place_id,
        provider_place_id=payload.provider_place_id,
        category=payload.category.strip() if payload.category else None,
        coordinates=coordinates,
        address_summary=payload.address_summary.strip() if payload.address_summary else None,
        estimated_duration_minutes=payload.estimated_duration_minutes,
        preferred_time_block=payload.preferred_time_block,
        explicit_day_reference=payload.explicit_day_reference,
        source_kind=payload.source_kind.value,
        source_ref=payload.source_ref,
        evidence_refs=list(payload.evidence_refs),
        location_state=location_state,
        route_state=CandidateDataState.NOT_REQUESTED.value,
        duration_state=duration_state,
        confidence=confidence,
        content_digest=candidate_content_digest(payload),
        created_at=now,
    )


def candidate_to_response(
    candidate: TripCandidateRecord,
    *,
    workflow_state: str,
    latest_decision_id: str | None,
) -> TripCandidateResponse:
    return TripCandidateResponse(
        id=candidate.id,
        trip_id=candidate.trip_id,
        candidate_type=candidate.candidate_type,
        display_name=candidate.display_name,
        normalized_name=candidate.normalized_name,
        canonical_place_id=candidate.canonical_place_id,
        provider_place_id=candidate.provider_place_id,
        category=candidate.category,
        coordinates=CandidateCoordinate.model_validate(candidate.coordinates)
        if candidate.coordinates
        else None,
        address_summary=candidate.address_summary,
        estimated_duration_minutes=candidate.estimated_duration_minutes,
        preferred_time_block=candidate.preferred_time_block,
        explicit_day_reference=candidate.explicit_day_reference,
        source_kind=candidate.source_kind,
        source_ref=candidate.source_ref,
        evidence_refs=candidate.evidence_refs,
        location_state=candidate.location_state,
        route_state=candidate.route_state,
        duration_state=candidate.duration_state,
        confidence=candidate.confidence,
        content_digest=candidate.content_digest,
        workflow_state=workflow_state,
        latest_decision_id=latest_decision_id,
        created_at=candidate.created_at,
    )


def infer_workflow_state(decisions: list[TripCandidateDecisionRecord]) -> tuple[str, str | None]:
    if not decisions:
        return "pending", None
    latest = decisions[-1]
    if latest.decision_type == CandidateDecisionType.REJECT.value:
        return "rejected", latest.id
    if latest.decision_type == CandidateDecisionType.DEFER.value:
        return "deferred", latest.id
    if latest.decision_type == CandidateDecisionType.SCHEDULED.value:
        return "scheduled", latest.id
    return "pending", latest.id
