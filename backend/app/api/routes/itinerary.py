from __future__ import annotations

import hashlib
import logging
import math
from collections import OrderedDict
from collections.abc import Iterable
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from app.core.scheduler import Scheduler, SchedulingError
from app.planner.trace import (
    PlannerDecision,
    PlannerDecisionStage,
    PlannerInputSnapshot,
    PlannerReasonCode,
    PlannerResultSummary,
    PlannerSubjectType,
    PlannerTraceCollector,
    stable_subject_id,
)
from app.schemas import (
    AvailabilityWindow,
    AvailabilityPreviewRequest,
    AvailabilityPreviewResponse,
    CompletionTaskActionRequest,
    CompletionTaskActionResponse,
    CompletionTaskCandidatePreviewRequest,
    CompletionTaskCandidatePreviewResponse,
    FollowUpInterpretationSummary,
    GenerateFromTripIntentRequest,
    GenerateFromTripIntentResponse,
    HotelInput,
    HotelStay,
    ItineraryCompletionRecommendation,
    ItineraryCompletionOption,
    ItineraryRequest,
    ItineraryResponse,
    NormalizedPOI,
    PlanTripFromTextRequest,
    PlanTripFromTextResponse,
    POIType,
    PlanningAssumptionSummary,
    PlanningAnchorSource,
    PlanningDecisionTraceEvidence,
    PlanningExecutionTraceItem,
    POIDetailPreviewRequest,
    POIDetailPreviewResponse,
    ParsedFixedEvent,
    ParsedTripIntentResponse,
    RefreshItinerarySurfacesRequest,
    ReplanItineraryRequest,
    ReplanItineraryResponse,
    RegenerationIntentSummary,
    RoutePreviewRequest,
    RoutePreviewResponse,
    RouteSegmentPreviewFailure,
    RouteSegmentPreviewResult,
    RawPOIInput,
    ScheduledPOI,
    ScheduledPOISourceType,
    TimeBlockType,
    TravelMode,
    TripDaysInputSource,
    TripIntentCompileSummary,
    TripIntentEnvelope,
    TripIntentEnvelopeSource,
    TripIntentPatch,
    UserConfirmedReplacement,
)
from app.services.amap_direction import RoutePlanningError, get_route
from app.services.amap_client import GeocodingError, search_place_detail_candidates
from app.services.completion_intelligence import build_completion_intelligence_summary
from app.services.departure_recommendation import build_departure_recommendation
from app.services.itinerary_completion_recommendation import (
    CITY_CANDIDATES,
    CandidateSpec,
    apply_completion_task_action,
    apply_completion_recommendation_autofill,
    build_itinerary_completion_recommendation,
    normalize_city_name as normalize_candidate_city_name,
    preview_completion_task_candidates,
    repair_missing_meal_slots,
)
from app.services.intent_disambiguation import disambiguate_trip_intent
from app.services.journey_approach_recommendation import (
    build_journey_approach_recommendation,
)
from app.services.mock_normalizer import (
    infer_poi_profile,
    normalize_anchor,
    normalize_hotel,
    normalize_poi,
)
from app.services.nl_parser import normalize_parsed_trip_intent, parse_trip_text
from app.services.poi_discovery_provider import get_poi_discovery_capability
from app.services.poi_research_summary import attach_poi_research_summaries
from app.services.planner_realism_analyzer import analyze_planner_realism
from app.services.execution_trust import build_execution_trust_summary
from app.services.planning_state_transformer import (
    build_planning_input_state,
    classify_preference_state,
)
from app.services.preference_policy import (
    build_preference_policy,
    build_style_preference_signal,
    ordered_style_preferences,
    style_preference_sources_from_signal,
)
from app.services.stay_recommendation import build_stay_recommendation
from app.services.trip_scope_estimator import estimate_trip_scope

router = APIRouter()
logger = logging.getLogger(__name__)
APPLY_COMPLETION_IDEMPOTENCY_CACHE_LIMIT = 128
APPLY_COMPLETION_IDEMPOTENCY_CACHE: OrderedDict[str, CompletionTaskActionResponse] = OrderedDict()


@router.post(
    "/preview-availability",
    response_model=AvailabilityPreviewResponse,
    status_code=status.HTTP_200_OK,
)
def preview_availability(payload: AvailabilityPreviewRequest) -> AvailabilityPreviewResponse:
    """
    Preview effective day-window availability without generating an itinerary.
    """
    scheduler = Scheduler()
    try:
        return scheduler.preview_availability(
            trip_days=payload.trip_days,
            availability_windows=payload.availability_windows,
        )
    except SchedulingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/preview-route-segments",
    response_model=RoutePreviewResponse,
    status_code=status.HTTP_200_OK,
)
def preview_route_segments(payload: RoutePreviewRequest) -> RoutePreviewResponse:
    """
    Preview edited route segments with Amap routes for the selected transport mode.

    This endpoint is intentionally local and deterministic: it does not reorder the
    itinerary, does not mutate trip intent, and only refreshes adjacent segment
    distance/duration for route-edit UI feedback.
    """
    results: list[RouteSegmentPreviewResult] = []
    failures: list[RouteSegmentPreviewFailure] = []

    for segment in payload.segments[:20]:
        try:
            route = get_route(
                mode=segment.mode.value,
                origin_lat=segment.from_latitude,
                origin_lng=segment.from_longitude,
                dest_lat=segment.to_latitude,
                dest_lng=segment.to_longitude,
                city=segment.from_city or segment.to_city,
            )
        except RoutePlanningError as exc:
            failures.append(
                RouteSegmentPreviewFailure(
                    segment_key=segment.segment_key,
                    from_name=segment.from_name,
                    to_name=segment.to_name,
                    reason=str(exc),
                )
            )
            results.append(build_local_route_preview_segment(segment))
            continue

        results.append(
            RouteSegmentPreviewResult(
                segment_key=segment.segment_key,
                from_name=segment.from_name,
                to_name=segment.to_name,
                distance_m=int(route["distance_m"]),
                duration_s=int(route["duration_s"]),
                source=str(route.get("source") or f"amap_{segment.mode.value}"),
                mode=segment.mode,
                path_points=route.get("path_points", []),
            )
        )

    return RoutePreviewResponse(segments=results, failed_segments=failures)


def build_local_route_preview_segment(segment) -> RouteSegmentPreviewResult:
    """
    Keep route editing usable when the external route provider fails.

    The fallback is deliberately labeled as local_estimate_* and only uses
    straight-line distance plus conservative mode speed. It does not replace
    execution-layer routing; it prevents the UI from becoming visually blank
    while still exposing the failed segment in failed_segments.
    """
    distance_m = int(
        round(
            haversine_km(
                segment.from_latitude,
                segment.from_longitude,
                segment.to_latitude,
                segment.to_longitude,
            )
            * 1000
        )
    )
    duration_s = estimate_route_preview_duration_s(distance_m, segment.mode.value)
    return RouteSegmentPreviewResult(
        segment_key=segment.segment_key,
        from_name=segment.from_name,
        to_name=segment.to_name,
        distance_m=distance_m,
        duration_s=duration_s,
        source=f"local_estimate_{segment.mode.value}",
        mode=segment.mode,
        path_points=[
            {"latitude": segment.from_latitude, "longitude": segment.from_longitude},
            {"latitude": segment.to_latitude, "longitude": segment.to_longitude},
        ],
    )


def estimate_route_preview_duration_s(distance_m: int, mode: str) -> int:
    if distance_m <= 0:
        return 0
    speed_kmh = {
        "walk": 4.2,
        "transit": 18.0,
        "drive": 28.0,
    }.get(mode, 4.2)
    return max(60, int(round((distance_m / 1000) / speed_kmh * 3600)))


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    earth_radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return 2 * earth_radius_km * math.asin(math.sqrt(a))


@router.post(
    "/preview-poi-detail",
    response_model=POIDetailPreviewResponse,
    status_code=status.HTTP_200_OK,
)
def preview_poi_detail(payload: POIDetailPreviewRequest) -> POIDetailPreviewResponse:
    """
    Fetch a lightweight real POI detail card from Amap.

    This endpoint enriches the mobile route editor drawer only. It does not
    change scheduling, does not infer facts with an LLM, and safely returns an
    empty state when the POI provider is unavailable.
    """
    try:
        candidates = search_place_detail_candidates(
            keyword=payload.name,
            city=payload.city,
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
    except GeocodingError as exc:
        return POIDetailPreviewResponse(
            found=False,
            name=payload.name,
            source="amap_place_detail",
            failure_reason=str(exc),
        )

    if not candidates:
        return POIDetailPreviewResponse(
            found=False,
            name=payload.name,
            source="amap_place_detail",
            failure_reason="No Amap POI detail candidate found.",
        )

    candidate = candidates[0]
    return POIDetailPreviewResponse(
        found=True,
        name=str(candidate.get("name") or payload.name),
        address=_clean_optional_text(candidate.get("address")),
        category=_clean_optional_text(candidate.get("type")),
        business_area=_clean_optional_text(candidate.get("business_area")),
        rating=_clean_optional_text(candidate.get("rating")),
        cost=_clean_optional_text(candidate.get("cost")),
        tel=_clean_optional_text(candidate.get("tel")),
        website=_clean_optional_text(candidate.get("website")),
        open_time=_clean_optional_text(candidate.get("open_time")),
        photo_url=_clean_optional_text(candidate.get("photo_url")),
        latitude=candidate.get("latitude"),
        longitude=candidate.get("longitude"),
        source="amap_place_detail",
    )


def _clean_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or stripped == "[]":
        return None
    return stripped


@router.post(
    "/generate-itinerary",
    response_model=ItineraryResponse,
    status_code=status.HTTP_200_OK,
)
def generate_itinerary(payload: ItineraryRequest) -> ItineraryResponse:
    """
    Generate an itinerary from raw user input using live Amap geocoding.
    """
    try:
        return build_itinerary_response(payload)
    except GeocodingError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except SchedulingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/generate-from-trip-intent",
    response_model=GenerateFromTripIntentResponse,
    status_code=status.HTTP_200_OK,
)
def generate_from_trip_intent(
    payload: GenerateFromTripIntentRequest,
) -> GenerateFromTripIntentResponse:
    """
    Regenerate an itinerary from the rolling trip intent envelope.
    """
    try:
        current_intent = prepare_regeneration_intent_for_generate(payload)
        itinerary_payload = build_itinerary_request_from_regeneration_intent(
            current_intent,
            auto_fill_sparse_days=payload.auto_fill_sparse_days,
        )
        itinerary = build_itinerary_response(
            itinerary_payload,
            intent_source=TripIntentEnvelopeSource.REGENERATE,
            raw_text=payload.trip_intent.raw_text,
            latest_follow_up_text=payload.trip_intent.latest_follow_up_text,
            base_intent=payload.trip_intent.current_intent,
            parsed_intent=payload.trip_intent.parsed_intent,
            planning_state=payload.trip_intent.planning_state,
            completion_candidate_history=payload.trip_intent.completion_candidate_history,
        )
        return GenerateFromTripIntentResponse(
            trip_intent=require_trip_intent_envelope(itinerary),
            itinerary=itinerary,
        )
    except GeocodingError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except SchedulingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/plan-trip-from-text",
    response_model=PlanTripFromTextResponse,
    status_code=status.HTTP_200_OK,
)
def plan_trip_from_text(payload: PlanTripFromTextRequest) -> PlanTripFromTextResponse:
    """
    Parse a natural-language trip idea and execute it through the deterministic planner.
    """
    try:
        parsed_intent = disambiguate_trip_intent(
            parse_trip_text(payload.text),
            raw_text=payload.text,
        )
        if payload.extra_preferences:
            parsed_intent = normalize_parsed_trip_intent(
                parsed_intent.model_copy(
                    update={
                        "preferences": unique_preserve_order(
                            [*parsed_intent.preferences, *payload.extra_preferences]
                        )
                    }
                )
            )
        planning_state = build_planning_input_state(parsed_intent)
        travel_mode = payload.travel_mode or infer_travel_mode_from_text(payload.text)
        itinerary_payload = build_itinerary_request_from_parsed_intent(
            parsed_intent=parsed_intent,
            planning_state=planning_state,
            travel_mode=travel_mode,
            auto_fill_sparse_days=payload.auto_fill_sparse_days,
        )
        itinerary = build_itinerary_response(
            itinerary_payload,
            intent_source=TripIntentEnvelopeSource.INITIAL_TEXT,
            raw_text=payload.text,
            parsed_intent=parsed_intent,
            planning_state=planning_state,
        )
        trip_intent = require_trip_intent_envelope(itinerary)
        return PlanTripFromTextResponse(
            trip_intent=trip_intent,
            parsed_intent=parsed_intent,
            planning_state=planning_state,
            itinerary=itinerary,
        )
    except GeocodingError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except SchedulingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


