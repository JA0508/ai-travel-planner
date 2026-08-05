from __future__ import annotations

from datetime import time
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .availability import AvailabilityWindow
from .intent import ParsedFixedEvent, ParsedTripIntentResponse
from .planning_state import PlanningInputState, TripScopeEstimate


class POIType(str, Enum):
    SCENIC = "scenic"
    RESTAURANT = "restaurant"
    HOTEL = "hotel"


class TimeBlockType(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class TravelMode(str, Enum):
    AIRPLANE = "airplane"
    HIGH_SPEED_RAIL = "high_speed_rail"
    RAIL = "rail"
    CAR = "car"
    UNDECIDED = "undecided"


class VerifiedPlaceRef(BaseModel):
    """A confirmed provider place identity that planning must reuse verbatim."""

    model_config = ConfigDict(extra="forbid")

    stable_id: str
    original_name: str
    canonical_name: str = Field(min_length=1, max_length=180)
    provider: Literal["amap"]
    provider_place_id: str = Field(min_length=1, max_length=180)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    category: str | None = None
    source_fragment_ids: list[str] = Field(default_factory=list)


class RoutePreviewMode(str, Enum):
    WALK = "walk"
    TRANSIT = "transit"
    DRIVE = "drive"


class TripDaysInputSource(str, Enum):
    EXPLICIT = "explicit"
    INTERACTION_ESTIMATED = "interaction_estimated"


class TripIntentEnvelopeSource(str, Enum):
    DIRECT_GENERATE = "direct_generate"
    INITIAL_TEXT = "initial_text"
    FOLLOW_UP = "follow_up"
    REGENERATE = "regenerate"


class ScheduledPOISourceType(str, Enum):
    USER_SEED = "user_seed"
    USER_FIXED = "user_fixed"
    AUTO_SEEDED_POI = "auto_seeded_poi"
    AUTO_SEEDED_MEAL = "auto_seeded_meal"
    AUTO_FILLED = "auto_filled"


class POIVisitStyle(str, Enum):
    MUSEUM = "museum"
    NIGHT_VIEW = "night_view"
    OLD_STREET = "old_street"
    WATERFRONT = "waterfront"
    TEMPLE_PARK = "temple_park"
    FOOD_STOP = "food_stop"
    FOOD_DISTRICT = "food_district"
    LANDMARK = "landmark"
    LEISURE_DISTRICT = "leisure_district"
    GENERAL = "general"


class POIProfile(BaseModel):
    visit_style: POIVisitStyle
    best_time_blocks: list[TimeBlockType] = Field(default_factory=list)
    typical_duration_minutes: int = Field(..., gt=0, le=1440)
    intensity: str = Field(default="medium")
    signal_source: str = Field(default="heuristic")
    signal_summary: str | None = None


class FixedConstraint(BaseModel):
    fixed_day: int | None = Field(default=None, ge=1)
    fixed_time_start: time | None = None
    fixed_time_end: time | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "FixedConstraint":
        if (self.fixed_time_start is None) ^ (self.fixed_time_end is None):
            raise ValueError(
                "fixed_time_start and fixed_time_end must be provided together."
            )
        if (
            self.fixed_time_start is not None
            and self.fixed_time_end is not None
            and self.fixed_time_start >= self.fixed_time_end
        ):
            raise ValueError("fixed_time_start must be earlier than fixed_time_end.")
        return self


class RawPOIInput(FixedConstraint):
    name: str = Field(..., min_length=1, description="User-provided place name.")
    # A formal intent handoff can carry an already reviewed canonical place.  These
    # fields let the deterministic planner reuse that identity instead of doing a
    # second name-only provider lookup.
    candidate_id: str | None = Field(default=None, min_length=1)
    canonical_place_id: str | None = Field(default=None, min_length=1)
    resolved_latitude: float | None = Field(default=None, ge=-90, le=90)
    resolved_longitude: float | None = Field(default=None, ge=-180, le=180)
    resolved_duration_minutes: int | None = Field(default=None, gt=0, le=1440)
    # The planner keeps its existing source_type categories. This optional label
    # carries the confirmed intent distinction through scheduling and persistence
    # so the route UI does not collapse must-visit and flexible places.
    intent_ownership: Literal["user_must", "user_optional"] | None = None
    verified_place: VerifiedPlaceRef | None = None

    @model_validator(mode="after")
    def validate_resolved_coordinates(self) -> "RawPOIInput":
        if (self.resolved_latitude is None) != (self.resolved_longitude is None):
            raise ValueError("resolved_latitude and resolved_longitude must be provided together.")
        return self


class ScenicSpotInput(RawPOIInput):
    pass


class RestaurantInput(RawPOIInput):
    pass


class HotelInput(BaseModel):
    name: str = Field(..., min_length=1, description="User-provided hotel name.")


class ItineraryRequest(BaseModel):
    city: str | None = Field(
        default=None,
        min_length=1,
        description="Optional parsed city used to bootstrap sparse natural-language requests.",
    )
    scenic_spots: list[ScenicSpotInput] = Field(default_factory=list)
    restaurants: list[RestaurantInput] = Field(default_factory=list)
    hotel: HotelInput | None = None
    travel_mode: TravelMode | None = None
    arrival_anchor: str | None = Field(default=None, min_length=1)
    departure_anchor: str | None = Field(default=None, min_length=1)
    availability_windows: list[AvailabilityWindow] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    rejected_scenic_spots: list[str] = Field(
        default_factory=list,
        description="User-rejected scenic POIs that should not be reintroduced as carry-forward intent.",
    )
    rejected_restaurants: list[str] = Field(
        default_factory=list,
        description="User-rejected restaurants that should not be reintroduced as carry-forward intent.",
    )
    confirmed_replacements: list["UserConfirmedReplacement"] = Field(
        default_factory=list,
        description="User-confirmed local swaps promoted into trip intent.",
    )
    auto_fill_sparse_days: bool = Field(
        default=False,
        description=(
            "Optionally insert top completion candidates into empty sparse-day blocks "
            "after the first itinerary skeleton is generated."
        ),
    )
    trip_days: int | None = Field(
        default=None,
        ge=1,
        description="Optional user-provided number of days. Scheduler estimates if absent.",
    )
    trip_days_source: TripDaysInputSource | None = Field(
        default=None,
        description=(
            "Whether trip_days came directly from the user or from the natural-language "
            "interaction layer. Omitted keeps legacy behavior."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_optional_hotel(cls, data):
        if not isinstance(data, dict):
            return data

        hotel = data.get("hotel")
        if isinstance(hotel, dict) and not str(hotel.get("name") or "").strip():
            normalized = dict(data)
            normalized["hotel"] = None
            return normalized

        return data


class AvailabilityPreviewRequest(BaseModel):
    trip_days: int = Field(..., ge=1)
    availability_windows: list[AvailabilityWindow] = Field(default_factory=list)


class AvailabilityPreviewDay(BaseModel):
    day: int = Field(..., ge=1)
    availability_summary: DayAvailabilitySummary


class AvailabilityPreviewResponse(BaseModel):
    trip_days: int = Field(..., ge=1)
    days: list[AvailabilityPreviewDay] = Field(default_factory=list)


class NormalizedPOI(FixedConstraint):
    name: str
    type: POIType
    city: str | None = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    duration_minutes: int = Field(..., gt=0, le=1440)
    profile: POIProfile
    # These fields are optional for legacy free-text planning. A confirmed
    # intent handoff supplies them so a scheduled item can retain its source.
    candidate_id: str | None = Field(default=None, min_length=1)
    canonical_place_id: str | None = Field(default=None, min_length=1)
    intent_ownership: Literal["user_must", "user_optional"] | None = None
    verified_place: VerifiedPlaceRef | None = None


class HotelStay(BaseModel):
    name: str
    city: str | None = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class PlanningCandidateTrace(BaseModel):
    name: str
    type: POIType
    rank: int | None = Field(default=None, ge=1)
    score: int | None = None
    status: str
    reason: str


class POIResearchSummary(BaseModel):
    overview: str
    access_tip: str
    practical_tip: str
    best_for: str
    source: str = "route_context"


class ScheduledPOI(BaseModel):
    stable_id: str | None = Field(
        default=None,
        min_length=1,
        description="Stable scheduled-item identity for TripRevision mutation commands.",
    )
    name: str
    type: POIType
    city: str | None = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    duration_minutes: int = Field(..., gt=0, le=1440)
    day: int = Field(..., ge=1)
    start_time: time
    end_time: time
    is_fixed: bool
    placement_reason: str | None = None
    source_type: ScheduledPOISourceType = ScheduledPOISourceType.USER_SEED
    source_label: str | None = None
    source_reason: str | None = None
    travel_from_name: str | None = None
    travel_distance_m: int | None = None
    travel_duration_s: int | None = None
    travel_calculation_status: str | None = None
    selection_top_candidates: list[PlanningCandidateTrace] = Field(default_factory=list)
    selection_rejected_candidates: list[PlanningCandidateTrace] = Field(default_factory=list)
    poi_research: POIResearchSummary | None = None
    candidate_id: str | None = None
    canonical_place_id: str | None = None
    verified_place: VerifiedPlaceRef | None = None
    travel_from_place_id: str | None = None
    travel_to_place_id: str | None = None
    travel_provider: str | None = None
    travel_data_status: Literal["confirmed", "unavailable", "estimated"] | None = None
    candidate_provenance: dict[str, Any] | None = None
    local_edit: dict[str, Any] | None = None


class DayTimeBlock(BaseModel):
    block_type: TimeBlockType
    start_time: time
    end_time: time
    items: list[ScheduledPOI] = Field(default_factory=list)


class RemainingBlockWindow(BaseModel):
    block_type: TimeBlockType
    start_time: time
    end_time: time


class DayAvailabilitySummary(BaseModel):
    was_trimmed: bool = False
    effective_start: time | None = None
    effective_end: time | None = None
    remaining_blocks: list[RemainingBlockWindow] = Field(default_factory=list)


class DayItinerary(BaseModel):
    day: int = Field(..., ge=1)
    hotel: HotelStay
    availability_summary: DayAvailabilitySummary = Field(
        default_factory=DayAvailabilitySummary
    )
    blocks: list[DayTimeBlock] = Field(default_factory=list)


class BoundaryInfluenceExplanation(BaseModel):
    arrival_anchor_influenced: bool = False
    arrival_anchor_name: str | None = None
    arrival_poi_name: str | None = None
    departure_anchor_influenced: bool = False
    departure_anchor_name: str | None = None
    departure_poi_name: str | None = None


class PlanningAnchorSource(BaseModel):
    source_type: str
    source_name: str
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class StayOption(BaseModel):
    option_title: str
    suggested_area_label: str
    fit_label: str
    anchor_pois: list[str] = Field(default_factory=list)
    reasoning_summary: str
    itinerary_relation_summary: str
    area_source: str | None = None


class StayRecommendation(BaseModel):
    recommendation_type: str = "suggested_options"
    recommendation_title: str = "住宿区域建议"
    options: list[StayOption] = Field(default_factory=list)


class DepartureRecommendation(BaseModel):
    recommendation_title: str = "离开枢纽建议"
    options: list["DepartureOption"] = Field(default_factory=list)


class DepartureHubCandidateTrace(BaseModel):
    name: str
    category: str
    rank: int | None = Field(default=None, ge=1)
    distance_km: float | None = Field(default=None, ge=0)
    status: str
    reason: str


class DepartureHubDecisionTrace(BaseModel):
    selected_hub_name: str
    preferred_mode: TravelMode | None = None
    target_summary: str
    selection_rule: str
    top_candidates: list[DepartureHubCandidateTrace] = Field(default_factory=list)
    rejected_candidates: list[DepartureHubCandidateTrace] = Field(default_factory=list)


class DepartureOption(BaseModel):
    option_title: str
    fit_label: str
    suggested_departure_label: str
    anchor_pois: list[str] = Field(default_factory=list)
    reasoning_summary: str
    itinerary_relation_summary: str
    decision_trace: DepartureHubDecisionTrace | None = None


class JourneyApproachSuggestion(BaseModel):
    recommendation_title: str
    recommended_mode: TravelMode
    recommended_hub_name: str | None = None
    fit_label: str
    suggested_area_label: str
    anchor_pois: list[str] = Field(default_factory=list)
    reasoning_summary: str
    itinerary_relation_summary: str


class JourneyApproachRecommendation(BaseModel):
    recommendation_title: str = "推荐到达与离开方式"
    arrival: JourneyApproachSuggestion | None = None
    departure: JourneyApproachSuggestion | None = None


class SparseDaySummary(BaseModel):
    day: int = Field(..., ge=1)
    item_count: int = Field(..., ge=0)
    missing_blocks: list[TimeBlockType] = Field(default_factory=list)


class CompletionCandidateTrace(BaseModel):
    name: str
    type: POIType
    rank: int | None = Field(default=None, ge=1)
    score: int | None = None
    status: str
    reason: str


class CompletionDecisionEvidence(BaseModel):
    why_gap_exists: str
    why_this_poi_fits: str
    alternatives_rejected: str
    top_candidates: list[CompletionCandidateTrace] = Field(default_factory=list)
    rejected_candidates: list[CompletionCandidateTrace] = Field(default_factory=list)


class ItineraryCompletionOption(BaseModel):
    name: str
    type: POIType
    suggested_day: int = Field(..., ge=1)
    suggested_block: TimeBlockType
    reasoning_summary: str
    itinerary_relation_summary: str
    decision_evidence: CompletionDecisionEvidence | None = None


class ItineraryCompletionRecommendation(BaseModel):
    recommendation_title: str = "这趟旅行还可以继续补齐"
    summary: str
    sparse_days: list[SparseDaySummary] = Field(default_factory=list)
    options: list[ItineraryCompletionOption] = Field(default_factory=list)


class CompletionScoreFactor(BaseModel):
    code: str
    label: str
    value: int | str | None = None
    impact: int | None = None


class CompletionScoreBreakdown(BaseModel):
    density: int = Field(..., ge=0, le=100)
    density_reason: str
    density_signals: list[CompletionScoreFactor] = Field(default_factory=list)
    density_penalties: list[CompletionScoreFactor] = Field(default_factory=list)
    meals: int = Field(..., ge=0, le=100)
    meals_reason: str
    meals_signals: list[CompletionScoreFactor] = Field(default_factory=list)
    meals_penalties: list[CompletionScoreFactor] = Field(default_factory=list)
    evening: int = Field(..., ge=0, le=100)
    evening_reason: str
    evening_signals: list[CompletionScoreFactor] = Field(default_factory=list)
    evening_penalties: list[CompletionScoreFactor] = Field(default_factory=list)
    transport_boundary: int = Field(..., ge=0, le=100)
    transport_boundary_reason: str
    transport_boundary_signals: list[CompletionScoreFactor] = Field(default_factory=list)
    transport_boundary_penalties: list[CompletionScoreFactor] = Field(default_factory=list)


class CompletionTaskCard(BaseModel):
    task_id: str
    task_instance_key: str | None = None
    title: str
    reason: str
    action_label: str
    action_prompt: str
    priority: str = "medium"


class CompletionIntelligenceSummary(BaseModel):
    trip_completeness: int = Field(..., ge=0, le=100)
    score_breakdown: CompletionScoreBreakdown
    action_tasks: list[CompletionTaskCard] = Field(default_factory=list)
    sparse_blocks_detected: list[str] = Field(default_factory=list)
    auto_filled_scenic_count: int = Field(..., ge=0)
    auto_filled_meal_count: int = Field(..., ge=0)
    auto_filled_evening_count: int = Field(..., ge=0)
    auto_fill_attempted: bool = False
    auto_fill_blocked_reasons: list[str] = Field(default_factory=list)
    stay_area_recommendation: str | None = None
    departure_hub_recommendation: str | None = None
    why_this_plan_works: list[str] = Field(default_factory=list)


class UserConfirmedReplacement(BaseModel):
    original_name: str
    original_type: POIType
    replacement_name: str
    replacement_type: POIType
    source: str = "swap"
    reasoning_summary: str | None = None


class RegenerationIntentSummary(BaseModel):
    city: str | None = None
    travel_mode: TravelMode | None = None
    hotel: str | None = None
    arrival_anchor: str | None = None
    departure_anchor: str | None = None
    availability_windows: list[AvailabilityWindow] = Field(default_factory=list)
    trip_days: int | None = Field(
        default=None,
        ge=1,
        description="Explicit trip_days to carry into regeneration. None keeps duration flexible.",
    )
    suggested_trip_days: int = Field(
        ...,
        ge=1,
        description="Current executable day count that can be pinned in a later regenerate flow.",
    )
    trip_days_basis: str
    flexible_scenic_spots: list[str] = Field(default_factory=list)
    flexible_restaurants: list[str] = Field(default_factory=list)
    fixed_events: list[ParsedFixedEvent] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    style_preferences: list[str] = Field(default_factory=list)
    style_preference_sources: dict[str, str] = Field(default_factory=dict)
    auto_seeded_scenic_spots: list[str] = Field(default_factory=list)
    auto_seeded_restaurants: list[str] = Field(default_factory=list)
    carry_forward_scenic_spots: list[str] = Field(default_factory=list)
    carry_forward_restaurants: list[str] = Field(default_factory=list)
    rejected_scenic_spots: list[str] = Field(default_factory=list)
    rejected_restaurants: list[str] = Field(default_factory=list)
    confirmed_replacements: list[UserConfirmedReplacement] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReplanItineraryRequest(BaseModel):
    base_intent: RegenerationIntentSummary | None = Field(
        default=None,
        description="Legacy regenerate brief. Prefer trip_intent.current_intent when available.",
    )
    trip_intent: Optional["TripIntentEnvelope"] = Field(
        default=None,
        description="Current rolling trip intent envelope. Its current_intent is used as the replan base.",
    )
    follow_up_text: str = Field(
        ...,
        min_length=1,
        description=(
            "Natural-language follow-up that adjusts the current regenerate brief "
            "without rebuilding the whole trip from scratch."
        ),
    )
    auto_fill_sparse_days: bool = Field(
        default=True,
        description=(
            "Whether the replan path should continue auto-filling sparse blocks "
            "after rebuilding the itinerary skeleton."
        ),
    )


class PlanTripFromTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Free-form trip planning text.")
    travel_mode: TravelMode | None = None
    auto_fill_sparse_days: bool = True
    extra_preferences: list[str] = Field(
        default_factory=list,
        description=(
            "Frontend-only rhythm/taste hints such as pacing or learned swap preferences. "
            "They are merged into parsed preferences before deterministic planning."
        ),
    )


class TripIntentPatch(BaseModel):
    city: str | None = None
    travel_mode: TravelMode | None = None
    hotel: str | None = None
    arrival_anchor: str | None = None
    departure_anchor: str | None = None
    availability_windows: list[AvailabilityWindow] | None = None
    trip_days: int | None = Field(default=None, ge=1)
    flexible_scenic_spots: list[str] | None = None
    flexible_restaurants: list[str] | None = None
    fixed_events: list[ParsedFixedEvent] | None = None
    preferences: list[str] | None = None
    rejected_scenic_spots: list[str] | None = None
    rejected_restaurants: list[str] | None = None
    confirmed_replacements: list[UserConfirmedReplacement] | None = None


class GenerateFromTripIntentRequest(BaseModel):
    trip_intent: "TripIntentEnvelope"
    intent_patch: TripIntentPatch | None = Field(
        default=None,
        description="Optional structured UI/manual edits to apply to current_intent before compiling.",
    )
    auto_fill_sparse_days: bool = True
    trip_days_override: int | None = Field(
        default=None,
        ge=1,
        description="Optional user-pinned day count for this regeneration.",
    )
    extra_preferences: list[str] = Field(
        default_factory=list,
        description="Frontend rhythm/taste hints to merge into the current intent before regeneration.",
    )


class FollowUpInterpretationSummary(BaseModel):
    raw_text: str
    destination_changed_to: str | None = None
    pinned_trip_days: int | None = Field(default=None, ge=1)
    added_scenic_spots: list[str] = Field(default_factory=list)
    added_restaurants: list[str] = Field(default_factory=list)
    removed_scenic_spots: list[str] = Field(default_factory=list)
    removed_restaurants: list[str] = Field(default_factory=list)
    added_fixed_events: list[ParsedFixedEvent] = Field(default_factory=list)
    added_availability_windows: list[AvailabilityWindow] = Field(default_factory=list)
    added_preferences: list[str] = Field(default_factory=list)
    summary_lines: list[str] = Field(default_factory=list)


class PlanningDecisionTraceEvidence(BaseModel):
    why_included: str
    timing_decision: str
    ownership_signal: str
    flexibility: str
    top_candidates: list[PlanningCandidateTrace] = Field(default_factory=list)
    rejected_candidates: list[PlanningCandidateTrace] = Field(default_factory=list)


class PlanningExecutionTraceItem(BaseModel):
    item_name: str
    item_type: POIType
    day: int = Field(..., ge=1)
    block_type: TimeBlockType
    source_type: ScheduledPOISourceType
    decision_type: str
    decision_stage: str
    ownership_type: str
    timing_role: str
    is_user_owned: bool
    is_hard_constraint: bool
    is_editable: bool
    summary: str
    evidence: PlanningDecisionTraceEvidence


class PlanningAssumptionSummary(BaseModel):
    destination: str | None = None
    trip_days_basis: str
    trip_scope_estimate: TripScopeEstimate | None = None
    user_seed_scenic_count: int = Field(..., ge=0)
    user_seed_restaurant_count: int = Field(..., ge=0)
    fixed_event_count: int = Field(..., ge=0)
    availability_window_count: int = Field(..., ge=0)
    auto_seeded_poi_count: int = Field(..., ge=0)
    auto_seeded_meal_count: int = Field(..., ge=0)
    auto_filled_count: int = Field(..., ge=0)
    meal_structure_applied: bool = True
    summary_lines: list[str] = Field(default_factory=list)
    execution_trace: list[PlanningExecutionTraceItem] = Field(default_factory=list)
    departure_hub_trace: DepartureHubDecisionTrace | None = None
    regeneration_intent: RegenerationIntentSummary | None = None
    follow_up_interpretation: FollowUpInterpretationSummary | None = None


class TripIntentCompileSummary(BaseModel):
    city: str | None = None
    trip_days_mode: str
    scenic_seed_count: int = Field(..., ge=0)
    restaurant_seed_count: int = Field(..., ge=0)
    fixed_event_count: int = Field(..., ge=0)
    availability_window_count: int = Field(..., ge=0)
    rejected_poi_count: int = Field(..., ge=0)
    confirmed_replacement_count: int = Field(..., ge=0)
    needs_auto_completion: bool
    summary_lines: list[str] = Field(default_factory=list)


class TripIntentEnvelope(BaseModel):
    version: int = 1
    source: TripIntentEnvelopeSource
    raw_text: str | None = None
    latest_follow_up_text: str | None = None
    base_intent: RegenerationIntentSummary | None = None
    current_intent: RegenerationIntentSummary
    parsed_intent: ParsedTripIntentResponse | None = None
    planning_state: PlanningInputState | None = None
    follow_up_interpretation: FollowUpInterpretationSummary | None = None
    compile_summary: TripIntentCompileSummary | None = None
    completion_candidate_history: list[ItineraryCompletionOption] = Field(default_factory=list)
    summary_lines: list[str] = Field(default_factory=list)


class PlannerRealismIssue(BaseModel):
    code: str
    severity: str = "medium"
    title: str
    detail: str
    day: int | None = None
    item_names: list[str] = Field(default_factory=list)


class PlannerRealismAction(BaseModel):
    action_id: str
    label: str
    prompt: str
    priority: str = "medium"
    related_issue_code: str | None = None


class DailyRouteLoad(BaseModel):
    """Deterministic, server-owned execution load for one itinerary day."""

    day: int = Field(..., ge=1)
    classification: str
    activity_count: int = Field(..., ge=0)
    fixed_count: int = Field(..., ge=0)
    activity_minutes: int = Field(..., ge=0)
    travel_minutes: int = Field(..., ge=0)
    route_distance_m: int | None = Field(default=None, ge=0)
    reason_codes: list[str] = Field(default_factory=list)
    explanation: str


class PlannerRealismSummary(BaseModel):
    status: str
    headline: str
    issues: list[PlannerRealismIssue] = Field(default_factory=list)
    suggested_actions: list[PlannerRealismAction] = Field(default_factory=list)
    daily_loads: list[DailyRouteLoad] = Field(default_factory=list)


class ItineraryResponse(BaseModel):
    trip_days: int = Field(..., ge=1)
    hotel: HotelStay | None = None
    planning_anchor_source: PlanningAnchorSource
    trip_intent: TripIntentEnvelope | None = None
    planning_assumptions: PlanningAssumptionSummary | None = None
    completion_recommendation: ItineraryCompletionRecommendation | None = None
    completion_intelligence: CompletionIntelligenceSummary | None = None
    journey_approach_recommendation: JourneyApproachRecommendation | None = None
    stay_recommendation: StayRecommendation | None = None
    departure_recommendation: DepartureRecommendation | None = None
    planner_realism: PlannerRealismSummary | None = None
    boundary_explanation: BoundaryInfluenceExplanation = Field(
        default_factory=BoundaryInfluenceExplanation
    )
    days: list[DayItinerary] = Field(default_factory=list)


class PlanTripFromTextResponse(BaseModel):
    trip_intent: TripIntentEnvelope
    parsed_intent: ParsedTripIntentResponse
    planning_state: PlanningInputState
    itinerary: ItineraryResponse


class ReplanItineraryResponse(BaseModel):
    trip_intent: TripIntentEnvelope
    itinerary: ItineraryResponse


class GenerateFromTripIntentResponse(BaseModel):
    trip_intent: TripIntentEnvelope
    itinerary: ItineraryResponse


class CompletionTaskActionRequest(BaseModel):
    itinerary: ItineraryResponse
    task_id: str = Field(
        ...,
        description=(
            "Deterministic completion task id, such as repair_meal_anchor, "
            "repair_evening_close, or repair_sparse_block."
        ),
    )
    task_instance_key: str | None = Field(
        default=None,
        description="Optional frontend/backend task instance key for UI state alignment.",
    )
    day: int | None = Field(
        default=None,
        ge=1,
        description="Optional day to repair. When omitted, the backend chooses the first matching gap.",
    )
    block_type: TimeBlockType | None = Field(
        default=None,
        description="Optional time block to repair. Meal repair defaults to afternoon/evening.",
    )
    selected_candidate: ItineraryCompletionOption | None = Field(
        default=None,
        description="Optional deterministic candidate chosen by the user from a preview response.",
    )
    completion_candidate_history: list[ItineraryCompletionOption] = Field(
        default_factory=list,
        description="Optional rolling candidate memory used to validate preview-selected candidates.",
    )


class CompletionTaskActionResponse(BaseModel):
    task_id: str
    applied: bool
    summary: str
    inserted_item: ScheduledPOI | None = None
    itinerary: ItineraryResponse


class CompletionTaskCandidatePreviewRequest(BaseModel):
    itinerary: ItineraryResponse
    task_id: str
    task_instance_key: str | None = None
    day: int | None = Field(default=None, ge=1)
    block_type: TimeBlockType | None = None
    completion_candidate_history: list[ItineraryCompletionOption] = Field(default_factory=list)


class CompletionTaskCandidatePreviewResponse(BaseModel):
    task_id: str
    task_instance_key: str | None = None
    target_day: int | None = Field(default=None, ge=1)
    target_block: TimeBlockType | None = None
    summary: str
    candidate_source_summary: str | None = None
    candidate_discovery_status: str | None = None
    options: list[ItineraryCompletionOption] = Field(default_factory=list)


class RouteSegmentPreviewInput(BaseModel):
    segment_key: str = Field(..., min_length=1)
    mode: RoutePreviewMode = RoutePreviewMode.WALK
    from_name: str = Field(..., min_length=1)
    from_latitude: float = Field(..., ge=-90, le=90)
    from_longitude: float = Field(..., ge=-180, le=180)
    from_city: str | None = None
    to_name: str = Field(..., min_length=1)
    to_latitude: float = Field(..., ge=-90, le=90)
    to_longitude: float = Field(..., ge=-180, le=180)
    to_city: str | None = None


class RoutePathPoint(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class RouteSegmentPreviewResult(BaseModel):
    segment_key: str
    from_name: str
    to_name: str
    distance_m: int = Field(..., ge=0)
    duration_s: int = Field(..., ge=0)
    source: str = "amap_walking"
    mode: RoutePreviewMode = RoutePreviewMode.WALK
    path_points: list[RoutePathPoint] = Field(default_factory=list)


class RouteSegmentPreviewFailure(BaseModel):
    segment_key: str
    from_name: str
    to_name: str
    reason: str


class RoutePreviewRequest(BaseModel):
    segments: list[RouteSegmentPreviewInput] = Field(default_factory=list)


class RoutePreviewResponse(BaseModel):
    segments: list[RouteSegmentPreviewResult] = Field(default_factory=list)
    failed_segments: list[RouteSegmentPreviewFailure] = Field(default_factory=list)


class POIDetailPreviewRequest(BaseModel):
    name: str = Field(..., min_length=1)
    city: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class POIDetailPreviewResponse(BaseModel):
    found: bool
    name: str
    address: str | None = None
    category: str | None = None
    business_area: str | None = None
    rating: str | None = None
    cost: str | None = None
    tel: str | None = None
    website: str | None = None
    open_time: str | None = None
    photo_url: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source: str = "amap_place_detail"
    failure_reason: str | None = None


class RefreshItinerarySurfacesRequest(BaseModel):
    itinerary: ItineraryResponse
    restored_completion_candidate: ItineraryCompletionOption | None = None
    restored_completion_candidates: list[ItineraryCompletionOption] = Field(default_factory=list)
    completion_candidate_history: list[ItineraryCompletionOption] = Field(default_factory=list)
