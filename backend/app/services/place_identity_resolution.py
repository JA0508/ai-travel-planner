from __future__ import annotations

import re
from typing import Iterable

from app.services.poi_discovery_provider import (
    PoiDiscoveryCandidate,
    PoiDiscoveryProvider,
    PoiDiscoveryUnavailable,
    default_poi_discovery_provider,
)
from app.services.trip_compiler import compile_travel_intent
from app.trips.intent_contracts import PlaceIdentity, PlaceResolutionOption


class PlaceIdentityResolutionError(ValueError):
    """A typed failure that leaves the Draft Intent revision unchanged."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def discover_place_identities(
    *,
    direct_user_text: str,
    city: str | None,
    provider: PoiDiscoveryProvider | None = None,
) -> list[PlaceIdentity]:
    """Return bounded, provider-sourced confirmation choices for direct place text.

    Discovery never promotes a candidate to canonical identity by itself.  A user
    selection is required and is recorded by a new immutable Draft Intent revision.
    """

    compiled = compile_travel_intent(direct_user_text).intent
    active_provider = provider or default_poi_discovery_provider()
    identities: list[PlaceIdentity] = []
    for place in compiled.must_visit_places:
        if _is_destination_phrase(place.name, city or compiled.destination):
            continue
        identities.append(
            _identity_from_discovery(
                stable_id=place.stable_id,
                original_name=place.name,
                ownership="must",
                source_fragment_ids=place.source_fragment_ids,
                city=city or compiled.destination,
                provider=active_provider,
            )
        )
    for place in compiled.optional_places:
        if _is_destination_phrase(place.name, city or compiled.destination):
            continue
        identities.append(
            _identity_from_discovery(
                stable_id=place.stable_id,
                original_name=place.name,
                ownership="optional",
                source_fragment_ids=place.source_fragment_ids,
                city=city or compiled.destination,
                provider=active_provider,
            )
        )
    for event in compiled.fixed_events:
        # A title without a location is still a fixed event, but must not be
        # fabricated into a canonical POI. The scheduler retains its time window.
        if not event.name.strip():
            continue
        identities.append(
            _identity_from_discovery(
                stable_id=event.stable_id,
                original_name=event.name,
                ownership="fixed",
                fixed_event_id=event.stable_id,
                source_fragment_ids=event.source_fragment_ids,
                city=city or compiled.destination,
                provider=active_provider,
            )
        )
    return _deduplicate_identities(identities)


def discover_fixed_event_identity(
    *,
    event_id: str,
    location_text: str,
    city: str | None,
    source_fragment_ids: list[str],
    provider: PoiDiscoveryProvider | None = None,
) -> PlaceIdentity:
    """Re-discover one edited fixed event without changing its immutable lineage."""

    active_provider = provider or default_poi_discovery_provider()
    return _identity_from_discovery(
        stable_id=event_id,
        original_name=location_text,
        ownership="fixed",
        fixed_event_id=event_id,
        source_fragment_ids=source_fragment_ids,
        city=city,
        provider=active_provider,
    )


def confirm_place_identity(
    *,
    identity: PlaceIdentity,
    provider_place_id: str,
    provider: PoiDiscoveryProvider | None = None,
) -> PlaceIdentity:
    """Re-read the chosen provider candidate; never trust client-side geometry."""

    if not provider_place_id.strip():
        raise PlaceIdentityResolutionError("place_identity_selection_required")
    active_provider = provider or default_poi_discovery_provider()
    try:
        candidates = active_provider.search_text(
            keyword=identity.original_name,
            city=identity.city or "",
            offset=20,
        )
    except PoiDiscoveryUnavailable as exc:
        raise PlaceIdentityResolutionError("place_identity_provider_unavailable") from exc
    selected = next(
        (candidate for candidate in candidates if candidate.provider_place_id == provider_place_id),
        None,
    )
    if selected is None:
        raise PlaceIdentityResolutionError("place_identity_selection_not_found")
    if selected.latitude is None or selected.longitude is None or not selected.name:
        raise PlaceIdentityResolutionError("place_identity_selection_incomplete")
    return identity.model_copy(
        update={
            "canonical_name": selected.name,
            "city": identity.city,
            "resolution_status": "verified",
            "provider": "amap",
            "provider_place_id": selected.provider_place_id,
            "latitude": selected.latitude,
            "longitude": selected.longitude,
            "category": selected.type,
            "confirmation_options": [],
            "resolution_confidence": 1.0,
        },
        deep=True,
    )


def _identity_from_discovery(
    *,
    stable_id: str,
    original_name: str,
    ownership: str,
    source_fragment_ids: list[str],
    city: str | None,
    provider: PoiDiscoveryProvider,
    fixed_event_id: str | None = None,
) -> PlaceIdentity:
    options = _search_options(provider=provider, keyword=original_name, city=city or "")
    return PlaceIdentity(
        stable_id=stable_id,
        original_name=original_name,
        city=city,
        ownership=ownership,  # type: ignore[arg-type]
        fixed_event_id=fixed_event_id,
        resolution_status="ambiguous" if options else "unresolved",
        source_fragment_ids=source_fragment_ids,
        confirmation_options=options,
        resolution_confidence=None,
    )


def _search_options(*, provider: PoiDiscoveryProvider, keyword: str, city: str) -> list[PlaceResolutionOption]:
    try:
        candidates = provider.search_text(keyword=keyword, city=city, offset=4)
    except PoiDiscoveryUnavailable:
        return []
    return [option for candidate in candidates if (option := _option_from_candidate(candidate)) is not None][:4]


def _option_from_candidate(candidate: PoiDiscoveryCandidate) -> PlaceResolutionOption | None:
    if not candidate.provider_place_id or not candidate.name:
        return None
    return PlaceResolutionOption(
        provider_place_id=candidate.provider_place_id,
        canonical_name=candidate.name,
        address_summary=candidate.address,
        category=candidate.type,
        city=candidate.business_area,
    )


def _deduplicate_identities(items: Iterable[PlaceIdentity]) -> list[PlaceIdentity]:
    seen: set[tuple[str, str]] = set()
    result: list[PlaceIdentity] = []
    for item in items:
        key = (item.ownership, _normalise_name(item.original_name))
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _normalise_name(value: str) -> str:
    return re.sub(r"[\s\W_]", "", value, flags=re.UNICODE).casefold()


def _is_destination_phrase(value: str, city: str | None) -> bool:
    """Keep a parser's "go to X for N days" span out of POI confirmation."""

    if not city:
        return False
    compact = re.sub(r"\s+", "", value)
    escaped_city = re.escape(city.strip())
    return bool(re.fullmatch(rf"(?:去)?{escaped_city}(?:玩|游|旅行|待|住).{{0,12}}", compact))
