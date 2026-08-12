from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .itinerary import ItineraryResponse
from .trip_compiler import TravelIntent


ConstraintKind = Literal[
    "destination", "trip_duration", "arrival_boundary", "departure_boundary",
    "fixed_event", "must_visit", "optional_visit", "pace", "travel_mode",
    "avoidance", "meal_preference", "daily_load",
]
ConstraintStrength = Literal["hard", "soft"]
ConstraintStatus = Literal["satisfied", "unsatisfied", "conflicting", "assumed"]
CandidateStrategy = Literal["relaxed", "balanced", "low_travel"]


class ConstraintSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_fragment_id: str
    source_type: Literal["exact_user_fragment", "user_confirmation", "system_derived"] = "exact_user_fragment"
    resolution_status: Literal["exact", "confirmed", "derived"] = "exact"
    derivation_rule: str | None = None


class ConstraintNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ConstraintKind
    strength: ConstraintStrength
    status: ConstraintStatus
    label: str
    source_refs: list[ConstraintSourceRef] = Field(default_factory=list)


class ConstraintEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_node_id: str
    to_node_id: str
    relationship: Literal["bounds", "requires", "prefers", "conflicts_with", "derived_from"]


class ConstraintGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_digest: str
    nodes: list[ConstraintNode] = Field(default_factory=list)
    edges: list[ConstraintEdge] = Field(default_factory=list)


class ConflictCore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "arrival_after_fixed_event", "fixed_event_overlap",
        "departure_before_required_activity", "insufficient_travel_gap",
    ]
    node_ids: list[str] = Field(min_length=2)
    source_refs: list[ConstraintSourceRef] = Field(default_factory=list)
    explanation: str


class CandidateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixed_coverage: int = Field(ge=0)
    must_coverage: int = Field(ge=0)
    optional_coverage: int = Field(ge=0)
    total_travel_minutes: int | None = Field(default=None, ge=0)
    activity_minutes: int = Field(ge=0)
    max_daily_activity_minutes: int = Field(ge=0)
    free_buffer_minutes: int = Field(ge=0)
    missing_travel_data: bool = False
    minimum_daily_slack_minutes: int = Field(ge=0)
    rushed_day_count: int = Field(ge=0)
    infeasible_day_count: int = Field(ge=0)
    risk_count: int = Field(ge=0)
    travel_data_completeness: Literal["complete", "partial", "missing"] = "missing"
    daily_windows: list[dict[str, Any]] = Field(default_factory=list)


class PlanCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    candidate_hash: str
    strategy: CandidateStrategy
    title: str
    tradeoff_summary: str
    itinerary: ItineraryResponse
    constraint_graph: ConstraintGraph
    applied_constraint_ids: list[str] = Field(default_factory=list)
    relaxed_constraint_ids: list[str] = Field(default_factory=list)
    unsatisfied_constraint_ids: list[str] = Field(default_factory=list)
    metrics: CandidateMetrics


class CandidateComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    highlights: list[str] = Field(default_factory=list)


class PlanningSnapshotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_contract_version: str
    planner_policy_version: str
    metric_policy_version: str
    intent_digest: str
    constraint_graph_digest: str
    poi_snapshot_digest: str
    route_snapshot_digest: str
    strategy_manifest_digest: str
    candidate_set_hash: str
    candidate_count: int = Field(ge=0)


class ReplayDifference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["candidate_count", "candidate_order", "candidate_missing", "candidate_hash", "candidate_metrics", "candidate_itinerary", "candidate_set_hash", "snapshot_digest"]
    candidate_id: str | None = None
    expected: Any
    actual: Any


class ReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["verified", "mismatch", "unsupported_policy_version", "invalid_snapshot", "planning_run_not_found"]
    planning_run_id: str
    planner_policy_version: str | None = None
    expected_candidate_set_hash: str | None = None
    actual_candidate_set_hash: str | None = None
    differences: list[ReplayDifference] = Field(default_factory=list)


class PlanCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: TravelIntent


class PlanCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_digest: str
    constraint_graph: ConstraintGraph
    candidates: list[PlanCandidate] = Field(min_length=1, max_length=3)
    comparison: list[CandidateComparison] = Field(default_factory=list)
    planning_run_id: str | None = None
    status: Literal["generated", "selecting", "selected", "expired", "invalidated"] | None = None
    expires_at: str | None = None


class SelectPlanCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_hash: str = Field(min_length=16)
    intent_digest: str = Field(min_length=16)


class PlanningRunRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planning_run_id: str
    status: Literal["generated", "selecting", "selected", "expired", "invalidated"]
    expires_at: str
    intent_digest: str
    confirmed_intent: TravelIntent
    constraint_graph: ConstraintGraph
    candidates: list[PlanCandidate] = Field(default_factory=list)
    comparison: list[CandidateComparison] = Field(default_factory=list)
    selected_candidate_id: str | None = None
    trip_id: str | None = None


class PlanningRunRecordEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    occurred_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanningRunHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: list[str] = Field(default_factory=list)
    evidence: list[dict[str, str]] = Field(default_factory=list)
    status: Literal["generated", "selecting", "selected", "expired", "invalidated"]
    selected_candidate_id: str | None = None
    trip_id: str | None = None
