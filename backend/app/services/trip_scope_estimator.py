from __future__ import annotations

from app.schemas.intent import ParsedTripIntentResponse
from app.schemas.planning_state import (
    POILoadLevel,
    PreferenceStrength,
    TripScopeConfidence,
    TripScopeEstimate,
    TripScopeEstimationMode,
)


def estimate_trip_scope(
    parsed_intent: ParsedTripIntentResponse,
    preference_strength: PreferenceStrength,
) -> TripScopeEstimate:
    if parsed_intent.trip_days is not None:
        return TripScopeEstimate(
            estimated_trip_days=parsed_intent.trip_days,
            estimation_mode=TripScopeEstimationMode.EXPLICIT,
            confidence=TripScopeConfidence.HIGH,
            poi_load_level=classify_poi_load(parsed_intent),
            reasoning_summary="用户已经明确给出旅行天数，因此不再额外估算行程范围。",
        )

    scenic_count = len(parsed_intent.scenic_spots)
    restaurant_count = len(parsed_intent.restaurants)
    fixed_event_count = len(parsed_intent.fixed_events)
    explicit_poi_count = scenic_count + restaurant_count

    estimated_days = 1
    if explicit_poi_count >= 4:
        estimated_days += 1
    if explicit_poi_count >= 8:
        estimated_days += 1
    if fixed_event_count >= 2:
        estimated_days += 1
    if preference_strength == PreferenceStrength.STRONG:
        estimated_days += 1

    latest_referenced_day = latest_day_reference(parsed_intent)
    if latest_referenced_day is not None:
        estimated_days = max(estimated_days, latest_referenced_day)

    estimated_days = min(max(1, estimated_days), 5)

    confidence = TripScopeConfidence.MEDIUM if explicit_poi_count >= 2 else TripScopeConfidence.LOW
    if latest_referenced_day is not None and latest_referenced_day >= 2:
        confidence = TripScopeConfidence.MEDIUM
    reasoning_parts = [
        f"根据 {explicit_poi_count} 个明确想去地点估算",
        f"{fixed_event_count} 个固定安排",
    ]
    if latest_referenced_day is not None:
        reasoning_parts.append(
            f"相对日期表述说明至少需要 {latest_referenced_day} 天"
        )
    if preference_strength == PreferenceStrength.STRONG:
        reasoning_parts.append("偏好较明确，适合保留更宽松的行程范围")

    return TripScopeEstimate(
        estimated_trip_days=estimated_days,
        estimation_mode=TripScopeEstimationMode.ESTIMATED,
        confidence=confidence,
        poi_load_level=classify_poi_load(parsed_intent),
        reasoning_summary=", ".join(reasoning_parts) + ".",
    )


def classify_poi_load(parsed_intent: ParsedTripIntentResponse) -> POILoadLevel:
    total_pois = len(parsed_intent.scenic_spots) + len(parsed_intent.restaurants)
    if total_pois <= 2:
        return POILoadLevel.LIGHT
    if total_pois <= 6:
        return POILoadLevel.MEDIUM
    return POILoadLevel.DENSE


def latest_day_reference(parsed_intent: ParsedTripIntentResponse) -> int | None:
    day_refs = [
        window.day
        for window in parsed_intent.availability_windows
        if window.day is not None
    ]
    day_refs.extend(
        event.fixed_day
        for event in parsed_intent.fixed_events
        if event.fixed_day is not None
    )
    return max(day_refs) if day_refs else None
