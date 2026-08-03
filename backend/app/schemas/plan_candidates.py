from __future__ import annotations

from typing import Literal

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


class PlanCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: TravelIntent


class PlanCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_digest: str
    constraint_graph: ConstraintGraph
    candidates: list[PlanCandidate] = Field(min_length=1, max_length=3)
    comparison: list[CandidateComparison] = Field(default_factory=list)


class SelectPlanCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_hash: str = Field(min_length=16)
    intent_digest: str = Field(min_length=16)
