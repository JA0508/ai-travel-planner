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
from .models import (
    DraftIntentRevisionRecord,
    PlannerHandoffRunRecord,
    PrePlanHandoffRunRecord,
    TripMutationProposalRecord,
    TripRecord,
    TripRevisionRecord,
)
from .mutation_commands import TripMutationCommandEnvelope


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


class DraftTripCreateRequest(BaseModel):
    """Admission request deliberately contains no itinerary or inferred trip facts."""

    model_config = ConfigDict(extra="forbid")

    direct_user_text: str = Field(..., min_length=1, max_length=10000)


class TripMetadata(BaseModel):
    id: str
    current_revision_id: str | None = None
    revision_count: int
    lifecycle_status: str
    planning_phase: str = "planned"
    draft_version: int = 0
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: TripRecord) -> "TripMetadata":
        return cls(
            id=record.id,
            current_revision_id=record.current_revision_id,
            revision_count=record.revision_count,
            lifecycle_status=record.lifecycle_status,
            planning_phase=record.planning_phase,
            draft_version=record.draft_version,
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


class DraftTripCreateResponse(BaseModel):
    trip: TripMetadata
    persistence: TripPersistenceInfo


class DraftTripDetailResponse(BaseModel):
    trip: TripMetadata
    direct_user_text: str


class DraftIntentRevisionMetadata(BaseModel):
    id: str
    trip_id: str
    revision_number: int
    parent_draft_intent_revision_id: str | None = None
    envelope_schema_version: str
    content_digest: str
    compiler_version: str
    source_digest: str
    created_at: str

    @classmethod
    def from_record(cls, record: DraftIntentRevisionRecord) -> "DraftIntentRevisionMetadata":
        return cls(
            id=record.id,
            trip_id=record.trip_id,
            revision_number=record.revision_number,
            parent_draft_intent_revision_id=record.parent_draft_intent_revision_id,
            envelope_schema_version=record.envelope_schema_version,
            content_digest=record.content_digest,
            compiler_version=record.compiler_version,
            source_digest=record.source_digest,
            created_at=record.created_at,
        )


class PrePlanIntentCompileResponse(BaseModel):
    envelope: dict
    revision: DraftIntentRevisionMetadata
    idempotent_replay: bool = False


class DraftIntentEditResponse(BaseModel):
    draft_trip_id: str
    draft_version: int
    previous_intent_revision_id: str
    latest_intent_revision_id: str
    intent_revision_number: int
    changed: bool
    idempotent_replay: bool = False
    readiness: str
    issue_summary: list[str] = Field(default_factory=list)
    envelope: dict
    revision: DraftIntentRevisionMetadata


class PrePlanIntentLatestResponse(BaseModel):
    trip: TripMetadata
    envelope: dict
    revision: DraftIntentRevisionMetadata


class PrePlanHandoffPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_intent_revision_id: str = Field(..., min_length=1)


class PrePlanHandoffApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_intent_revision_id: str = Field(..., min_length=1)
    handoff_digest: str = Field(..., min_length=1)


class PrePlanHandoffRunMetadata(BaseModel):
    id: str
    trip_id: str
    draft_intent_revision_id: str
    intent_semantic_digest: str
    intent_lineage_digest: str
    input_digest: str
    planner_version: str
    trace_schema_version: str
    trace_digest: str
    result_content_digest: str
    status: str
    expires_at: str
    applied_revision_id: str | None = None
    created_at: str

    @classmethod
    def from_record(cls, record: PrePlanHandoffRunRecord) -> "PrePlanHandoffRunMetadata":
        return cls(
            id=record.id,
            trip_id=record.trip_id,
            draft_intent_revision_id=record.draft_intent_revision_id,
            intent_semantic_digest=record.intent_semantic_digest,
            intent_lineage_digest=record.intent_lineage_digest,
            input_digest=record.input_digest,
            planner_version=record.planner_version,
            trace_schema_version=record.trace_schema_version,
            trace_digest=record.trace_digest,
            result_content_digest=record.result_content_digest,
            status=record.status,
            expires_at=record.expires_at,
            applied_revision_id=record.applied_revision_id,
            created_at=record.created_at,
        )


class PrePlanHandoffPreviewResponse(BaseModel):
    trip: TripMetadata
    draft_intent_revision_id: str
    handoff: PrePlanHandoffRunMetadata
    itinerary: ItineraryResponse
    source_links: list[dict]


class PrePlanHandoffApplyResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    draft_intent_revision_id: str
    handoff: PrePlanHandoffRunMetadata
    itinerary: ItineraryResponse
    persistence: TripPersistenceInfo


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


class ApplyPersistedMutationProposalRequest(BaseModel):
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
    execution_kind: str | None = None
    command_schema_version: str | None = None
    mutation_engine_version: str | None = None
    mutation_kind: str | None = None
    commands: list[dict] | None = None
    command_digest: str | None = None
    impact_summary: dict | None = None
    invalidated_surfaces: list[str] | None = None
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
            execution_kind=record.execution_kind,
            command_schema_version=record.command_schema_version,
            mutation_engine_version=record.mutation_engine_version,
            mutation_kind=record.mutation_kind,
            commands=record.commands,
            command_digest=record.command_digest,
            impact_summary=record.impact_summary,
            invalidated_surfaces=record.invalidated_surfaces,
            status=record.status,
            expires_at=record.expires_at,
            applied_revision_id=record.applied_revision_id,
        )


class PersistedReplanPreviewResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    proposal: MutationProposalMetadata
    replan_result: ReplanItineraryResponse


class PersistedMutationPreviewResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    proposal: MutationProposalMetadata
    itinerary: ItineraryResponse
    impact_summary: dict
    invalidated_surfaces: list[str]
    refresh_targets: list[str]


class PersistedMutationApplyResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    itinerary: ItineraryResponse
    impact_summary: dict | None = None
    invalidated_surfaces: list[str] | None = None
    refresh_targets: list[str] | None = None
    persistence: TripPersistenceInfo


class GoldenPathRepairPreviewRequest(BaseModel):
    """A deliberately narrow intent-only request for the golden-path repair."""

    model_config = ConfigDict(extra="forbid")

    base_revision: str = Field(..., min_length=1)
    target_day: int = Field(..., ge=1)
    goal: Literal["relax_day"]


class GoldenPathRepairApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision: str = Field(..., min_length=1)
    proposal_digest: str = Field(..., min_length=1)


class GoldenPathRepairProposal(BaseModel):
    proposal_id: str
    proposal_digest: str
    base_revision: str
    target_day: int
    moved_activity_id: str
    moved_activity_name: str
    from_day: int
    to_day: int
    before: ItineraryResponse
    after: ItineraryResponse
    protection_summary: str
    execution_evidence: dict[str, int]


class GoldenPathRepairPreviewResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    proposal: GoldenPathRepairProposal


class GoldenPathRepairApplyResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    itinerary: ItineraryResponse
    persistence: TripPersistenceInfo


class PlannerHandoffRunMetadata(BaseModel):
    id: str
    trip_id: str
    base_trip_revision_id: str
    intent_revision_id: str
    intent_semantic_digest: str
    intent_lineage_digest: str
    input_schema_version: str
    input_digest: str
    planner_version: str
    trace_schema_version: str
    trace_digest: str
    result_content_digest: str
    status: str
    proposal_id: str | None = None
    applied_revision_id: str | None = None
    created_at: str

    @classmethod
    def from_record(cls, record: PlannerHandoffRunRecord) -> "PlannerHandoffRunMetadata":
        return cls(
            id=record.id,
            trip_id=record.trip_id,
            base_trip_revision_id=record.base_trip_revision_id,
            intent_revision_id=record.intent_revision_id,
            intent_semantic_digest=record.intent_semantic_digest,
            intent_lineage_digest=record.intent_lineage_digest,
            input_schema_version=record.input_schema_version,
            input_digest=record.input_digest,
            planner_version=record.planner_version,
            trace_schema_version=record.trace_schema_version,
            trace_digest=record.trace_digest,
            result_content_digest=record.result_content_digest,
            status=record.status,
            proposal_id=record.proposal_id,
            applied_revision_id=record.applied_revision_id,
            created_at=record.created_at,
        )


class PlannerHandoffPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision_id: str = Field(..., min_length=1)
    intent_revision_id: str = Field(..., min_length=1)


class ApplyPlannerHandoffProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision_id: str = Field(..., min_length=1)
    intent_revision_id: str = Field(..., min_length=1)
    proposal_digest: str = Field(..., min_length=1)


class PlannerHandoffPreviewResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    intent_revision_id: str
    planner_run: PlannerHandoffRunMetadata
    proposal: MutationProposalMetadata
    itinerary: ItineraryResponse
    source_links: list[dict]


class PlannerHandoffApplyResponse(BaseModel):
    trip: TripMetadata
    current_revision: TripRevisionMetadata
    intent_revision_id: str
    planner_run: PlannerHandoffRunMetadata
    itinerary: ItineraryResponse
    persistence: TripPersistenceInfo


class PersistedMutationPreviewRequest(TripMutationCommandEnvelope):
    pass


class LocalRepairPreviewRequest(BaseModel):
    """A user goal; the server, not the browser, determines the mutation command."""

    model_config = ConfigDict(extra="forbid")

    base_revision_id: str = Field(..., min_length=1)
    target_day: int = Field(..., ge=1)
    goal: Literal["relax_day"]


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