def infer_travel_mode_from_text(text: str) -> TravelMode | None:
    """
    Recover explicit transport intent from the raw user sentence.

    This stays in the interaction-to-contract adapter layer: it only fills the
    existing travel_mode field so deterministic scheduling and departure-hub
    ranking can make bounded decisions.
    """
    normalized = text.strip().lower()
    if not normalized:
        return None

    if any(token in normalized for token in ("高铁", "动车")):
        return TravelMode.HIGH_SPEED_RAIL
    if any(token in normalized for token in ("火车", "铁路", "火车站", "坐火车")):
        return TravelMode.RAIL
    if any(token in normalized for token in ("飞机", "机场", "航班", "坐飞机", "飞回", "飞去")):
        return TravelMode.AIRPLANE
    if any(token in normalized for token in ("自驾", "开车", "租车")):
        return TravelMode.CAR

    return None


@router.post(
    "/replan-itinerary",
    response_model=ReplanItineraryResponse,
    status_code=status.HTTP_200_OK,
)
def replan_itinerary(payload: ReplanItineraryRequest) -> ReplanItineraryResponse:
    """
    Rebuild the itinerary from the current regenerate brief plus one natural-language follow-up.
    """
    try:
        base_intent = resolve_replan_base_intent(payload)
        follow_up_intent = disambiguate_trip_intent(
            parse_trip_text(payload.follow_up_text),
            raw_text=payload.follow_up_text,
            city_hint=base_intent.city,
        )
        merged_payload, merge_notes, interpretation_summary = build_replan_request(
            base_intent=base_intent,
            follow_up_text=payload.follow_up_text,
            follow_up_intent=follow_up_intent,
            auto_fill_sparse_days=payload.auto_fill_sparse_days,
        )
        itinerary = build_itinerary_response(
            merged_payload,
            replan_notes=merge_notes,
            follow_up_interpretation=interpretation_summary,
            intent_source=TripIntentEnvelopeSource.FOLLOW_UP,
            raw_text=(
                payload.trip_intent.raw_text
                if payload.trip_intent is not None
                else payload.follow_up_text
            ),
            latest_follow_up_text=payload.follow_up_text,
            base_intent=base_intent,
            parsed_intent=(
                payload.trip_intent.parsed_intent
                if payload.trip_intent is not None
                else follow_up_intent
            ),
            planning_state=(
                payload.trip_intent.planning_state
                if payload.trip_intent is not None
                else None
            ),
            completion_candidate_history=(
                payload.trip_intent.completion_candidate_history
                if payload.trip_intent is not None
                else None
            ),
        )
        return ReplanItineraryResponse(
            trip_intent=require_trip_intent_envelope(itinerary),
            itinerary=itinerary,
        )
    except GeocodingError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except SchedulingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/apply-completion-task",
    response_model=CompletionTaskActionResponse,
    status_code=status.HTTP_200_OK,
)
def apply_completion_task(
    payload: CompletionTaskActionRequest,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> CompletionTaskActionResponse:
    """
    Apply one deterministic Completion Intelligence task without rebuilding the whole trip.
    """
    idempotency_cache_key = build_apply_completion_idempotency_key(
        x_idempotency_key,
        payload,
    )
    if idempotency_cache_key is not None:
        cached_response = get_apply_completion_idempotency_response(idempotency_cache_key)
        if cached_response is not None:
            return cached_response

    response = execute_completion_task_action(payload)
    if idempotency_cache_key is not None:
        remember_apply_completion_idempotency_response(idempotency_cache_key, response)
    return response


def execute_completion_task_action(
    payload: CompletionTaskActionRequest,
) -> CompletionTaskActionResponse:
    """
    Execute the deterministic Completion Intelligence mutation once.

    The legacy endpoint wraps this helper with an in-memory idempotency cache.
    Persisted TripRevision endpoints wrap the same helper with durable
    idempotency, stale-base checks, and immutable revision creation.
    """
    intent = current_intent_from_itinerary(payload.itinerary)
    preference_policy = build_preference_policy(intent.preferences if intent is not None else [])
    request_style_signal = build_style_preference_signal(
        preferences=intent.preferences if intent is not None else [],
        parsed_style_preferences=(intent.style_preferences if intent is not None else None),
        parsed_style_preference_sources=(intent.style_preference_sources if intent is not None else None),
    )
    action_result = apply_completion_task_action(
        itinerary=payload.itinerary,
        task_id=payload.task_id,
        day=payload.day,
        block_type=payload.block_type,
        selected_candidate=payload.selected_candidate,
        completion_candidate_history=[
            *(
                payload.itinerary.trip_intent.completion_candidate_history
                if payload.itinerary.trip_intent is not None
                else []
            ),
            *payload.completion_candidate_history,
        ],
        preference_policy=preference_policy,
        request_style_preferences=request_style_signal,
    )
    refreshed_itinerary = refresh_completion_task_itinerary_surfaces(
        action_result.itinerary,
        preference_policy=preference_policy,
        request_style_signal=request_style_signal,
        preferred_mode=(intent.travel_mode if intent is not None else None),
    )
    response = CompletionTaskActionResponse(
        task_id=action_result.task_id,
        applied=action_result.applied,
        summary=action_result.summary,
        inserted_item=action_result.inserted_item,
        itinerary=refreshed_itinerary,
    )
    return response


def build_apply_completion_idempotency_key(
    raw_key: str | None,
    payload: CompletionTaskActionRequest,
) -> str | None:
    normalized_key = raw_key.strip() if raw_key else ""
    if not normalized_key:
        return None
    payload_digest = hashlib.sha256(
        payload.model_dump_json().encode("utf-8"),
    ).hexdigest()
    return f"apply-completion-task:{normalized_key}:{payload_digest}"


def get_apply_completion_idempotency_response(
    cache_key: str,
) -> CompletionTaskActionResponse | None:
    cached_response = APPLY_COMPLETION_IDEMPOTENCY_CACHE.get(cache_key)
    if cached_response is None:
        return None
    APPLY_COMPLETION_IDEMPOTENCY_CACHE.move_to_end(cache_key)
    return cached_response.model_copy(deep=True)


def remember_apply_completion_idempotency_response(
    cache_key: str,
    response: CompletionTaskActionResponse,
) -> None:
    APPLY_COMPLETION_IDEMPOTENCY_CACHE[cache_key] = response.model_copy(deep=True)
    APPLY_COMPLETION_IDEMPOTENCY_CACHE.move_to_end(cache_key)
    while len(APPLY_COMPLETION_IDEMPOTENCY_CACHE) > APPLY_COMPLETION_IDEMPOTENCY_CACHE_LIMIT:
        APPLY_COMPLETION_IDEMPOTENCY_CACHE.popitem(last=False)


@router.post(
    "/preview-completion-task-candidates",
    response_model=CompletionTaskCandidatePreviewResponse,
    status_code=status.HTTP_200_OK,
)
def preview_completion_task_candidate_options(
    payload: CompletionTaskCandidatePreviewRequest,
) -> CompletionTaskCandidatePreviewResponse:
    """
    Preview deterministic candidate options for a Completion Intelligence task.
    """
    intent = current_intent_from_itinerary(payload.itinerary)
    preference_policy = build_preference_policy(intent.preferences if intent is not None else [])
    request_style_signal = build_style_preference_signal(
        preferences=intent.preferences if intent is not None else [],
        parsed_style_preferences=(intent.style_preferences if intent is not None else None),
        parsed_style_preference_sources=(intent.style_preference_sources if intent is not None else None),
    )
    (
        target_day,
        target_block,
        summary,
        options,
        candidate_source_summary,
        candidate_discovery_status,
    ) = preview_completion_task_candidates(
        itinerary=payload.itinerary,
        task_id=payload.task_id,
        day=payload.day,
        block_type=payload.block_type,
        completion_candidate_history=[
            *(
                payload.itinerary.trip_intent.completion_candidate_history
                if payload.itinerary.trip_intent is not None
                else []
            ),
            *payload.completion_candidate_history,
        ],
        preference_policy=preference_policy,
        request_style_preferences=request_style_signal,
    )
    return CompletionTaskCandidatePreviewResponse(
        task_id=payload.task_id,
        task_instance_key=payload.task_instance_key,
        target_day=target_day,
        target_block=target_block,
        summary=summary,
        candidate_source_summary=candidate_source_summary,
        candidate_discovery_status=candidate_discovery_status,
        options=options,
    )


@router.post(
    "/refresh-itinerary-surfaces",
    response_model=ItineraryResponse,
    status_code=status.HTTP_200_OK,
)
def refresh_itinerary_surfaces(
    payload: RefreshItinerarySurfacesRequest,
) -> ItineraryResponse:
    """
    Refresh explanation and completion surfaces without changing scheduled items.
    """
    intent = current_intent_from_itinerary(payload.itinerary)
    preference_policy = build_preference_policy(intent.preferences if intent is not None else [])
    request_style_signal = build_style_preference_signal(
        preferences=intent.preferences if intent is not None else [],
        parsed_style_preferences=(intent.style_preferences if intent is not None else None),
        parsed_style_preference_sources=(intent.style_preference_sources if intent is not None else None),
    )
    return refresh_completion_task_itinerary_surfaces(
        payload.itinerary,
        preference_policy=preference_policy,
        request_style_signal=request_style_signal,
        preferred_mode=(intent.travel_mode if intent is not None else None),
        restored_completion_candidate=payload.restored_completion_candidate,
        restored_completion_candidates=payload.restored_completion_candidates,
        completion_candidate_history=payload.completion_candidate_history,
    )


def current_intent_from_itinerary(
    itinerary: ItineraryResponse,
) -> RegenerationIntentSummary | None:
    if itinerary.trip_intent is not None:
        return itinerary.trip_intent.current_intent
    if (
        itinerary.planning_assumptions is not None
        and itinerary.planning_assumptions.regeneration_intent is not None
    ):
        return itinerary.planning_assumptions.regeneration_intent
    return None


def refresh_completion_task_itinerary_surfaces(
    itinerary: ItineraryResponse,
    *,
    preference_policy,
    request_style_signal,
    preferred_mode,
    restored_completion_candidate=None,
    restored_completion_candidates=None,
    completion_candidate_history=None,
) -> ItineraryResponse:
    itinerary = attach_poi_research_summaries(itinerary)
    completion_recommendation = build_itinerary_completion_recommendation(
        itinerary,
        preference_policy=preference_policy,
        request_style_preferences=request_style_signal,
    )
    journey_approach_recommendation = build_journey_approach_recommendation(
        itinerary=itinerary,
        preferred_mode=preferred_mode,
    )
    hotel_was_provided = itinerary.planning_anchor_source.source_type == "provided_hotel"
    departure_anchor_was_provided = itinerary.planning_anchor_source.source_type == "departure_anchor"
    stay_recommendation = build_stay_recommendation(
        itinerary=itinerary,
        hotel_was_provided=hotel_was_provided,
    )
    departure_recommendation = build_departure_recommendation(
        itinerary=itinerary,
        departure_anchor_was_provided=departure_anchor_was_provided,
        preferred_mode=preferred_mode,
    )
    planning_assumptions = itinerary.planning_assumptions
    if planning_assumptions is not None:
        departure_hub_trace = (
            departure_recommendation.options[0].decision_trace
            if departure_recommendation is not None
            and departure_recommendation.options
            else planning_assumptions.departure_hub_trace
        )
        planning_assumptions = planning_assumptions.model_copy(
            update={
                "auto_filled_count": count_auto_filled_items(itinerary),
                "departure_hub_trace": departure_hub_trace,
            }
        )
    completion_intelligence = (
        build_completion_intelligence_summary(
            itinerary=itinerary,
            planning_assumptions=planning_assumptions,
            completion_recommendation=completion_recommendation,
            stay_recommendation=stay_recommendation,
            departure_recommendation=departure_recommendation,
        )
        if planning_assumptions is not None
        else itinerary.completion_intelligence
    )
    completion_candidate_history = merge_completion_candidate_history(
        itinerary,
        [restored_completion_candidate] if restored_completion_candidate is not None else [],
        restored_completion_candidates or [],
        completion_recommendation.options if completion_recommendation is not None else [],
        completion_candidate_history or [],
        (
            itinerary.trip_intent.completion_candidate_history
            if itinerary.trip_intent is not None
            else []
        ),
    )
    if completion_candidate_history:
        completion_recommendation = upsert_restored_completion_candidates(
            completion_recommendation,
            completion_candidate_history,
        )
    trip_intent = itinerary.trip_intent
    if trip_intent is not None:
        trip_intent = trip_intent.model_copy(
            update={"completion_candidate_history": completion_candidate_history}
        )
    response = itinerary.model_copy(
        update={
            "trip_intent": trip_intent,
            "planning_assumptions": planning_assumptions,
            "completion_recommendation": completion_recommendation,
            "completion_intelligence": completion_intelligence,
            "journey_approach_recommendation": journey_approach_recommendation,
            "stay_recommendation": stay_recommendation,
            "departure_recommendation": departure_recommendation,
        }
    )
    return response


def upsert_restored_completion_candidates(
    recommendation: ItineraryCompletionRecommendation | None,
    restored_candidates,
) -> ItineraryCompletionRecommendation:
    if recommendation is None:
        return ItineraryCompletionRecommendation(
            summary="Recently removed completion candidates are available again.",
            options=dedupe_completion_candidates(restored_candidates),
        )

    restored_keys = {completion_candidate_key(candidate) for candidate in restored_candidates}
    filtered_options = [
        option
        for option in recommendation.options
        if completion_candidate_key(option) not in restored_keys
    ]
    return recommendation.model_copy(
        update={
            "options": [
                *dedupe_completion_candidates(restored_candidates),
                *filtered_options,
            ],
        }
    )


def merge_completion_candidate_history(
    itinerary: ItineraryResponse,
    *candidate_groups,
) -> list[ItineraryCompletionOption]:
    candidates = filter_scheduled_completion_candidates(
        itinerary,
        [
            candidate
            for candidate_group in candidate_groups
            for candidate in (candidate_group or [])
        ],
    )
    return trim_completion_candidate_history(dedupe_completion_candidates(candidates))


def dedupe_completion_candidates(candidates) -> list[ItineraryCompletionOption]:
    unique: dict[tuple, ItineraryCompletionOption] = {}
    for candidate in candidates:
        key = completion_candidate_key(candidate)
        if key not in unique:
            unique[key] = candidate
    return list(unique.values())


def filter_scheduled_completion_candidates(itinerary: ItineraryResponse, candidates):
    scheduled_keys = {
        (item.name, item.type)
        for day in itinerary.days
        for block in day.blocks
        for item in block.items
    }
    return [
        candidate
        for candidate in candidates
        if (candidate.name, candidate.type) not in scheduled_keys
    ]


def trim_completion_candidate_history(
    candidates: list[ItineraryCompletionOption],
    *,
    per_bucket_limit: int = 4,
    total_limit: int = 40,
) -> list[ItineraryCompletionOption]:
    bucket_counts: dict[tuple, int] = {}
    trimmed: list[ItineraryCompletionOption] = []
    for candidate in candidates:
        bucket_key = (
            candidate.suggested_day,
            candidate.suggested_block,
            candidate.type,
        )
        if bucket_counts.get(bucket_key, 0) >= per_bucket_limit:
            continue
        bucket_counts[bucket_key] = bucket_counts.get(bucket_key, 0) + 1
        trimmed.append(candidate)
        if len(trimmed) >= total_limit:
            break
    return trimmed


def completion_candidate_key(candidate) -> tuple:
    return (
        candidate.name,
        candidate.type,
        candidate.suggested_day,
        candidate.suggested_block,
    )


def count_auto_filled_items(itinerary: ItineraryResponse) -> int:
    return sum(
        1
        for day in itinerary.days
        for block in day.blocks
        for item in block.items
        if item.source_type == ScheduledPOISourceType.AUTO_FILLED
    )


def build_auto_fill_blocked_reasons(
    *,
    auto_fill_attempted: bool,
    initial_option_count: int,
    auto_filled_count: int,
) -> list[str]:
    if not auto_fill_attempted or auto_filled_count > 0:
        return []
    if initial_option_count <= 0:
        return [
            "系统识别到空缺，但没有找到足够稳妥的真实 POI 候选，所以没有自动补入占位地点。"
        ]
    return [
        "系统识别到可补齐候选，但候选没有通过当前时间块的可插入校验，已留给你手动确认。"
    ]


def resolve_replan_base_intent(payload: ReplanItineraryRequest) -> RegenerationIntentSummary:
    if payload.trip_intent is not None:
        return payload.trip_intent.current_intent
    if payload.base_intent is not None:
        return payload.base_intent
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Either trip_intent or base_intent is required for replanning.",
    )


