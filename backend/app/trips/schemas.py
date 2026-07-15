from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas import (
    CompletionTaskActionRequest,
    CompletionTaskActionResponse,
    GenerateFromTripIntentResponse,
    ItineraryRequest,
    ItineraryCompletionOption,
    ItineraryResponse,
    PlanTripFromTextResponse,
    ParsedTripIntentResponse,
    PlanningInputState,
    ReplanItineraryResponse,
    TimeBlockType,
    TravelMode,
    TripIntentEnvelope,
)
from .models import TripMutationProposalRecord, TripRecord, TripRevisionRecord


class TripPlanRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    travel_mode: TravelMode | None = None
    auto_fill_sparse_days: bool = True
    extra_preferences: list[str] = Field(default_factory=list)
    itinerary_request: ItineraryRequest | None = None

    @model_validator(mode="after")
    def validate_single_planning_source(self) -> "TripPlanRequest":
        has_text = bool(self.text and self.text.strip())
        has_itinerary = self.itinerary_request is not None
        if has_text == has_itinerary:
            raise ValueError("Provide exactly one of text or itinerary_request.")
        return self


class TripMetadata(BaseModel):
    id: str
    current_revision_id: str
    revision_count: int
    lifecycle_status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: TripRecord) -> "TripMetadata":
        return cls(
            id=record.id,
            current_revision_id=record.current_revision_id,
            revision_count=record.revision_count,
            lifecycle_status=record.lifecycle_status,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class TripRevisionMetadata(BaseModel):
    id: str
    trip_id: str
    revision_number: int
    parent_revision_id: str | None = None
    base_revision_id: str | None = None
    source_type: str
    snapshot_schema_version: str
    content_digest: str
    parent_lineage_digest: str | None = None
    lineage_digest: str
    planner_run_id: str | None = None
    planner_version: str | None = None
    trace_schema_version: str | None = None
    trace_digest: str | None = None
    restored_from_revision_id: str | None = None
    created_at: str

    @classmethod
    def from_record(cls, record: TripRevisionRecord) -> "TripRevisionMetadata":
        return cls(
            id=record.id,
            trip_id=record.trip_id,
            revision_number=record.revision_number,
            parent_revision_id=record.parent_revision_id,
            base_revision_id=record.base_revision_id,
            source_type=record.source_type,
            snapshot_schema_version=record.snapshot_schema_version,
            content_digest=record.content_digest,
            parent_lineage_digest=record.parent_lineage_digest,
            lineage_digest=record.lineage_digest,
            planner_run_id=record.planner_run_id,
            planner_version=record.planner_version,
            trace_schema_version=record.trace_schema_version,
            trace_digest=record.trace_digest,
            restored_from_revision_id=record.restored_from_revision_id,
            created_at=record.created_at,
        )


class TripPersistenceInfo(BaseModel):
    status: Literal["saved"] = "saved"
    schema_version: str = "1"
    idempotent_replay: bool = False


class TripPlanResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    itinerary: ItineraryResponse
    trip_intent: TripIntentEnvelope | None = None
    parsed_intent: ParsedTripIntentResponse | None = None
    planning_state: PlanningInputState | None = None
    persistence: TripPersistenceInfo


class TripCurrentResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    itinerary: ItineraryResponse
    persistence: TripPersistenceInfo


class TripRevisionListResponse(BaseModel):
    trip: TripMetadata
    revisions: list[TripRevisionMetadata]


class TripRevisionDetailResponse(BaseModel):
    trip: TripMetadata
    revision: TripRevisionMetadata
    itinerary: ItineraryResponse


class PersistedCompletionTaskActionRequest(BaseModel):
    base_revision_id: str = Field(..., min_length=1)
    task_id: str = Field(..., min_length=1)
    task_instance_key: str | None = None
    day: int | None = Field(default=None, ge=1)
    block_type: TimeBlockType | None = None
    selected_candidate: ItineraryCompletionOption | None = None
    completion_candidate_history: list[ItineraryCompletionOption] = Field(default_factory=list)


class PersistedCompletionTaskActionResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    task_result: CompletionTaskActionResponse
    persistence: TripPersistenceInfo


class PersistedReplanRequest(BaseModel):
    base_revision_id: str = Field(..., min_length=1)
    follow_up_text: str = Field(..., min_length=1)
    auto_fill_sparse_days: bool = True


class ApplyPersistedReplanProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision_id: str = Field(..., min_length=1)
    proposal_digest: str = Field(..., min_length=1)


class PersistedReplanResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    replan_result: ReplanItineraryResponse
    persistence: TripPersistenceInfo


class MutationProposalMetadata(BaseModel):
    id: str
    schema_version: str
    operation_type: str
    source_type: str
    base_revision_id: str
    request_digest: str
    instruction_digest: str | None = None
    preview_content_digest: str
    proposal_digest: str
    planner_run_id: str | None = None
    planner_version: str | None = None
    trace_schema_version: str | None = None
    trace_digest: str | None = None
    validation_report: dict
    status: str
    expires_at: str
    applied_revision_id: str | None = None

    @classmethod
    def from_record(cls, record: TripMutationProposalRecord) -> "MutationProposalMetadata":
        return cls(
            id=record.id,
            schema_version=record.proposal_schema_version,
            operation_type=record.operation_type,
            source_type=record.source_type,
            base_revision_id=record.base_revision_id,
            request_digest=record.request_digest,
            instruction_digest=record.instruction_digest,
            preview_content_digest=record.preview_content_digest,
            proposal_digest=record.proposal_digest,
            planner_run_id=record.planner_run_id,
            planner_version=record.planner_version,
            trace_schema_version=record.trace_schema_version,
            trace_digest=record.trace_digest,
            validation_report=record.validation_report,
            status=record.status,
            expires_at=record.expires_at,
            applied_revision_id=record.applied_revision_id,
        )


class PersistedReplanPreviewResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    proposal: MutationProposalMetadata
    replan_result: ReplanItineraryResponse


class UndoPersistedMutationRequest(BaseModel):
    base_revision_id: str = Field(..., min_length=1)


class UndoPersistedMutationResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    itinerary: ItineraryResponse
    persistence: TripPersistenceInfo


class RestoreRevisionRequest(BaseModel):
    base_revision_id: str = Field(..., min_length=1)


class RestoreRevisionResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    itinerary: ItineraryResponse
    persistence: TripPersistenceInfo
