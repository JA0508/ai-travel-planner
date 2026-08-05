from __future__ import annotations

from app.schemas.trip_compiler import (
    TRIP_COMPILER_MAX_DAYS,
    TRIP_COMPILER_MIN_DAYS,
    TripCompilerPlace,
    TripCompilerPreference,
    TripCompilerFixedEvent,
    TravelIntent,
)
from app.schemas.itinerary import VerifiedPlaceRef
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
    fixed_events = []
    for item in formal.fixed_events:
        identity = _fixed_identity_for_event(
            formal.place_identities,
            item,
            fixed_event_count=len(formal.fixed_events),
        )
        if identity is None:
            raise DraftIntentProjectionError(
                "draft_intent_fixed_event_identity_unconfirmed",
                "请先确认每个固定安排的具体地点。",
            )
        fixed_events.append(
            TripCompilerFixedEvent(
                stable_id=item.event_id or identity.stable_id,
                # The reservation title is explanatory only. The actual planning
                # identity stays the confirmed provider place.
                name=identity.canonical_name or identity.original_name,
                day=_fixed_event_day(item.fixed_day, item.start_at, formal.date_policy.start_date if formal.date_policy else None),
                start_time=item.start_at.strftime("%H:%M") if item.start_at else item.fixed_time_start,
                end_time=item.end_at.strftime("%H:%M") if item.end_at else item.fixed_time_end,
                fixed_reason="你明确说明这是固定安排。",
                confidence=1.0,
                source_fragment_ids=identity.source_fragment_ids,
                verified_place=_verified_place(identity),
            )
        )
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
        verified_place=_verified_place(identity),
    )


def _verified_place(identity) -> VerifiedPlaceRef:
    if (
        identity.provider != "amap"
        or not identity.provider_place_id
        or identity.latitude is None
        or identity.longitude is None
    ):
        raise DraftIntentProjectionError(
            "draft_intent_place_identity_incomplete",
            "已确认地点缺少服务商位置数据，请重新确认。",
        )
    return VerifiedPlaceRef(
        stable_id=identity.stable_id,
        original_name=identity.original_name,
        canonical_name=identity.canonical_name or identity.original_name,
        provider=identity.provider,
        provider_place_id=identity.provider_place_id,
        latitude=identity.latitude,
        longitude=identity.longitude,
        category=identity.category,
        source_fragment_ids=identity.source_fragment_ids,
    )


def _fixed_identity_for_event(identities, event, *, fixed_event_count: int):
    """Link a fixed reservation to its existing Draft identity without lookup."""
    verified = [
        identity
        for identity in identities
        if identity.ownership == "fixed" and identity.resolution_status == "verified"
    ]
    for reference in (event.event_id, event.place_candidate_id):
        match = next((identity for identity in verified if identity.fixed_event_id == reference), None)
        if match is not None:
            return match
    # Historic Draft revisions may have given the formal fixed-event field a
    # compiler field id instead of the discovery identity id. A unique original
    # source label is a deterministic link to the identity already in this
    # immutable revision, never a fresh provider name search.
    by_source_name = [identity for identity in verified if identity.original_name == event.title]
    if len(by_source_name) == 1:
        return by_source_name[0]
    # Earlier Draft compiler revisions did not persist a relationship between
    # the formal fixed-event field id and its separately discovered place
    # identity. With exactly one of each, the immutable revision provides an
    # unambiguous deterministic relationship. This never searches by name.
    return verified[0] if fixed_event_count == 1 and len(verified) == 1 else None


def _fixed_event_day(fixed_day: int | None, start_at, trip_start_date) -> int | None:
    if fixed_day is not None:
        return fixed_day
    if start_at is not None and trip_start_date is not None:
        return (start_at.date() - trip_start_date).days + 1
    return None