def build_itinerary_response(
    payload: ItineraryRequest,
    *,
    replan_notes: list[str] | None = None,
    follow_up_interpretation: FollowUpInterpretationSummary | None = None,
    intent_source: TripIntentEnvelopeSource = TripIntentEnvelopeSource.DIRECT_GENERATE,
    raw_text: str | None = None,
    latest_follow_up_text: str | None = None,
    base_intent: RegenerationIntentSummary | None = None,
    parsed_intent: ParsedTripIntentResponse | None = None,
    planning_state=None,
    completion_candidate_history: list[ItineraryCompletionOption] | None = None,
    trace_collector: PlannerTraceCollector | None = None,
) -> ItineraryResponse:
    scheduler = Scheduler()
    hotel_was_provided = payload.hotel is not None
    departure_anchor_was_provided = payload.departure_anchor is not None
    provided_hotel = normalize_optional_hotel(payload.hotel, city=payload.city)
    scenic_spots = normalize_optional_pois(
        raw_pois=payload.scenic_spots,
        poi_type=POIType.SCENIC,
        city=payload.city,
        trace_collector=trace_collector,
    )
    restaurants = normalize_optional_pois(
        raw_pois=payload.restaurants,
        poi_type=POIType.RESTAURANT,
        city=payload.city,
        trace_collector=trace_collector,
    )
    arrival_anchor = normalize_optional_anchor(payload.arrival_anchor, city=payload.city)
    departure_anchor = normalize_optional_anchor(payload.departure_anchor, city=payload.city)
    bootstrap_scenic, bootstrap_restaurants = build_sparse_city_bootstrap_pois(
        city=payload.city,
        preferences=payload.preferences,
        needs_scenic=not scenic_spots,
        needs_restaurants=not restaurants,
        target_trip_days=payload.trip_days or 1,
    )
    scenic_spots.extend(bootstrap_scenic)
    restaurants.extend(bootstrap_restaurants)
    if trace_collector is not None:
        for bootstrap_poi in [*bootstrap_scenic, *bootstrap_restaurants]:
            trace_collector.record_decision(
                stage=PlannerDecisionStage.CANDIDATE_DISCOVERY,
                subject_type=PlannerSubjectType.CANDIDATE,
                subject_id=stable_trace_candidate_id(bootstrap_poi),
                decision=PlannerDecision.FALLBACK_USED,
                reason_codes=[PlannerReasonCode.FALLBACK_CANDIDATE_USED],
                metrics={
                    "name": bootstrap_poi.name,
                    "type": bootstrap_poi.type.value,
                    "city": bootstrap_poi.city,
                },
            )
    if (
        provided_hotel is None
        and arrival_anchor is None
        and departure_anchor is None
        and not scenic_spots
        and not restaurants
        and request_contains_unresolved_planning_seeds(payload)
    ):
        raise SchedulingError(build_unresolved_planning_seed_error(payload))

    planning_anchor, planning_anchor_source = resolve_planning_anchor(
        provided_hotel=provided_hotel,
        scenic_spots=scenic_spots,
        restaurants=restaurants,
        arrival_anchor=arrival_anchor,
        departure_anchor=departure_anchor,
        city=payload.city,
    )
    if trace_collector is not None:
        anchor_reason = (
            PlannerReasonCode.FALLBACK_SOFT_ROUTE_ANCHOR_USED
            if planning_anchor_source.source_type in {"route_soft_anchor", "fallback_poi"}
            else PlannerReasonCode.ACCEPTED_PLANNING_ANCHOR
        )
        trace_collector.record_decision(
            stage=PlannerDecisionStage.IDENTITY_RESOLUTION,
            subject_type=PlannerSubjectType.PLANNING_ANCHOR,
            subject_id=stable_subject_id(
                "planning_anchor",
                planning_anchor_source.source_type,
                planning_anchor.name.casefold(),
                round(planning_anchor.latitude, 6),
                round(planning_anchor.longitude, 6),
            ),
            decision=(
                PlannerDecision.FALLBACK_USED
                if anchor_reason == PlannerReasonCode.FALLBACK_SOFT_ROUTE_ANCHOR_USED
                else PlannerDecision.ACCEPTED
            ),
            reason_codes=[anchor_reason],
            metrics={
                "source_type": planning_anchor_source.source_type,
                "source_name": planning_anchor_source.source_name,
            },
        )
    preference_policy = build_preference_policy(payload.preferences)
    request_style_signal = build_style_preference_signal(
        preferences=payload.preferences,
        scenic_spots=scenic_spots,
        restaurants=restaurants,
    )

    itinerary = scheduler.build_schedule(
        scenic_spots=scenic_spots,
        restaurants=restaurants,
        hotel=planning_anchor,
        planning_anchor_source=planning_anchor_source,
        travel_mode=payload.travel_mode,
        apply_hotel_end_of_day_bias=hotel_was_provided,
        arrival_anchor=arrival_anchor,
        departure_anchor=departure_anchor,
        availability_windows=payload.availability_windows,
        trip_days=payload.trip_days,
        preference_policy=preference_policy,
        trace_collector=trace_collector,
    )
    annotate_bootstrap_items(
        itinerary=itinerary,
        bootstrap_scenic=bootstrap_scenic,
        bootstrap_restaurants=bootstrap_restaurants,
    )
    completion_recommendation = build_itinerary_completion_recommendation(
        itinerary=itinerary,
        preference_policy=preference_policy,
        request_style_preferences=request_style_signal,
    )
    auto_fill_attempted = bool(payload.auto_fill_sparse_days)
    initial_completion_option_count = (
        len(completion_recommendation.options) if completion_recommendation is not None else 0
    )
    if payload.auto_fill_sparse_days and completion_recommendation is not None:
        itinerary = apply_completion_recommendation_autofill(
            itinerary=itinerary,
            recommendation=completion_recommendation,
        )
        itinerary = repair_missing_meal_slots(
            itinerary,
            preference_policy=preference_policy,
            request_style_preferences=request_style_signal,
        )
        annotate_bootstrap_items(
            itinerary=itinerary,
            bootstrap_scenic=bootstrap_scenic,
            bootstrap_restaurants=bootstrap_restaurants,
        )
        completion_recommendation = build_itinerary_completion_recommendation(
            itinerary=itinerary,
            preference_policy=preference_policy,
            request_style_preferences=request_style_signal,
        )
    auto_fill_blocked_reasons = build_auto_fill_blocked_reasons(
        auto_fill_attempted=auto_fill_attempted,
        initial_option_count=initial_completion_option_count,
        auto_filled_count=count_auto_filled_items(itinerary),
    )

    planning_assumptions = build_planning_assumption_summary(
        payload=payload,
        itinerary=itinerary,
        bootstrap_scenic=bootstrap_scenic,
        bootstrap_restaurants=bootstrap_restaurants,
        request_style_signal=request_style_signal,
    )
    if replan_notes:
        planning_assumptions = append_replan_notes_to_assumptions(
            planning_assumptions,
            replan_notes,
        )
    if follow_up_interpretation is not None:
        planning_assumptions = planning_assumptions.model_copy(
            update={"follow_up_interpretation": follow_up_interpretation}
        )
    journey_approach_recommendation = build_journey_approach_recommendation(
        itinerary=itinerary,
        preferred_mode=payload.travel_mode,
    )
    stay_recommendation = build_stay_recommendation(
        itinerary=itinerary,
        hotel_was_provided=hotel_was_provided,
    )
    departure_recommendation = build_departure_recommendation(
        itinerary=itinerary,
        departure_anchor_was_provided=departure_anchor_was_provided,
        preferred_mode=payload.travel_mode,
    )
    planner_realism = analyze_planner_realism(
        itinerary.model_copy(
            update={"departure_recommendation": departure_recommendation}
        )
    )
    departure_hub_trace = (
        departure_recommendation.options[0].decision_trace
        if departure_recommendation is not None
        and departure_recommendation.options
        else None
    )
    if departure_hub_trace is not None:
        planning_assumptions = planning_assumptions.model_copy(
            update={"departure_hub_trace": departure_hub_trace}
        )
    completion_candidate_history = merge_completion_candidate_history(
        itinerary,
        completion_recommendation.options if completion_recommendation is not None else [],
        completion_candidate_history or [],
    )
    trip_intent = build_trip_intent_envelope(
        source=intent_source,
        assumptions=planning_assumptions,
        raw_text=raw_text,
        latest_follow_up_text=latest_follow_up_text,
        base_intent=base_intent,
        parsed_intent=parsed_intent,
        planning_state=planning_state,
        completion_candidate_history=completion_candidate_history,
    )
    completion_intelligence = build_completion_intelligence_summary(
        itinerary=itinerary,
        planning_assumptions=planning_assumptions,
        completion_recommendation=completion_recommendation,
        stay_recommendation=stay_recommendation,
        departure_recommendation=departure_recommendation,
        auto_fill_attempted=auto_fill_attempted,
        auto_fill_blocked_reasons=auto_fill_blocked_reasons,
    )

    itinerary = attach_poi_research_summaries(itinerary)

    return itinerary.model_copy(
        update={
            "hotel": provided_hotel,
            "trip_intent": trip_intent,
            "planning_assumptions": planning_assumptions,
            "completion_recommendation": completion_recommendation,
            "completion_intelligence": completion_intelligence,
            "journey_approach_recommendation": journey_approach_recommendation,
            "stay_recommendation": stay_recommendation,
            "departure_recommendation": departure_recommendation,
            "planner_realism": planner_realism,
        }
    )
    return response.model_copy(
        update={
            "execution_trust": build_execution_trust_summary(
                itinerary=response,
                provider_summary=trace_collector.provider_summary if trace_collector is not None else None,
            )
        }
    )


