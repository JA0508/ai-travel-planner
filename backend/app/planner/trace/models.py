from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .reason_codes import PlannerReasonCode
from .versions import PLANNER_TRACE_SCHEMA_VERSION, PLANNER_VERSION

JsonScalar = str | int | float | bool | None
JsonValue = Any


class PlannerDecisionStage(str, Enum):
    INTENT_NORMALIZATION = "intent_normalization"
    CANDIDATE_DISCOVERY = "candidate_discovery"
    IDENTITY_RESOLUTION = "identity_resolution"
    CANDIDATE_VALIDATION = "candidate_validation"
    CONSTRAINT_CHECK = "constraint_check"
    CANDIDATE_RANKING = "candidate_ranking"
    DAY_ASSIGNMENT = "day_assignment"
    TIME_BLOCK_ASSIGNMENT = "time_block_assignment"
    ROUTE_EVALUATION = "route_evaluation"
    SCHEDULE_COMMIT = "schedule_commit"
    RESULT_VALIDATION = "result_validation"


class PlannerSubjectType(str, Enum):
    REQUEST = "request"
    INTENT = "intent"
    CANDIDATE = "candidate"
    FIXED_EVENT = "fixed_event"
    AVAILABILITY_WINDOW = "availability_window"
    PLANNING_ANCHOR = "planning_anchor"
    ROUTE_SEGMENT = "route_segment"
    SCHEDULED_ITEM = "scheduled_item"
    RESULT = "result"


class PlannerDecision(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    SKIPPED = "skipped"
    FALLBACK_USED = "fallback_used"
    WARNING = "warning"


class PlannerInputSnapshot(BaseModel):
    city: str | None = None
    trip_days: int | None = Field(default=None, ge=1)
    trip_days_source: str | None = None
    travel_mode: str | None = None
    scenic_seed_count: int = Field(default=0, ge=0)
    restaurant_seed_count: int = Field(default=0, ge=0)
    fixed_event_count: int = Field(default=0, ge=0)
    availability_window_count: int = Field(default=0, ge=0)
    has_hotel: bool = False
    has_arrival_anchor: bool = False
    has_departure_anchor: bool = False
    preference_count: int = Field(default=0, ge=0)
    raw_text_ref: str | None = None


class ProviderRouteSnapshot(BaseModel):
    origin_id: str
    destination_id: str
    travel_mode: str
    duration_seconds: int | None = Field(default=None, ge=0)
    distance_meters: int | None = Field(default=None, ge=0)
    availability: str


class ProviderSnapshotSummary(BaseModel):
    place_known_count: int = Field(default=0, ge=0)
    place_missing_count: int = Field(default=0, ge=0)
    place_failed_count: int = Field(default=0, ge=0)
    route_known_count: int = Field(default=0, ge=0)
    route_missing_count: int = Field(default=0, ge=0)
    route_failed_count: int = Field(default=0, ge=0)
    route_not_requested_count: int = Field(default=0, ge=0)
    routes: list[ProviderRouteSnapshot] = Field(default_factory=list)


class PlannerDecisionEvent(BaseModel):
    sequence: int = Field(..., ge=1)
    stage: PlannerDecisionStage
    subject_type: PlannerSubjectType
    subject_id: str
    decision: PlannerDecision
    reason_codes: list[PlannerReasonCode] = Field(default_factory=list)
    metrics: dict[str, JsonValue] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)


class PlannerTraceWarning(BaseModel):
    code: str
    stage: PlannerDecisionStage | None = None
    subject_id: str | None = None
    recoverable: bool = True
    detail: str | None = None


class PlannerResultSummary(BaseModel):
    status: str
    trip_days: int = Field(..., ge=1)
    scheduled_item_count: int = Field(..., ge=0)
    fixed_event_count: int = Field(default=0, ge=0)
    auto_seeded_count: int = Field(default=0, ge=0)
    auto_filled_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    scheduled_item_refs: list[str] = Field(default_factory=list)


class PlannerTrace(BaseModel):
    schema_version: str = PLANNER_TRACE_SCHEMA_VERSION
    planner_version: str = PLANNER_VERSION
    planner_run_id: str
    trace_digest: str | None = None
    volatile_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    input_summary: PlannerInputSnapshot
    provider_summary: ProviderSnapshotSummary = Field(default_factory=ProviderSnapshotSummary)
    decisions: list[PlannerDecisionEvent] = Field(default_factory=list)
    result_summary: PlannerResultSummary
    warnings: list[PlannerTraceWarning] = Field(default_factory=list)

    def deterministic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "planner_version": self.planner_version,
            "input_summary": self.input_summary.model_dump(mode="json"),
            "provider_summary": self.provider_summary.model_dump(mode="json"),
            "decisions": [event.model_dump(mode="json") for event in self.decisions],
            "result_summary": self.result_summary.model_dump(mode="json"),
            "warnings": [
                warning.model_dump(mode="json", exclude={"detail"})
                for warning in self.warnings
            ],
        }
