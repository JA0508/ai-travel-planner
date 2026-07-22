from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TripLifecycleStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class TripPlanningPhase(str, Enum):
    """Whether a trip has an executable itinerary revision yet."""

    DRAFT = "draft"
    PLANNED = "planned"


class RevisionSourceType(str, Enum):
    PLANNER_GENERATION = "planner_generation"
    PLANNER_REGENERATION = "planner_regeneration"
    PLANNER_INTENT_HANDOFF = "planner_intent_handoff"
    REPLAN_PATCH = "replan_patch"
    REPLAN_UNDO = "replan_undo"
    COMPLETION_PATCH = "completion_patch"
    COMPLETION_UNDO = "completion_undo"
    ROUTE_EDIT = "route_edit"
    SWAP = "swap"
    CANDIDATE_ADMISSION = "candidate_admission"
    MUTATION_UNDO = "mutation_undo"
    RESTORE = "restore"
    SYSTEM_MIGRATION = "system_migration"


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


@dataclass(slots=True)
class TripRecord:
    id: str
    current_revision_id: str | None
    revision_count: int
    lifecycle_status: str
    planning_phase: str
    capability_hash: str
    created_at: str
    updated_at: str
    draft_version: int = 0


@dataclass(slots=True)
class TripRevisionRecord:
    id: str
    trip_id: str
    revision_number: int
    parent_revision_id: str | None
    base_revision_id: str | None
    source_type: str
    snapshot_schema_version: str
    itinerary_snapshot: dict[str, Any]
    content_digest: str
    parent_lineage_digest: str | None
    lineage_digest: str
    planner_run_id: str | None
    planner_version: str | None
    trace_schema_version: str | None
    trace_digest: str | None
    restored_from_revision_id: str | None
    created_at: str


@dataclass(slots=True)
class RevisionOperationRecord:
    id: str
    trip_id: str
    revision_id: str
    base_revision_id: str | None
    source_type: str
    operation_type: str
    request_digest: str
    idempotency_key_hash: str | None
    actor_type: str
    summary: str
    operation_metadata: dict[str, Any]
    created_at: str


@dataclass(slots=True)
class TripMutationProposalRecord:
    id: str
    trip_id: str
    base_revision_id: str
    proposal_schema_version: str
    source_type: str
    operation_type: str
    request_digest: str
    instruction_digest: str | None
    preview_snapshot_schema_version: str
    preview_snapshot: dict[str, Any]
    preview_content_digest: str
    proposal_digest: str
    planner_run_id: str | None
    planner_version: str | None
    trace_schema_version: str | None
    trace_digest: str | None
    validation_report: dict[str, Any]
    execution_kind: str | None
    command_schema_version: str | None
    mutation_engine_version: str | None
    mutation_kind: str | None
    commands: list[dict[str, Any]] | None
    command_digest: str | None
    impact_summary: dict[str, Any] | None
    invalidated_surfaces: list[str] | None
    status: str
    expires_at: str
    applied_revision_id: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class PlannerHandoffRunRecord:
    id: str
    trip_id: str
    base_trip_revision_id: str
    intent_revision_id: str
    intent_semantic_digest: str
    intent_lineage_digest: str
    input_schema_version: str
    input_snapshot: dict[str, Any]
    input_digest: str
    planner_version: str
    trace_schema_version: str
    trace_snapshot: dict[str, Any]
    trace_digest: str
    result_snapshot_schema_version: str
    result_snapshot: dict[str, Any]
    result_content_digest: str
    validation_report: dict[str, Any]
    proposal_id: str | None
    status: str
    applied_revision_id: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class TripAggregate:
    trip: TripRecord
    current_revision: TripRevisionRecord


@dataclass(slots=True)
class DraftIntentRevisionRecord:
    """An immutable intent contract that intentionally predates Revision 1."""

    id: str
    trip_id: str
    revision_number: int
    parent_draft_intent_revision_id: str | None
    envelope_schema_version: str
    envelope: dict[str, Any]
    content_digest: str
    compiler_version: str
    source_digest: str
    validation_report: dict[str, Any]
    created_at: str


@dataclass(slots=True)
class DraftIntentEditResult:
    revision: DraftIntentRevisionRecord
    previous_intent_revision_id: str
    draft_version: int
    changed: bool
    idempotent_replay: bool = False


@dataclass(slots=True)
class PrePlanHandoffRunRecord:
    """A frozen, reviewable planner result for a Draft Trip."""

    id: str
    trip_id: str
    draft_intent_revision_id: str
    intent_semantic_digest: str
    intent_lineage_digest: str
    input_snapshot: dict[str, Any]
    input_digest: str
    planner_version: str
    trace_schema_version: str
    trace_snapshot: dict[str, Any]
    trace_digest: str
    result_snapshot: dict[str, Any]
    result_content_digest: str
    validation_report: dict[str, Any]
    status: str
    expires_at: str
    applied_revision_id: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class CreateRevisionResult:
    revision: TripRevisionRecord
    idempotent_replay: bool = False


from .candidates import (  # noqa: E402
    CandidateEvidenceLinkRecord,
    CandidateDecisionResult,
    CandidateRegistrationResult,
    TripCandidateDecisionRecord,
    TripCandidateRecord,
)