def build_itinerary_request_from_parsed_intent(
    *,
    parsed_intent: ParsedTripIntentResponse,
    planning_state,
    travel_mode,
    auto_fill_sparse_days: bool,
) -> ItineraryRequest:
    trip_days_source = (
        TripDaysInputSource.EXPLICIT
        if parsed_intent.trip_days is not None
        else TripDaysInputSource.INTERACTION_ESTIMATED
    )
    trip_days = (
        parsed_intent.trip_days
        if parsed_intent.trip_days is not None
        else planning_state.trip_scope_estimate.estimated_trip_days
    )
    fixed_scenic = [
        build_raw_poi_payload(event)
        for event in parsed_intent.fixed_events
        if event.category != "restaurant" and is_actionable_fixed_event_poi(event)
    ]
    fixed_restaurants = [
        build_raw_poi_payload(event)
        for event in parsed_intent.fixed_events
        if event.category == "restaurant" and is_actionable_fixed_event_poi(event)
    ]

    return ItineraryRequest(
        city=parsed_intent.city,
        scenic_spots=[
            *({"name": name} for name in parsed_intent.scenic_spots),
            *fixed_scenic,
        ],
        restaurants=[
            *({"name": name} for name in parsed_intent.restaurants),
            *fixed_restaurants,
        ],
        hotel={"name": parsed_intent.hotel} if parsed_intent.hotel else None,
        travel_mode=travel_mode,
        arrival_anchor=parsed_intent.arrival_anchor,
        departure_anchor=parsed_intent.departure_anchor,
        availability_windows=list(parsed_intent.availability_windows),
        preferences=list(parsed_intent.preferences),
        auto_fill_sparse_days=auto_fill_sparse_days,
        trip_days=trip_days,
        trip_days_source=trip_days_source,
    )


def prepare_regeneration_intent_for_generate(
    payload: GenerateFromTripIntentRequest,
) -> RegenerationIntentSummary:
    current_intent = payload.trip_intent.current_intent
    if payload.intent_patch is not None:
        current_intent = apply_trip_intent_patch(current_intent, payload.intent_patch)
    updates = {}
    if payload.trip_days_override is not None:
        updates.update(
            {
                "trip_days": payload.trip_days_override,
                "suggested_trip_days": payload.trip_days_override,
                "trip_days_basis": TripDaysInputSource.EXPLICIT.value,
            }
        )
    if payload.extra_preferences:
        updates["preferences"] = unique_preserve_order(
            [*current_intent.preferences, *payload.extra_preferences]
        )
    if not updates:
        return current_intent
    return current_intent.model_copy(update=updates)


def apply_trip_intent_patch(
    intent: RegenerationIntentSummary,
    patch: TripIntentPatch,
) -> RegenerationIntentSummary:
    updates = {}
    fields_set = patch.model_fields_set

    for field_name in (
        "city",
        "travel_mode",
        "hotel",
        "arrival_anchor",
        "departure_anchor",
        "availability_windows",
        "fixed_events",
        "preferences",
        "rejected_scenic_spots",
        "rejected_restaurants",
        "confirmed_replacements",
    ):
        if field_name in fields_set:
            updates[field_name] = getattr(patch, field_name)

    if "flexible_scenic_spots" in fields_set:
        scenic = unique_preserve_order(patch.flexible_scenic_spots or [])
        updates["flexible_scenic_spots"] = scenic
        updates["carry_forward_scenic_spots"] = filter_rejected_names(
            scenic,
            patch.rejected_scenic_spots
            if "rejected_scenic_spots" in fields_set and patch.rejected_scenic_spots is not None
            else intent.rejected_scenic_spots,
        )

    if "flexible_restaurants" in fields_set:
        restaurants = unique_preserve_order(patch.flexible_restaurants or [])
        updates["flexible_restaurants"] = restaurants
        updates["carry_forward_restaurants"] = filter_rejected_names(
            restaurants,
            patch.rejected_restaurants
            if "rejected_restaurants" in fields_set and patch.rejected_restaurants is not None
            else intent.rejected_restaurants,
        )

    if "trip_days" in fields_set:
        updates["trip_days"] = patch.trip_days
        updates["trip_days_basis"] = (
            TripDaysInputSource.EXPLICIT.value
            if patch.trip_days is not None
            else "interaction_estimated"
        )

    if not updates:
        return intent

    updates["notes"] = unique_preserve_order(
        [
            "Manual intent patch was applied before deterministic regeneration.",
            *intent.notes,
        ]
    )
    return intent.model_copy(update=updates)


def build_itinerary_request_from_regeneration_intent(
    intent: RegenerationIntentSummary,
    *,
    auto_fill_sparse_days: bool,
) -> ItineraryRequest:
    scenic_names = filter_rejected_names(
        intent.carry_forward_scenic_spots or intent.flexible_scenic_spots,
        intent.rejected_scenic_spots,
    )
    restaurant_names = filter_rejected_names(
        intent.carry_forward_restaurants or intent.flexible_restaurants,
        intent.rejected_restaurants,
    )
    return ItineraryRequest(
        city=intent.city,
        scenic_spots=[
            *({"name": name} for name in scenic_names),
            *(
                build_raw_poi_payload(event)
                for event in intent.fixed_events
                if event.category != "restaurant"
            ),
        ],
        restaurants=[
            *({"name": name} for name in restaurant_names),
            *(
                build_raw_poi_payload(event)
                for event in intent.fixed_events
                if event.category == "restaurant"
            ),
        ],
        hotel={"name": intent.hotel} if intent.hotel else None,
        travel_mode=intent.travel_mode,
        arrival_anchor=intent.arrival_anchor,
        departure_anchor=intent.departure_anchor,
        availability_windows=list(intent.availability_windows),
        preferences=list(intent.preferences),
        rejected_scenic_spots=list(intent.rejected_scenic_spots),
        rejected_restaurants=list(intent.rejected_restaurants),
        confirmed_replacements=list(intent.confirmed_replacements),
        auto_fill_sparse_days=auto_fill_sparse_days,
        trip_days=intent.trip_days,
        trip_days_source=(
            TripDaysInputSource.EXPLICIT
            if intent.trip_days is not None and intent.trip_days_basis == TripDaysInputSource.EXPLICIT.value
            else None
        ),
    )


def build_trip_intent_envelope(
    *,
    source: TripIntentEnvelopeSource,
    assumptions: PlanningAssumptionSummary,
    raw_text: str | None = None,
    latest_follow_up_text: str | None = None,
    base_intent: RegenerationIntentSummary | None = None,
    parsed_intent: ParsedTripIntentResponse | None = None,
    planning_state=None,
    completion_candidate_history: list[ItineraryCompletionOption] | None = None,
) -> TripIntentEnvelope | None:
    current_intent = assumptions.regeneration_intent
    if current_intent is None:
        return None

    envelope_parsed_intent = parsed_intent
    envelope_planning_state = planning_state
    if source in {
        TripIntentEnvelopeSource.REGENERATE,
        TripIntentEnvelopeSource.FOLLOW_UP,
    }:
        envelope_parsed_intent = build_parsed_intent_from_regeneration_intent(
            current_intent
        )
        envelope_planning_state = build_planning_input_state(envelope_parsed_intent)

    return TripIntentEnvelope(
        source=source,
        raw_text=raw_text,
        latest_follow_up_text=latest_follow_up_text,
        base_intent=base_intent,
        current_intent=current_intent,
        parsed_intent=envelope_parsed_intent,
        planning_state=envelope_planning_state,
        follow_up_interpretation=assumptions.follow_up_interpretation,
        compile_summary=build_trip_intent_compile_summary(current_intent),
        completion_candidate_history=completion_candidate_history or [],
        summary_lines=unique_preserve_order(
            [
                *assumptions.summary_lines,
                *current_intent.notes,
            ]
        )[:8],
    )


def build_parsed_intent_from_regeneration_intent(
    intent: RegenerationIntentSummary,
) -> ParsedTripIntentResponse:
    scenic_spots = filter_rejected_names(
        intent.carry_forward_scenic_spots or intent.flexible_scenic_spots,
        intent.rejected_scenic_spots,
    )
    restaurants = filter_rejected_names(
        intent.carry_forward_restaurants or intent.flexible_restaurants,
        intent.rejected_restaurants,
    )
    return normalize_parsed_trip_intent(
        ParsedTripIntentResponse(
            city=intent.city,
            trip_days=intent.trip_days,
            hotel=intent.hotel,
            arrival_anchor=intent.arrival_anchor,
            departure_anchor=intent.departure_anchor,
            availability_windows=list(intent.availability_windows),
            scenic_spots=scenic_spots,
            restaurants=restaurants,
            fixed_events=list(intent.fixed_events),
            preferences=list(intent.preferences),
            style_preferences=list(intent.style_preferences),
            style_preference_sources=dict(intent.style_preference_sources),
        )
    )


def build_trip_intent_compile_summary(
    intent: RegenerationIntentSummary,
) -> TripIntentCompileSummary:
    scenic_seed_count = len(intent.carry_forward_scenic_spots)
    restaurant_seed_count = len(intent.carry_forward_restaurants)
    rejected_poi_count = len(intent.rejected_scenic_spots) + len(
        intent.rejected_restaurants
    )
    confirmed_replacement_count = len(intent.confirmed_replacements)
    target_seed_count = max(intent.suggested_trip_days * 2, 1)
    needs_auto_completion = (
        scenic_seed_count == 0
        or restaurant_seed_count == 0
        or scenic_seed_count + restaurant_seed_count < target_seed_count
    )
    trip_days_mode = (
        "explicit"
        if intent.trip_days is not None
        else intent.trip_days_basis or "flexible"
    )

    summary_lines = [
        (
            f"当前 brief 会带着 {scenic_seed_count} 个景点种子和 "
            f"{restaurant_seed_count} 个餐食种子进入下一次再生成。"
        ),
        (
            f"行程天数是用户明确给出的 {intent.trip_days} 天。"
            if intent.trip_days is not None
            else (
                "行程天数仍是弹性的；系统会沿用当前 "
                f"{intent.suggested_trip_days} 天可执行范围继续规划。"
            )
        ),
    ]
    if intent.fixed_events or intent.availability_windows:
        summary_lines.append(
            (
                f"{len(intent.fixed_events)} 个固定安排和 "
                f"{len(intent.availability_windows)} 个可用时间窗会作为硬时间上下文保留。"
            )
        )
    if rejected_poi_count or confirmed_replacement_count:
        summary_lines.append(
            (
                f"{rejected_poi_count} 个已拒绝地点和 "
                f"{confirmed_replacement_count} 个已确认替换会影响下一次再生成。"
            )
        )
    if needs_auto_completion:
        summary_lines.append(
            "当前 brief 仍偏稀疏，确定性补全会优先补齐可执行空档。"
        )
    else:
        summary_lines.append(
            "当前 brief 已有足够保留种子，下一次再生成会更接近用户手动塑形后的版本。"
        )

    return TripIntentCompileSummary(
        city=intent.city,
        trip_days_mode=trip_days_mode,
        scenic_seed_count=scenic_seed_count,
        restaurant_seed_count=restaurant_seed_count,
        fixed_event_count=len(intent.fixed_events),
        availability_window_count=len(intent.availability_windows),
        rejected_poi_count=rejected_poi_count,
        confirmed_replacement_count=confirmed_replacement_count,
        needs_auto_completion=needs_auto_completion,
        summary_lines=summary_lines,
    )


def require_trip_intent_envelope(itinerary: ItineraryResponse) -> TripIntentEnvelope:
    if itinerary.trip_intent is None:
        raise SchedulingError("Trip intent envelope could not be built for this itinerary.")
    return itinerary.trip_intent


