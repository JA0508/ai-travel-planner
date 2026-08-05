from __future__ import annotations

from app.schemas.trip_compiler import (
    TRIP_COMPILER_MAX_DAYS,
    TRIP_COMPILER_MIN_DAYS,
    TripCompilerPlace,
    TripCompilerPreference,
    TripCompilerFixedEvent,
    TravelIntent,
)
from app.trips.intent_contracts import IntentPlannerReadyStatus, SourceLinkedTripIntentEnvelope


class DraftIntentProjectionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def project_confirmed_draft_intent(envelope: SourceLinkedTripIntentEnvelope) -> TravelIntent:
    """Build the legacy Planning Run input from the one authoritative Draft revision."""

    if envelope.planner_ready_status not in {
        IntentPlannerReadyStatus.READY,
        IntentPlannerReadyStatus.READY_FOR_PLANNING,
    }:
        raise DraftIntentProjectionError(
            "draft_intent_not_planner_ready",
            "请先确认必去地点和其他必要信息，再生成路线。",
        )
    formal = envelope.formal_contract
    destination = formal.destinations[0].city_name if formal.destinations else None
    trip_days = formal.date_policy.trip_days if formal.date_policy else None
    if not destination or trip_days is None:
        raise DraftIntentProjectionError("draft_intent_incomplete", "请先补全目的地和旅行天数。")
    if not TRIP_COMPILER_MIN_DAYS <= trip_days <= TRIP_COMPILER_MAX_DAYS:
        raise DraftIntentProjectionError(
            "draft_intent_trip_days_unsupported",
            f"当前版本先支持 {TRIP_COMPILER_MIN_DAYS} 到 {TRIP_COMPILER_MAX_DAYS} 天的行程。",
        )
    unresolved_required = [
        identity
        for identity in formal.place_identities
        if identity.ownership in {"must", "fixed"} and identity.resolution_status != "verified"
    ]
    if unresolved_required:
        raise DraftIntentProjectionError(
            "draft_intent_place_identity_unconfirmed",
            "请先确认每个必去地点和固定安排的具体地点。",
        )
    must = [
        _place(identity, ownership="user_must")
        for identity in formal.place_identities
        if identity.ownership == "must" and identity.resolution_status == "verified"
    ]
    optional = [
        _place(identity, ownership="user_optional")
        for identity in formal.place_identities
        if identity.ownership == "optional" and identity.resolution_status == "verified"
    ]
    # Existing reviewed TripCandidates are still represented by their own formal
    # contract fields. They are intentionally not promoted to canonical POIs here.
    # That keeps one admission boundary rather than silently creating another.
    pace = formal.pace.value if formal.pace else "balanced"
    preferences = [
        TripCompilerPreference(
            stable_id=f"intent_transport_{index}",
            value=item.custom_label or item.mode,
            confidence=1.0,
            source_fragment_ids=[],
        )
        for index, item in enumerate(formal.transport_preferences)
    ]
    fixed_events = [
        TripCompilerFixedEvent(
            stable_id=item.event_id,
            name=item.title,
            day=_fixed_event_day(item.fixed_day, item.start_at, formal.date_policy.start_date if formal.date_policy else None),
            start_time=item.start_at.strftime("%H:%M") if item.start_at else None,
            end_time=item.end_at.strftime("%H:%M") if item.end_at else None,
            fixed_reason="你明确说明这是固定安排。",
            confidence=1.0,
            source_fragment_ids=[],
        )
        for item in formal.fixed_events
    ]
    return TravelIntent(
        destination=destination,
        trip_days=trip_days,
        pace=pace,
        must_visit_places=must,
        optional_places=optional,
        fixed_events=fixed_events,
        preferences=preferences,
        constraints=[],
        avoid_items=[],
        unresolved_items=[],
        source_fragments=[],
    )


def _place(identity, *, ownership: str) -> TripCompilerPlace:
    if not identity.provider_place_id or identity.latitude is None or identity.longitude is None:
        raise DraftIntentProjectionError(
            "draft_intent_place_identity_incomplete",
            "已确认地点缺少服务商位置数据，请重新确认。",
        )
    return TripCompilerPlace(
        stable_id=identity.stable_id,
        name=identity.canonical_name or identity.original_name,
        ownership=ownership,  # type: ignore[arg-type]
        confidence=1.0,
        source_fragment_ids=identity.source_fragment_ids,
    )


def _fixed_event_day(fixed_day: int | None, start_at, trip_start_date) -> int | None:
    if fixed_day is not None:
        return fixed_day
    if start_at is not None and trip_start_date is not None:
        return (start_at.date() - trip_start_date).days + 1
    return None
