from enum import Enum

from pydantic import BaseModel, Field, PrivateAttr

from .availability import AvailabilityWindow
from .intent import IntentDisambiguationSummary, ParsedFixedEvent
from .preference_policy import PlannerPreferencePolicy


class TimeStateType(str, Enum):
    FIXED_DURATION = "fixed_duration"
    SEMI_FIXED_DURATION = "semi_fixed_duration"
    FLEXIBLE_DURATION = "flexible_duration"


class HotelStateType(str, Enum):
    KNOWN = "known"
    ROUGHLY_KNOWN = "roughly_known"
    UNKNOWN = "unknown"


class AnchorStateType(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"


class POIStateType(str, Enum):
    EXPLICIT_POIS = "explicit_pois"
    PARTIAL_POIS = "partial_pois"
    MOSTLY_PREFERENCE_DRIVEN = "mostly_preference_driven"


class FixedEventStateType(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"


class PreferenceMode(str, Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"


class PreferenceStrength(str, Enum):
    WEAK = "weak"
    STRONG = "strong"


class TripScopeEstimationMode(str, Enum):
    EXPLICIT = "explicit"
    ESTIMATED = "estimated"


class TripScopeConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class POILoadLevel(str, Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    DENSE = "dense"


class IntentReadinessLevel(str, Enum):
    READY = "ready"
    NEEDS_ASSUMPTION = "needs_assumption"
    NEEDS_CLARIFICATION = "needs_clarification"


class IntentReadinessIssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class IntentReadinessIssue(BaseModel):
    code: str
    severity: IntentReadinessIssueSeverity
    message: str
    can_auto_assume: bool = True


class IntentReadinessAssessment(BaseModel):
    level: IntentReadinessLevel
    can_generate: bool
    issue_count: int = Field(..., ge=0)
    issues: list[IntentReadinessIssue] = Field(default_factory=list)
    auto_assumptions: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    summary: str


class PreferenceState(BaseModel):
    mode: PreferenceMode
    strength: PreferenceStrength
    extracted_preferences: list[str] = Field(default_factory=list)


class TripScopeEstimate(BaseModel):
    estimated_trip_days: int = Field(..., ge=1)
    estimation_mode: TripScopeEstimationMode
    confidence: TripScopeConfidence
    poi_load_level: POILoadLevel
    reasoning_summary: str


class PlanningInputState(BaseModel):
    city: str | None = None
    trip_days: int | None = Field(default=None, ge=1)
    hotel: str | None = None
    arrival_anchor: str | None = None
    departure_anchor: str | None = None
    availability_windows: list[AvailabilityWindow] = Field(default_factory=list)
    scenic_spots: list[str] = Field(default_factory=list)
    restaurants: list[str] = Field(default_factory=list)
    fixed_events: list[ParsedFixedEvent] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    style_preferences: list[str] = Field(default_factory=list)
    style_preference_sources: dict[str, str] = Field(default_factory=dict)
    disambiguation_summary: IntentDisambiguationSummary | None = None
    _style_preference_evidence: dict[str, str] = PrivateAttr(default_factory=dict)
    time_state: TimeStateType
    hotel_state: HotelStateType
    arrival_anchor_state: AnchorStateType
    departure_anchor_state: AnchorStateType
    poi_state: POIStateType
    fixed_event_state: FixedEventStateType
    preference_state: PreferenceState
    preference_policy: PlannerPreferencePolicy
    trip_scope_estimate: TripScopeEstimate
    readiness: IntentReadinessAssessment