def build_replan_request(
    *,
    base_intent: RegenerationIntentSummary,
    follow_up_text: str,
    follow_up_intent,
    auto_fill_sparse_days: bool,
) -> tuple[ItineraryRequest, list[str], FollowUpInterpretationSummary]:
    destination_changed = bool(
        follow_up_intent.city
        and base_intent.city
        and follow_up_intent.city.strip() != base_intent.city.strip()
    )
    base_rejected_scenic = [] if destination_changed else list(base_intent.rejected_scenic_spots)
    base_rejected_restaurants = (
        [] if destination_changed else list(base_intent.rejected_restaurants)
    )
    base_scenic = filter_rejected_names(
        [] if destination_changed else list(base_intent.carry_forward_scenic_spots),
        base_rejected_scenic,
    )
    base_restaurants = filter_rejected_names(
        [] if destination_changed else list(base_intent.carry_forward_restaurants),
        base_rejected_restaurants,
    )
    newly_rejected_scenic = extract_rejected_seed_names(follow_up_text, base_scenic)
    newly_rejected_restaurants = extract_rejected_seed_names(follow_up_text, base_restaurants)
    rejected_scenic = unique_preserve_order(
        [*base_rejected_scenic, *newly_rejected_scenic]
    )
    rejected_restaurants = unique_preserve_order(
        [*base_rejected_restaurants, *newly_rejected_restaurants]
    )
    merged_scenic = unique_preserve_order(
        [
            name
            for name in base_scenic
            if name not in rejected_scenic
        ]
        + [
            name
            for name in follow_up_intent.scenic_spots
            if not name_is_rejected(name, rejected_scenic)
        ]
    )
    merged_restaurants = unique_preserve_order(
        [
            name
            for name in base_restaurants
            if name not in rejected_restaurants
        ]
        + [
            name
            for name in follow_up_intent.restaurants
            if not name_is_rejected(name, rejected_restaurants)
        ]
    )
    merged_fixed_events = (
        unique_fixed_events(follow_up_intent.fixed_events)
        if destination_changed
        else unique_fixed_events([*base_intent.fixed_events, *follow_up_intent.fixed_events])
    )
    merged_availability_windows = (
        unique_availability_windows(follow_up_intent.availability_windows)
        if destination_changed
        else unique_availability_windows(
            [*base_intent.availability_windows, *follow_up_intent.availability_windows]
        )
    )
    merged_preferences = unique_preserve_order(
        [
            *base_intent.preferences,
            *follow_up_intent.preferences,
        ]
    )
    merged_payload = ItineraryRequest(
        city=follow_up_intent.city or base_intent.city,
        scenic_spots=[
            *({"name": name} for name in merged_scenic),
            *(
                build_raw_poi_payload(event)
                for event in merged_fixed_events
                if event.category != "restaurant"
            ),
        ],
        restaurants=[
            *({"name": name} for name in merged_restaurants),
            *(
                build_raw_poi_payload(event)
                for event in merged_fixed_events
                if event.category == "restaurant"
            ),
        ],
        hotel=(
            {"name": follow_up_intent.hotel}
            if follow_up_intent.hotel
            else {"name": base_intent.hotel}
            if base_intent.hotel and not destination_changed
            else None
        ),
        travel_mode=base_intent.travel_mode,
        arrival_anchor=(
            follow_up_intent.arrival_anchor
            or (None if destination_changed else base_intent.arrival_anchor)
        ),
        departure_anchor=(
            follow_up_intent.departure_anchor
            or (None if destination_changed else base_intent.departure_anchor)
        ),
        availability_windows=merged_availability_windows,
        preferences=merged_preferences,
        rejected_scenic_spots=rejected_scenic,
        rejected_restaurants=rejected_restaurants,
        confirmed_replacements=[] if destination_changed else list(base_intent.confirmed_replacements),
        auto_fill_sparse_days=auto_fill_sparse_days,
        trip_days=(
            follow_up_intent.trip_days
            if follow_up_intent.trip_days is not None
            else None if destination_changed else base_intent.trip_days
        ),
    )
    interpretation_summary = build_follow_up_interpretation_summary(
        follow_up_text=follow_up_text,
        follow_up_intent=follow_up_intent,
        destination_changed=destination_changed,
        rejected_scenic=newly_rejected_scenic,
        rejected_restaurants=newly_rejected_restaurants,
        base_scenic=base_scenic,
        base_restaurants=base_restaurants,
    )
    return merged_payload, build_replan_merge_notes(
        base_intent=base_intent,
        follow_up_intent=follow_up_intent,
        destination_changed=destination_changed,
        rejected_scenic=newly_rejected_scenic,
        rejected_restaurants=newly_rejected_restaurants,
        merged_scenic=merged_scenic,
        merged_restaurants=merged_restaurants,
    ), interpretation_summary


def build_follow_up_interpretation_summary(
    *,
    follow_up_text: str,
    follow_up_intent,
    destination_changed: bool,
    rejected_scenic: list[str],
    rejected_restaurants: list[str],
    base_scenic: list[str],
    base_restaurants: list[str],
) -> FollowUpInterpretationSummary:
    added_scenic_spots = [
        name for name in follow_up_intent.scenic_spots if name not in base_scenic
    ]
    added_restaurants = [
        name for name in follow_up_intent.restaurants if name not in base_restaurants
    ]
    summary_lines: list[str] = []
    if destination_changed and follow_up_intent.city:
        summary_lines.append(f"Destination changed to {follow_up_intent.city}.")
    if added_scenic_spots:
        summary_lines.append(
            "Added scenic seeds: " + " / ".join(added_scenic_spots) + "."
        )
    if added_restaurants:
        summary_lines.append(
            "Added food seeds: " + " / ".join(added_restaurants) + "."
        )
    if rejected_scenic or rejected_restaurants:
        rejected_names = [*rejected_scenic, *rejected_restaurants]
        summary_lines.append(
            "Removed from the current brief: " + " / ".join(rejected_names) + "."
        )
    if follow_up_intent.fixed_events:
        summary_lines.append(
            f"已加入 {len(follow_up_intent.fixed_events)} 个固定安排。"
        )
    if follow_up_intent.availability_windows:
        summary_lines.append(
            f"已加入 {len(follow_up_intent.availability_windows)} 个可用时间窗。"
        )
    if follow_up_intent.trip_days is not None:
        summary_lines.append(
            f"Pinned trip length to {follow_up_intent.trip_days} day"
            f"{'' if follow_up_intent.trip_days == 1 else 's'}."
        )
    if follow_up_intent.preferences:
        summary_lines.append(
            "Added preference cues: " + " / ".join(follow_up_intent.preferences) + "."
        )
    if not summary_lines:
        summary_lines.append(
            "Follow-up mostly kept the current brief and only refined the next deterministic run."
        )
    return FollowUpInterpretationSummary(
        raw_text=follow_up_text.strip(),
        destination_changed_to=follow_up_intent.city if destination_changed else None,
        pinned_trip_days=follow_up_intent.trip_days,
        added_scenic_spots=added_scenic_spots,
        added_restaurants=added_restaurants,
        removed_scenic_spots=rejected_scenic,
        removed_restaurants=rejected_restaurants,
        added_fixed_events=list(follow_up_intent.fixed_events),
        added_availability_windows=list(follow_up_intent.availability_windows),
        added_preferences=list(follow_up_intent.preferences),
        summary_lines=summary_lines,
    )


def build_raw_poi_payload(event: ParsedFixedEvent) -> dict[str, object]:
    return {
        "name": event.name,
        "fixed_day": event.fixed_day,
        "fixed_time_start": event.fixed_time_start,
        "fixed_time_end": event.fixed_time_end,
    }


def is_actionable_fixed_event_poi(event: ParsedFixedEvent) -> bool:
    """
    Only fixed events with a place-like name should enter the deterministic POI scheduler.

    Generic commitments such as "预约" are useful interaction context, but they are
    not route anchors. Geocoding them as POIs can create random map origins and
    unrealistic first-leg distances.
    """
    return event.name.strip() not in {"预约", "有安排", "安排"}


def filter_rejected_names(values: list[str], rejected_values: list[str]) -> list[str]:
    return [
        value
        for value in values
        if not name_is_rejected(value, rejected_values)
    ]


def name_is_rejected(value: str, rejected_values: list[str]) -> bool:
    normalized = value.strip().casefold()
    return any(rejected.strip().casefold() == normalized for rejected in rejected_values)


def build_replan_merge_notes(
    *,
    base_intent: RegenerationIntentSummary,
    follow_up_intent,
    destination_changed: bool,
    rejected_scenic: list[str],
    rejected_restaurants: list[str],
    merged_scenic: list[str],
    merged_restaurants: list[str],
) -> list[str]:
    notes = [
        "Follow-up replan used the current regenerate brief as the base instead of restarting from an empty form.",
    ]
    if destination_changed:
        notes.append(
            f"Destination changed from {base_intent.city} to {follow_up_intent.city}, so old carry-forward seeds and anchors were reset before rebuilding."
        )
    if rejected_scenic or rejected_restaurants:
        rejected_names = [*rejected_scenic, *rejected_restaurants]
        notes.append(
            "Follow-up removed carry-forward seeds you explicitly rejected: "
            + " / ".join(rejected_names)
            + "."
        )
    if follow_up_intent.fixed_events:
        notes.append(
            f"追问已把 {len(follow_up_intent.fixed_events)} 个固定安排加入下一次确定性排程。"
        )
    if follow_up_intent.availability_windows:
        notes.append(
            f"追问已加入 {len(follow_up_intent.availability_windows)} 个额外可用时间窗。"
        )
    if follow_up_intent.trip_days is not None:
        notes.append(
            f"Follow-up pinned trip_days to {follow_up_intent.trip_days} for the next regenerate."
        )
    if follow_up_intent.preferences:
        notes.append(
            f"Follow-up added {len(follow_up_intent.preferences)} new preference signal"
            f"{'' if len(follow_up_intent.preferences) == 1 else 's'}."
        )
    notes.append(
        f"Next regenerate brief now carries {len(merged_scenic)} scenic seed"
        f"{'' if len(merged_scenic) == 1 else 's'} and {len(merged_restaurants)} food seed"
        f"{'' if len(merged_restaurants) == 1 else 's'}."
    )
    return notes


def append_replan_notes_to_assumptions(
    assumptions: PlanningAssumptionSummary,
    replan_notes: list[str],
) -> PlanningAssumptionSummary:
    merged_summary_lines = unique_preserve_order([*replan_notes, *assumptions.summary_lines])
    regeneration_intent = assumptions.regeneration_intent
    if regeneration_intent is not None:
        regeneration_intent = regeneration_intent.model_copy(
            update={
                "notes": unique_preserve_order([*replan_notes, *regeneration_intent.notes]),
            }
        )
    return assumptions.model_copy(
        update={
            "summary_lines": merged_summary_lines,
            "regeneration_intent": regeneration_intent,
        }
    )


def unique_fixed_events(events: list[ParsedFixedEvent]) -> list[ParsedFixedEvent]:
    result: list[ParsedFixedEvent] = []
    seen: set[tuple[str, int | None, str | None, str | None, str | None]] = set()
    for event in events:
        key = (
            event.name,
            event.fixed_day,
            event.fixed_time_start,
            event.fixed_time_end,
            event.category,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result


def unique_availability_windows(
    windows: list[AvailabilityWindow],
) -> list[AvailabilityWindow]:
    result: list[AvailabilityWindow] = []
    seen: set[tuple[int | None, str | None, str | None, str | None]] = set()
    for window in windows:
        key = (
            window.day,
            window.label,
            window.available_start,
            window.available_end,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(window)
    return result


def extract_rejected_seed_names(text: str, candidate_names: list[str]) -> list[str]:
    normalized_text = text.replace(" ", "")
    rejected: list[str] = []
    for name in candidate_names:
        compact_name = name.replace(" ", "")
        patterns = (
            f"不要{compact_name}",
            f"不去{compact_name}",
            f"去掉{compact_name}",
            f"删掉{compact_name}",
            f"移除{compact_name}",
            f"换掉{compact_name}",
            f"把{compact_name}去掉",
            f"把{compact_name}删掉",
            f"{compact_name}不要了",
            f"{compact_name}不去了",
        )
        if any(pattern in normalized_text for pattern in patterns):
            rejected.append(name)
    return rejected


def normalize_optional_pois(
    raw_pois: Iterable[RawPOIInput],
    poi_type: POIType,
    city: str | None = None,
    trace_collector: PlannerTraceCollector | None = None,
) -> list[NormalizedPOI]:
    normalized_pois: list[NormalizedPOI] = []

    for raw_poi in raw_pois:
        try:
            if raw_poi.resolved_latitude is not None and raw_poi.resolved_longitude is not None:
                profile = infer_poi_profile(raw_poi.name, poi_type)
                normalized_poi = NormalizedPOI(
                    name=raw_poi.name,
                    type=poi_type,
                    city=city,
                    latitude=raw_poi.resolved_latitude,
                    longitude=raw_poi.resolved_longitude,
                    duration_minutes=raw_poi.resolved_duration_minutes or profile.typical_duration_minutes,
                    profile=profile.model_copy(
                        update={
                            "signal_source": "reviewed_candidate",
                            "signal_summary": "Reused the reviewed canonical-place coordinates from the intent handoff.",
                        }
                    ),
                    fixed_day=raw_poi.fixed_day,
                    fixed_time_start=raw_poi.fixed_time_start,
                    fixed_time_end=raw_poi.fixed_time_end,
                    candidate_id=raw_poi.candidate_id,
                    canonical_place_id=raw_poi.canonical_place_id,
                    provider_place_id=raw_poi.provider_place_id,
                    intent_ownership=raw_poi.intent_ownership,
                )
            else:
                normalized_poi = normalize_poi(raw_poi=raw_poi, poi_type=poi_type, city=city)
            normalized_pois.append(normalized_poi)
            if trace_collector is not None:
                trace_collector.mark_place_known()
                trace_collector.record_decision(
                    stage=PlannerDecisionStage.IDENTITY_RESOLUTION,
                    subject_type=PlannerSubjectType.CANDIDATE,
                    subject_id=stable_trace_candidate_id(normalized_poi),
                    decision=PlannerDecision.ACCEPTED,
                    reason_codes=[PlannerReasonCode.ACCEPTED_INPUT_CANDIDATE],
                    metrics={
                        "name": normalized_poi.name,
                        "type": normalized_poi.type.value,
                        "city": normalized_poi.city,
                    },
                )
        except GeocodingError as exc:
            fallback_poi = normalize_poi_from_local_catalog(
                raw_poi=raw_poi,
                poi_type=poi_type,
                city=city,
            )
            if fallback_poi is not None:
                if trace_collector is not None:
                    trace_collector.mark_place_missing()
                    trace_collector.record_decision(
                        stage=PlannerDecisionStage.IDENTITY_RESOLUTION,
                        subject_type=PlannerSubjectType.CANDIDATE,
                        subject_id=stable_trace_candidate_id(fallback_poi),
                        decision=PlannerDecision.FALLBACK_USED,
                        reason_codes=[
                            PlannerReasonCode.REJECTED_GEOCODE_FAILED,
                            PlannerReasonCode.FALLBACK_CANDIDATE_USED,
                        ],
                        metrics={
                            "name": fallback_poi.name,
                            "type": fallback_poi.type.value,
                            "city": fallback_poi.city,
                        },
                    )
                logger.info(
                    "Using local POI catalog fallback for %r after geocoding failure: %s",
                    raw_poi.name,
                    exc,
                )
                normalized_pois.append(fallback_poi)
            else:
                if trace_collector is not None:
                    trace_collector.mark_place_failed()
                    trace_collector.record_decision(
                        stage=PlannerDecisionStage.IDENTITY_RESOLUTION,
                        subject_type=PlannerSubjectType.CANDIDATE,
                        subject_id=stable_subject_id(
                            "candidate",
                            raw_poi.name.casefold(),
                            poi_type.value,
                            city or "",
                        ),
                        decision=PlannerDecision.SKIPPED,
                        reason_codes=[
                            PlannerReasonCode.REJECTED_GEOCODE_FAILED,
                            PlannerReasonCode.SKIPPED_NON_CRITICAL_PROVIDER_FAILURE,
                        ],
                        metrics={
                            "name": raw_poi.name,
                            "type": poi_type.value,
                            "city": city,
                        },
                    )
                logger.info("Skipping optional POI %r after geocoding failure: %s", raw_poi.name, exc)

    return normalized_pois


def stable_trace_candidate_id(poi: NormalizedPOI) -> str:
    if poi.canonical_place_id:
        return stable_subject_id(
            "candidate",
            poi.canonical_place_id,
            poi.provider_place_id or "",
            round(poi.latitude, 6),
            round(poi.longitude, 6),
        )
    return stable_subject_id(
        "candidate",
        poi.name.strip().casefold(),
        poi.type.value,
        poi.city or "",
        round(poi.latitude, 6),
        round(poi.longitude, 6),
    )


def build_planner_input_snapshot(
    payload: ItineraryRequest,
    *,
    raw_text_ref: str | None = None,
) -> PlannerInputSnapshot:
    fixed_event_count = sum(
        1
        for poi in [*payload.scenic_spots, *payload.restaurants]
        if poi.fixed_day is not None or poi.fixed_time_start is not None
    )
    return PlannerInputSnapshot(
        city=payload.city,
        trip_days=payload.trip_days,
        trip_days_source=payload.trip_days_source.value if payload.trip_days_source else None,
        travel_mode=payload.travel_mode.value if payload.travel_mode else None,
        scenic_seed_count=len(payload.scenic_spots),
        restaurant_seed_count=len(payload.restaurants),
        fixed_event_count=fixed_event_count,
        availability_window_count=len(payload.availability_windows),
        has_hotel=payload.hotel is not None,
        has_arrival_anchor=payload.arrival_anchor is not None,
        has_departure_anchor=payload.departure_anchor is not None,
        preference_count=len(payload.preferences),
        raw_text_ref=raw_text_ref,
    )


def build_planner_result_summary(itinerary: ItineraryResponse) -> PlannerResultSummary:
    scheduled_items = [
        item
        for day in itinerary.days
        for block in day.blocks
        for item in block.items
    ]
    return PlannerResultSummary(
        status=itinerary.planner_realism.status if itinerary.planner_realism else "completed",
        trip_days=itinerary.trip_days,
        scheduled_item_count=len(scheduled_items),
        fixed_event_count=sum(1 for item in scheduled_items if item.is_fixed),
        auto_seeded_count=sum(
            1
            for item in scheduled_items
            if item.source_type
            in {
                ScheduledPOISourceType.AUTO_SEEDED_POI,
                ScheduledPOISourceType.AUTO_SEEDED_MEAL,
            }
        ),
        auto_filled_count=sum(
            1
            for item in scheduled_items
            if item.source_type == ScheduledPOISourceType.AUTO_FILLED
        ),
        scheduled_item_refs=[
            stable_subject_id(
                "scheduled_item",
                item.name.casefold(),
                item.type.value,
                item.day,
                item.start_time.strftime("%H:%M"),
            )
            for item in scheduled_items
        ],
    )


def normalize_poi_from_local_catalog(
    *,
    raw_poi: RawPOIInput,
    poi_type: POIType,
    city: str | None,
) -> NormalizedPOI | None:
    candidate = find_local_candidate_for_raw_poi(
        name=raw_poi.name,
        poi_type=poi_type,
        city=city,
    )
    if candidate is None or candidate.latitude is None or candidate.longitude is None:
        return None

    profile = infer_poi_profile(candidate.name, candidate.type).model_copy(
        update={
            "signal_source": "local_catalog_fallback",
            "signal_summary": (
                f"Used local {normalize_candidate_city_name(city) or 'city'} candidate catalog "
                "because live geocoding was unavailable; deterministic scheduling still applies."
            ),
        }
    )
    return NormalizedPOI(
        name=candidate.name,
        type=candidate.type,
        city=normalize_candidate_city_name(city),
        latitude=float(candidate.latitude),
        longitude=float(candidate.longitude),
        # A confirmed fixed window is authoritative even when the place identity
        # falls back to the local catalog. Keep that duration through the
        # fallback instead of restoring a generic profile visit length.
        duration_minutes=raw_poi.resolved_duration_minutes or profile.typical_duration_minutes,
        profile=profile,
        fixed_day=raw_poi.fixed_day,
        fixed_time_start=raw_poi.fixed_time_start,
        fixed_time_end=raw_poi.fixed_time_end,
        intent_ownership=raw_poi.intent_ownership,
    )


def find_local_candidate_for_raw_poi(
    *,
    name: str,
    poi_type: POIType,
    city: str | None,
) -> CandidateSpec | None:
    normalized_city = normalize_candidate_city_name(city)
    candidates = [
        candidate
        for candidate in CITY_CANDIDATES.get(normalized_city or "", [])
        if candidate.type == poi_type
        and candidate.latitude is not None
        and candidate.longitude is not None
    ]
    if not candidates:
        return None

    ranked = sorted(
        candidates,
        key=lambda candidate: local_candidate_match_score(name, candidate),
        reverse=True,
    )
    best = ranked[0]
    return best if local_candidate_match_score(name, best) >= 48 else None


def local_candidate_match_score(name: str, candidate: CandidateSpec) -> int:
    target = compact_match_text(name)
    candidate_name = compact_match_text(candidate.name)
    if target == candidate_name:
        return 100
    if target and target in candidate_name:
        return 88
    if candidate_name and candidate_name in target:
        return 78
    shared_chars = len(set(target) & set(candidate_name))
    theme_score = max(
        (local_candidate_theme_score(target, theme) for theme in candidate.themes),
        default=0,
    )
    return max(min(shared_chars * 8, 56), theme_score)


def compact_match_text(value: str) -> str:
    return (
        value.casefold()
        .replace("（", "(")
        .replace("）", ")")
        .replace("·", "")
        .replace(" ", "")
        .strip()
    )


def local_candidate_theme_score(target: str, theme: str) -> int:
    theme_keywords = {
        "museum": ("博物馆", "展览", "自然", "museum"),
        "old_street": ("老街", "街区", "citywalk", "慢慢逛", "路"),
        "waterfront": ("夜景", "江景", "滨江", "外滩"),
        "street_food": ("小吃", "美食", "夜市", "吃"),
        "design": ("设计", "公馆", "新天地", "田子坊"),
        "garden": ("园林", "公园", "寺", "庙"),
        "night": ("夜景", "夜市", "晚上"),
    }
    return 64 if any(keyword in target for keyword in theme_keywords.get(theme, ())) else 0


def normalize_optional_anchor(name: str | None, city: str | None = None):
    if not name:
        return None

    try:
        return normalize_anchor(name, city=city)
    except GeocodingError as exc:
        logger.info("Skipping optional anchor %r after geocoding failure: %s", name, exc)
        return None


def normalize_optional_hotel(hotel: HotelInput | None, city: str | None = None) -> HotelStay | None:
    if hotel is None:
        return None
    return normalize_hotel(hotel, city=city)


def request_contains_unresolved_planning_seeds(payload: ItineraryRequest) -> bool:
    return bool(
        payload.hotel
        or payload.arrival_anchor
        or payload.departure_anchor
        or payload.scenic_spots
        or payload.restaurants
    )


def build_unresolved_planning_seed_error(payload: ItineraryRequest) -> str:
    seed_names = [
        *(poi.name for poi in payload.scenic_spots),
        *(poi.name for poi in payload.restaurants),
    ]
    if payload.hotel:
        seed_names.append(payload.hotel.name)
    if payload.arrival_anchor:
        seed_names.append(payload.arrival_anchor)
    if payload.departure_anchor:
        seed_names.append(payload.departure_anchor)

    preview = " / ".join(seed_names[:5]) or "the provided trip seeds"
    capability = get_poi_discovery_capability()
    if not capability.poi_discovery_enabled:
        return (
            "I found trip seeds, but could not resolve them into executable map locations "
            f"({preview}). Realtime POI discovery is unavailable: "
            f"{capability.failure_reason or 'AMAP_API_KEY is not configured.'}"
        )
    return (
        "I found trip seeds, but none could be resolved into executable map locations "
        f"({preview}). Please check the place names or try adding a more specific city/landmark."
    )


def build_sparse_city_bootstrap_pois(
    *,
    city: str | None,
    preferences: list[str],
    needs_scenic: bool,
    needs_restaurants: bool,
    target_trip_days: int = 1,
) -> tuple[list[NormalizedPOI], list[NormalizedPOI]]:
    if not city or (not needs_scenic and not needs_restaurants):
        return [], []

    normalized_city = normalize_candidate_city_name(city)
    candidates = CITY_CANDIDATES.get(normalized_city or "")
    if not candidates:
        return [], []

    preference_text = " ".join(preferences).casefold()
    scenic_candidates = [
        candidate
        for candidate in candidates
        if candidate.type == POIType.SCENIC
        and candidate.latitude is not None
        and candidate.longitude is not None
    ]
    restaurant_candidates = [
        candidate
        for candidate in candidates
        if candidate.type == POIType.RESTAURANT
        and candidate.latitude is not None
        and candidate.longitude is not None
    ]

    scenic_limit = 2
    if any(token in preference_text for token in ("高效", "多逛", "尽量排满", "packed")):
        scenic_limit = 3
    if any(token in preference_text for token in ("轻松", "别太赶", "休息", "relaxed")):
        scenic_limit = 1

    meal_anchor_target = max(target_trip_days * 2, 2)
    restaurant_limit = min(len(restaurant_candidates), meal_anchor_target)
    scenic = [
        candidate_to_normalized_poi(candidate, normalized_city)
        for candidate in sorted(
            scenic_candidates,
            key=lambda candidate: bootstrap_candidate_rank(candidate, preference_text),
        )[:scenic_limit]
    ] if needs_scenic else []
    restaurants = [
        candidate_to_normalized_poi(candidate, normalized_city)
        for candidate in sorted(
            restaurant_candidates,
            key=lambda candidate: bootstrap_candidate_rank(candidate, preference_text),
        )[:restaurant_limit]
    ] if needs_restaurants else []
    return scenic, restaurants


def annotate_bootstrap_items(
    *,
    itinerary: ItineraryResponse,
    bootstrap_scenic: list[NormalizedPOI],
    bootstrap_restaurants: list[NormalizedPOI],
) -> None:
    scenic_names = {poi.name for poi in bootstrap_scenic}
    restaurant_names = {poi.name for poi in bootstrap_restaurants}
    if not scenic_names and not restaurant_names:
        return

    for day in itinerary.days:
        for block in day.blocks:
            for item in block.items:
                if item.name in scenic_names:
                    item.source_type = ScheduledPOISourceType.AUTO_SEEDED_POI
                    item.source_label = "系统补点"
                    item.source_reason = (
                        "系统根据目的地和偏好补入这个起步地点，"
                        "让路线先形成可执行的旅行骨架。"
                    )
                    item.placement_reason = append_reason_prefix(
                        item.placement_reason,
                        (
                            "系统从稀疏输入里补入这个地点，"
                            "让旅行骨架先跑起来。"
                        ),
                    )
                elif item.name in restaurant_names:
                    item.source_type = ScheduledPOISourceType.AUTO_SEEDED_MEAL
                    item.source_label = "系统餐食锚点"
                    item.source_reason = (
                        "系统补入这个餐食锚点，"
                        "让午餐或晚餐成为路线节奏的一部分。"
                    )
                    item.placement_reason = append_reason_prefix(
                        item.placement_reason,
                        (
                            "系统从稀疏输入里补入这个餐食锚点，"
                            "让吃饭不再是路线外的临时决定。"
                        ),
                    )


def append_reason_prefix(existing_reason: str | None, prefix: str) -> str:
    if existing_reason and existing_reason.startswith(prefix):
        return existing_reason
    if existing_reason:
        return f"{prefix} {existing_reason}"
    return prefix


def build_planning_assumption_summary(
    *,
    payload: ItineraryRequest,
    itinerary: ItineraryResponse,
    bootstrap_scenic: list[NormalizedPOI],
    bootstrap_restaurants: list[NormalizedPOI],
    request_style_signal=None,
) -> PlanningAssumptionSummary:
    scheduled_items = [
        item
        for day in itinerary.days
        for block in day.blocks
        for item in block.items
    ]
    flexible_scenic = [
        poi.name
        for poi in payload.scenic_spots
        if poi.fixed_day is None and poi.fixed_time_start is None
    ]
    flexible_restaurants = [
        poi.name
        for poi in payload.restaurants
        if poi.fixed_day is None and poi.fixed_time_start is None
    ]
    fixed_events = [
        build_fixed_event_summary(poi, "scenic")
        for poi in payload.scenic_spots
        if poi.fixed_day is not None or poi.fixed_time_start is not None
    ] + [
        build_fixed_event_summary(poi, "restaurant")
        for poi in payload.restaurants
        if poi.fixed_day is not None or poi.fixed_time_start is not None
    ]
    style_preference_sources = (
        style_preference_sources_from_signal(request_style_signal)
        if request_style_signal is not None
        else {}
    )
    style_preferences = ordered_style_preferences(style_preference_sources.keys())
    auto_seeded_scenic_names = [poi.name for poi in bootstrap_scenic]
    auto_seeded_restaurant_names = [poi.name for poi in bootstrap_restaurants]
    carry_forward_scenic = filter_rejected_names(
        unique_preserve_order([*flexible_scenic, *auto_seeded_scenic_names]),
        payload.rejected_scenic_spots,
    )
    carry_forward_restaurants = filter_rejected_names(
        unique_preserve_order([*flexible_restaurants, *auto_seeded_restaurant_names]),
        payload.rejected_restaurants,
    )
    auto_filled_count = sum(
        1
        for item in scheduled_items
        if item.source_type == ScheduledPOISourceType.AUTO_FILLED
    )
    trip_days_basis = determine_trip_days_basis(payload)
    trip_days_for_regeneration = (
        payload.trip_days
        if trip_days_basis == TripDaysInputSource.EXPLICIT.value
        else None
    )
    trip_scope_estimate = build_trip_scope_estimate_for_request(
        payload=payload,
        flexible_scenic=flexible_scenic,
        flexible_restaurants=flexible_restaurants,
        fixed_events=fixed_events,
    )
    fixed_event_count = len(fixed_events)
    regeneration_notes = [
        build_trip_days_regeneration_note(
            trip_days_basis=trip_days_basis,
            trip_days=payload.trip_days,
        ),
        (
            f"行程范围估计：{trip_scope_estimate.estimated_trip_days} 天 · "
            f"{trip_scope_estimate.confidence.value} 置信度 · "
            f"{trip_scope_estimate.poi_load_level.value} POI 密度。"
        ),
        (
            "carry_forward_* 会把用户种子、系统起步补点和固定安排分开保存，后续刷新可以保留当前骨架，也可以基于稀疏 brief 重新估计。"
        ),
    ]
    if auto_filled_count:
        regeneration_notes.append(
            "自动补全的稀疏时段会单独汇总，默认不会直接提升为 carry_forward 种子。"
        )
    if payload.confirmed_replacements:
        regeneration_notes.append(
            f"{len(payload.confirmed_replacements)} user-confirmed replacement"
            f"{'' if len(payload.confirmed_replacements) == 1 else 's'} are preserved as owned intent for regeneration."
        )
    if payload.rejected_scenic_spots or payload.rejected_restaurants:
        regeneration_notes.append(
            "Rejected POIs are kept out of carry-forward seeds: "
            + " / ".join([*payload.rejected_scenic_spots, *payload.rejected_restaurants])
            + "."
        )
    summary_lines = [
        build_trip_days_summary_line(
            trip_days_basis=trip_days_basis,
            trip_days=payload.trip_days,
            itinerary_days=itinerary.trip_days,
        ),
        (
            f"用户种草点与硬约束已分离：{len(flexible_scenic)} 个景点线索，"
            f"{len(flexible_restaurants)} 个餐食线索。"
        ),
    ]
    if fixed_event_count:
        summary_lines.append(
            f"{fixed_event_count} 个固定安排已保留在可再生成的约束列表里，不会混进灵活种草点。"
        )
    if bootstrap_scenic or bootstrap_restaurants:
        summary_lines.append(
            f"系统为稀疏输入自动补入 {len(bootstrap_scenic)} 个起步地点和 "
            f"{len(bootstrap_restaurants)} 个餐食锚点。"
        )
    if auto_filled_count:
        summary_lines.append(
            f"初版骨架完成后，系统继续修复了 {auto_filled_count} 个稀疏时段。"
        )
    if payload.availability_windows:
        summary_lines.append(
            f"{len(payload.availability_windows)} 个可用时间窗已用于塑形每天边界。"
        )
    summary_lines.append(
        f"合理行程范围估计：{trip_scope_estimate.estimated_trip_days} 天，"
        f"依据 {trip_scope_estimate.poi_load_level.value} 输入密度和 "
        f"{trip_scope_estimate.confidence.value} 置信度。"
    )
    summary_lines.append(
        f"已准备可再生成 brief：{len(carry_forward_scenic)} 个景点种子，"
        f"{len(carry_forward_restaurants)} 个餐食种子。"
    )

    return PlanningAssumptionSummary(
        destination=payload.city,
        trip_days_basis=trip_days_basis,
        trip_scope_estimate=trip_scope_estimate,
        user_seed_scenic_count=len(flexible_scenic),
        user_seed_restaurant_count=len(flexible_restaurants),
        fixed_event_count=fixed_event_count,
        availability_window_count=len(payload.availability_windows),
        auto_seeded_poi_count=len(bootstrap_scenic),
        auto_seeded_meal_count=len(bootstrap_restaurants),
        auto_filled_count=auto_filled_count,
        meal_structure_applied=True,
        summary_lines=summary_lines,
        execution_trace=build_planning_execution_trace(itinerary),
        regeneration_intent=RegenerationIntentSummary(
            city=payload.city,
            travel_mode=payload.travel_mode,
            hotel=payload.hotel.name if payload.hotel is not None else None,
            arrival_anchor=payload.arrival_anchor,
            departure_anchor=payload.departure_anchor,
            availability_windows=list(payload.availability_windows),
            trip_days=trip_days_for_regeneration,
            suggested_trip_days=itinerary.trip_days,
            trip_days_basis=trip_days_basis,
            flexible_scenic_spots=flexible_scenic,
            flexible_restaurants=flexible_restaurants,
            fixed_events=fixed_events,
            preferences=list(payload.preferences),
            style_preferences=style_preferences,
            style_preference_sources=style_preference_sources,
            auto_seeded_scenic_spots=auto_seeded_scenic_names,
            auto_seeded_restaurants=auto_seeded_restaurant_names,
            carry_forward_scenic_spots=carry_forward_scenic,
            carry_forward_restaurants=carry_forward_restaurants,
            rejected_scenic_spots=list(payload.rejected_scenic_spots),
            rejected_restaurants=list(payload.rejected_restaurants),
            confirmed_replacements=list(payload.confirmed_replacements),
            notes=regeneration_notes,
        ),
    )


def build_planning_execution_trace(
    itinerary: ItineraryResponse,
) -> list[PlanningExecutionTraceItem]:
    trace: list[PlanningExecutionTraceItem] = []
    for day in itinerary.days:
        for block in day.blocks:
            for item in block.items:
                trace.append(
                    PlanningExecutionTraceItem(
                        item_name=item.name,
                        item_type=item.type,
                        day=day.day,
                        block_type=block.block_type,
                        source_type=item.source_type,
                        decision_type=planning_decision_type_for_source(item.source_type),
                        decision_stage=planning_decision_stage_for_source(item.source_type),
                        ownership_type=planning_ownership_type_for_source(item.source_type),
                        timing_role=planning_timing_role_for_item(
                            item=item,
                            block_type=block.block_type,
                        ),
                        is_user_owned=planning_item_is_user_owned(item.source_type),
                        is_hard_constraint=planning_item_is_hard_constraint(item),
                        is_editable=not planning_item_is_hard_constraint(item),
                        summary=build_execution_trace_summary(item),
                        evidence=build_planning_decision_trace_evidence(
                            item=item,
                            block_type=block.block_type,
                        ),
                    )
                )
    return trace


def planning_decision_type_for_source(source_type: ScheduledPOISourceType) -> str:
    if source_type == ScheduledPOISourceType.USER_FIXED:
        return "hard_user_constraint"
    if source_type == ScheduledPOISourceType.USER_SEED:
        return "user_seed_scheduled"
    if source_type == ScheduledPOISourceType.AUTO_SEEDED_POI:
        return "system_seed_completion"
    if source_type == ScheduledPOISourceType.AUTO_SEEDED_MEAL:
        return "system_meal_completion"
    if source_type == ScheduledPOISourceType.AUTO_FILLED:
        return "system_gap_fill"
    return "scheduled_item"


def planning_decision_stage_for_source(source_type: ScheduledPOISourceType) -> str:
    if source_type == ScheduledPOISourceType.USER_FIXED:
        return "constraint_enforcement"
    if source_type == ScheduledPOISourceType.USER_SEED:
        return "seed_scheduling"
    if source_type in {
        ScheduledPOISourceType.AUTO_SEEDED_POI,
        ScheduledPOISourceType.AUTO_SEEDED_MEAL,
    }:
        return "sparse_brief_bootstrap"
    if source_type == ScheduledPOISourceType.AUTO_FILLED:
        return "gap_completion"
    return "deterministic_scheduling"


def planning_ownership_type_for_source(source_type: ScheduledPOISourceType) -> str:
    if source_type == ScheduledPOISourceType.USER_FIXED:
        return "user_fixed_constraint"
    if source_type == ScheduledPOISourceType.USER_SEED:
        return "user_seed_or_confirmed_intent"
    if source_type == ScheduledPOISourceType.AUTO_SEEDED_POI:
        return "system_auto_seeded_poi"
    if source_type == ScheduledPOISourceType.AUTO_SEEDED_MEAL:
        return "system_auto_seeded_meal"
    if source_type == ScheduledPOISourceType.AUTO_FILLED:
        return "system_auto_filled_gap"
    return "planner_scheduled"


def planning_timing_role_for_item(
    *,
    item: ScheduledPOI,
    block_type: TimeBlockType,
) -> str:
    if item.source_type == ScheduledPOISourceType.USER_FIXED or item.is_fixed:
        return "fixed_time_constraint"
    if item.type == POIType.RESTAURANT and block_type == TimeBlockType.AFTERNOON:
        return "lunch_anchor"
    if item.type == POIType.RESTAURANT and block_type == TimeBlockType.EVENING:
        return "dinner_anchor"
    if item.source_type == ScheduledPOISourceType.AUTO_FILLED:
        return f"{block_type.value}_gap_fill"
    if block_type == TimeBlockType.MORNING:
        return "morning_visit"
    if block_type == TimeBlockType.AFTERNOON:
        return "afternoon_visit"
    return "evening_activity"


def planning_item_is_user_owned(source_type: ScheduledPOISourceType) -> bool:
    return source_type in {
        ScheduledPOISourceType.USER_FIXED,
        ScheduledPOISourceType.USER_SEED,
    }


def planning_item_is_hard_constraint(item: ScheduledPOI) -> bool:
    return item.is_fixed or item.source_type == ScheduledPOISourceType.USER_FIXED


def build_planning_decision_trace_evidence(
    *,
    item: ScheduledPOI,
    block_type: TimeBlockType,
) -> PlanningDecisionTraceEvidence:
    return PlanningDecisionTraceEvidence(
        why_included=build_trace_why_included(item),
        timing_decision=build_trace_timing_decision(item=item, block_type=block_type),
        ownership_signal=build_trace_ownership_signal(item),
        flexibility=build_trace_flexibility_signal(item),
        top_candidates=list(item.selection_top_candidates),
        rejected_candidates=list(item.selection_rejected_candidates),
    )


def build_trace_why_included(item: ScheduledPOI) -> str:
    if item.source_type == ScheduledPOISourceType.USER_FIXED:
        return "已纳入路线，因为这是用户给出的固定时间安排。"
    if item.source_type == ScheduledPOISourceType.USER_SEED:
        return "已纳入路线，因为它来自用户种草点或已确认的旅行意图。"
    if item.source_type == ScheduledPOISourceType.AUTO_SEEDED_POI:
        return "已纳入路线，因为输入较稀疏，需要一个起步地点让骨架先跑起来。"
    if item.source_type == ScheduledPOISourceType.AUTO_SEEDED_MEAL:
        return "已纳入路线，因为当天需要午餐或晚餐锚点来形成真实节奏。"
    if item.source_type == ScheduledPOISourceType.AUTO_FILLED:
        return "已纳入路线，因为生成骨架中仍有可修复空档。"
    return "已由确定性排程器纳入当前行程。"


def build_trace_timing_decision(
    *,
    item: ScheduledPOI,
    block_type: TimeBlockType,
) -> str:
    if planning_item_is_hard_constraint(item):
        return (
            f"保留在 {item.start_time.strftime('%H:%M')}-{item.end_time.strftime('%H:%M')}，"
            "因为固定时间优先级高于灵活路线塑形。"
        )
    timing_role = planning_timing_role_for_item(item=item, block_type=block_type)
    if timing_role == "lunch_anchor":
        return "放在下午时段，作为景点之间的午餐锚点。"
    if timing_role == "dinner_anchor":
        return "放在夜间时段，作为夜游前或夜游中的晚餐锚点。"
    if item.source_type == ScheduledPOISourceType.AUTO_FILLED:
        return "插入建议时段，不重新打乱整天路线。"
    return item.placement_reason or "已放入确定性路线与时间规则选中的时段。"


def build_trace_ownership_signal(item: ScheduledPOI) -> str:
    if item.source_type == ScheduledPOISourceType.USER_FIXED:
        return "用户拥有的硬约束。"
    if item.source_type == ScheduledPOISourceType.USER_SEED:
        return "用户拥有的种草点或已确认替换项。"
    if item.source_type == ScheduledPOISourceType.AUTO_SEEDED_POI:
        return "系统补入的起步地点，会显式标记为自动补全，不伪装成用户意图。"
    if item.source_type == ScheduledPOISourceType.AUTO_SEEDED_MEAL:
        return "系统补入的餐食锚点，会显式标记为自动补全，不伪装成用户意图。"
    if item.source_type == ScheduledPOISourceType.AUTO_FILLED:
        return "系统补入的空档修复项，只有用户保留后才进入后续意图。"
    return "排程器安排的路线项。"


def build_trace_flexibility_signal(item: ScheduledPOI) -> str:
    if planning_item_is_hard_constraint(item):
        return "除非用户修改固定约束，否则不应灵活移动。"
    if item.source_type == ScheduledPOISourceType.USER_SEED:
        return "时间可灵活调整，但后续再生成时会视为用户拥有的意图。"
    if item.source_type in {
        ScheduledPOISourceType.AUTO_SEEDED_POI,
        ScheduledPOISourceType.AUTO_SEEDED_MEAL,
        ScheduledPOISourceType.AUTO_FILLED,
    }:
        return "可替换、可排除；后续只有被用户保留才会进入意图。"
    return "默认可灵活调整，除非被提升为用户意图。"


def build_execution_trace_summary(item: ScheduledPOI) -> str:
    if item.source_type == ScheduledPOISourceType.USER_FIXED:
        return (
            item.placement_reason
            or "用户给出的固定时间已作为硬约束保留。"
        )
    if item.source_type == ScheduledPOISourceType.USER_SEED:
        return (
            item.placement_reason
            or "你给出的种草地点已由确定性排程器放入路线。"
        )
    if item.source_type == ScheduledPOISourceType.AUTO_SEEDED_POI:
        return (
            item.source_reason
            or "系统根据目的地和偏好补入这个起步地点，让路线先形成可执行的旅行骨架。"
        )
    if item.source_type == ScheduledPOISourceType.AUTO_SEEDED_MEAL:
        return (
            item.source_reason
            or "系统补入这个餐食锚点，让午餐或晚餐成为路线节奏的一部分。"
        )
    if item.source_type == ScheduledPOISourceType.AUTO_FILLED:
        return (
            item.source_reason
            or item.placement_reason
            or "系统插入这个地点，用来修复可执行路线中的空档。"
        )
    return item.placement_reason or "已由确定性行程排程器安排。"


def build_fixed_event_summary(raw_poi: RawPOIInput, category: str) -> ParsedFixedEvent:
    return ParsedFixedEvent(
        name=raw_poi.name,
        fixed_day=raw_poi.fixed_day,
        fixed_time_start=raw_poi.fixed_time_start.strftime("%H:%M")
        if raw_poi.fixed_time_start is not None
        else None,
        fixed_time_end=raw_poi.fixed_time_end.strftime("%H:%M")
        if raw_poi.fixed_time_end is not None
        else None,
        category=category,
    )


def build_trip_scope_estimate_for_request(
    *,
    payload: ItineraryRequest,
    flexible_scenic: list[str],
    flexible_restaurants: list[str],
    fixed_events: list[ParsedFixedEvent],
):
    trip_days_basis = determine_trip_days_basis(payload)
    parsed_intent = ParsedTripIntentResponse(
        city=payload.city,
        trip_days=(
            payload.trip_days
            if trip_days_basis == TripDaysInputSource.EXPLICIT.value
            else None
        ),
        hotel=payload.hotel.name if payload.hotel is not None else None,
        arrival_anchor=payload.arrival_anchor,
        departure_anchor=payload.departure_anchor,
        availability_windows=list(payload.availability_windows),
        scenic_spots=flexible_scenic,
        restaurants=flexible_restaurants,
        fixed_events=fixed_events,
        preferences=list(payload.preferences),
    )
    preference_state = classify_preference_state(parsed_intent.preferences)
    return estimate_trip_scope(parsed_intent, preference_state.strength)


def determine_trip_days_basis(payload: ItineraryRequest) -> str:
    if payload.trip_days_source is not None:
        return payload.trip_days_source.value
    return (
        TripDaysInputSource.EXPLICIT.value
        if payload.trip_days is not None
        else "scheduler_estimated"
    )


def build_trip_days_regeneration_note(
    *,
    trip_days_basis: str,
    trip_days: int | None,
) -> str:
    if trip_days_basis == TripDaysInputSource.EXPLICIT.value:
        return "trip_days stays pinned on regeneration because the user explicitly set the duration."
    if trip_days_basis == TripDaysInputSource.INTERACTION_ESTIMATED.value:
        return (
            f"trip_days was estimated as {trip_days} day"
            f"{'' if trip_days == 1 else 's'} by the interaction layer; "
            "regeneration keeps duration flexible unless the user pins the current scope."
        )
    return "trip_days remains flexible for regeneration; use suggested_trip_days if you want to pin the current scope."


def build_trip_days_summary_line(
    *,
    trip_days_basis: str,
    trip_days: int | None,
    itinerary_days: int,
) -> str:
    if trip_days_basis == TripDaysInputSource.EXPLICIT.value:
        return (
            f"Trip length came from the user input: {trip_days} day"
            f"{'' if trip_days == 1 else 's'}."
        )
    if trip_days_basis == TripDaysInputSource.INTERACTION_ESTIMATED.value:
        return (
            f"Trip length was estimated from the natural-language brief into {itinerary_days} executable day"
            f"{'' if itinerary_days == 1 else 's'}."
        )
    return (
        f"Trip length was estimated by the scheduler into {itinerary_days} executable day"
        f"{'' if itinerary_days == 1 else 's'}."
    )


def unique_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def bootstrap_candidate_rank(candidate: CandidateSpec, preference_text: str) -> tuple[int, int, str]:
    candidate_themes = set(candidate.themes)
    score = 0
    if any(token in preference_text for token in ("美食", "吃", "餐", "food")) and (
        candidate.type == POIType.RESTAURANT or "street_food" in candidate_themes
    ):
        score -= 8
    if any(token in preference_text for token in ("夜景", "晚上", "夜", "night")) and (
        "night" in candidate_themes or "waterfront" in candidate_themes
    ):
        score -= 5
    if any(token in preference_text for token in ("老街", "街区", "citywalk", "逛")) and (
        "old_street" in candidate_themes or "design" in candidate_themes
    ):
        score -= 4
    if any(token in preference_text for token in ("博物馆", "展览", "文化", "museum")) and (
        "museum" in candidate_themes
    ):
        score -= 4
    if any(token in preference_text for token in ("轻松", "别太赶", "休息", "relaxed")):
        score += 1 if candidate.profile_intensity == "heavy" else -1
    return (score, candidate.duration_minutes, candidate.name)


def candidate_to_normalized_poi(
    candidate: CandidateSpec,
    city: str | None,
) -> NormalizedPOI:
    profile = infer_poi_profile(candidate.name, candidate.type)
    return NormalizedPOI(
        name=candidate.name,
        type=candidate.type,
        city=city,
        latitude=float(candidate.latitude),
        longitude=float(candidate.longitude),
        duration_minutes=profile.typical_duration_minutes,
        profile=profile,
    )


def resolve_planning_anchor(
    provided_hotel: HotelStay | None,
    scenic_spots: list[NormalizedPOI],
    restaurants: list[NormalizedPOI],
    arrival_anchor: HotelStay | None,
    departure_anchor: HotelStay | None,
    city: str | None = None,
) -> tuple[HotelStay, PlanningAnchorSource]:
    if provided_hotel is not None:
        return provided_hotel, PlanningAnchorSource(
            source_type="provided_hotel",
            source_name=provided_hotel.name,
            latitude=provided_hotel.latitude,
            longitude=provided_hotel.longitude,
        )

    if arrival_anchor is not None:
        return arrival_anchor, PlanningAnchorSource(
            source_type="arrival_anchor",
            source_name=arrival_anchor.name,
            latitude=arrival_anchor.latitude,
            longitude=arrival_anchor.longitude,
        )

    if departure_anchor is not None:
        return departure_anchor, PlanningAnchorSource(
            source_type="departure_anchor",
            source_name=departure_anchor.name,
            latitude=departure_anchor.latitude,
            longitude=departure_anchor.longitude,
        )

    fallback_pois = scenic_spots + restaurants
    if fallback_pois:
        first_poi = select_soft_route_anchor_poi(fallback_pois)
        anchor_name = (
            f"{first_poi.name}附近路线中心"
            if len(fallback_pois) > 1
            else first_poi.name
        )
        fallback_anchor = HotelStay(
            name=anchor_name,
            city=city or first_poi.city,
            latitude=first_poi.latitude,
            longitude=first_poi.longitude,
        )
        return fallback_anchor, PlanningAnchorSource(
            source_type="route_soft_anchor" if len(fallback_pois) > 1 else "fallback_poi",
            source_name=anchor_name,
            latitude=fallback_anchor.latitude,
            longitude=fallback_anchor.longitude,
        )

    raise SchedulingError(
        "Add at least one scenic spot, restaurant, fixed event, hotel, or boundary anchor before generating."
    )


def select_soft_route_anchor_poi(pois: list[NormalizedPOI]) -> NormalizedPOI:
    """
    Pick a representative soft anchor when the user did not provide a hotel,
    arrival hub, or departure hub.

    Using the first POI as the daily base makes sparse natural-language trips
    brittle: a remote first seed (for example 兵马俑) can turn every city-center
    day into a 500-minute transfer. The deterministic scheduler still receives
    an explicit anchor, but this anchor is now the medoid of the supplied POI
    cluster, which is a safer product default until the user adds lodging.
    """
    if not pois:
        raise SchedulingError(
            "Add at least one scenic spot, restaurant, fixed event, hotel, or boundary anchor before generating."
        )
    if len(pois) == 1:
        return pois[0]

    def medoid_score(candidate: NormalizedPOI) -> tuple[float, str]:
        distances = [
            haversine_km(candidate.latitude, candidate.longitude, other.latitude, other.longitude)
            for other in pois
            if other is not candidate
        ]
        average_distance = sum(distances) / max(len(distances), 1)
        return average_distance, candidate.name

    return min(pois, key=medoid_score)
