from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Iterable

from pydantic import ValidationError

from app.services.poi_discovery_provider import (
    PoiDiscoveryCandidate,
    PoiDiscoveryProvider,
    PoiDiscoveryUnavailable,
    default_poi_discovery_provider,
)
from app.services.nl_parser import parse_trip_text_fallback
from app.services.trip_compiler import compile_travel_intent
from app.trips.intent_contracts import PlaceIdentity, PlaceResolutionOption


class PlaceIdentityResolutionError(ValueError):
    """A typed failure that leaves the Draft Intent revision unchanged."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PlaceIdentitySuggestions:
    """Read-only provider candidates for an explicit user place search."""

    query: str
    options: list[PlaceResolutionOption]
    recommended_provider_place_id: str | None


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

    active_provider = provider or default_poi_discovery_provider()
    try:
        compiled = compile_travel_intent(direct_user_text).intent
    except ValidationError as exc:
        if not _is_legacy_place_limit_error(exc):
            raise
        return _discover_explicit_direct_places(
            direct_user_text=direct_user_text,
            city=city,
            provider=active_provider,
        )

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


def _discover_explicit_direct_places(
    *,
    direct_user_text: str,
    city: str | None,
    provider: PoiDiscoveryProvider,
) -> list[PlaceIdentity]:
    """Recover source-place confirmation without the legacy itinerary limit.

    The pre-plan workspace only needs provider choices for clearly named places.
    It must not make its availability depend on the legacy V1 itinerary contract,
    which has a separate eight-place scheduling limit and can over-extract prose
    from a user's requested output format.
    """

    discovery_city = city or parse_trip_text_fallback(direct_user_text).city
    identities = [
        _identity_from_discovery(
            stable_id=_direct_place_stable_id(name, index),
            original_name=name,
            ownership="must",
            source_fragment_ids=[_direct_place_source_id(name, index)],
            city=discovery_city,
            provider=provider,
        )
        for index, name in enumerate(_explicit_must_visit_names(direct_user_text))
    ]
    return _deduplicate_identities(identities)


def _is_legacy_place_limit_error(error: ValidationError) -> bool:
    return any(
        "at most eight user places" in str(item.get("msg", ""))
        for item in error.errors()
    )


def _explicit_must_visit_names(text: str) -> list[str]:
    """Extract only deliberate destination lists, never requested output fields."""

    names: list[str] = []
    for match in re.finditer(r"(?:已经\s*(?:确定\s*)?|确定\s*)?(?:想去|必去)([^。；;\n]+)", text):
        for item in re.split(r"[、，,]|(?:和|及|与)", match.group(1)):
            name = item.strip(" ：:，,。")
            if _is_explicit_place_name(name):
                names.append(name)
    return _unique_names(names)


def _is_explicit_place_name(value: str) -> bool:
    if not 2 <= len(value) <= 80:
        return False
    return not any(
        token in value
        for token in (
            "玩",
            "旅行",
            "旅游",
            "朋友",
            "原因",
            "停留",
            "交通",
            "每个地点",
            "输出",
        )
    )


def _unique_names(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for value in values:
        key = _normalise_name(value)
        if key and key not in seen:
            seen.add(key)
            names.append(value)
    return names


def _direct_place_stable_id(name: str, index: int) -> str:
    return f"direct_place_{sha256(f'{index}:{name}'.encode('utf-8')).hexdigest()[:16]}"


def _direct_place_source_id(name: str, index: int) -> str:
    return f"direct_source_{sha256(f'{index}:{name}'.encode('utf-8')).hexdigest()[:16]}"


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
    search_query: str | None = None,
    provider: PoiDiscoveryProvider | None = None,
) -> PlaceIdentity:
    """Re-read the chosen provider candidate; never trust client-side geometry."""

    if not provider_place_id.strip():
        raise PlaceIdentityResolutionError("place_identity_selection_required")
    active_provider = provider or default_poi_discovery_provider()
    keyword = _normalise_search_query(search_query) or identity.original_name
    try:
        candidates = active_provider.search_text(
            keyword=keyword,
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


def search_place_identity_suggestions(
    *,
    identity: PlaceIdentity,
    query: str | None = None,
    provider: PoiDiscoveryProvider | None = None,
) -> PlaceIdentitySuggestions:
    """Find ordered, provider-backed choices without modifying a Draft Intent."""

    active_provider = provider or default_poi_discovery_provider()
    keyword = _normalise_search_query(query) or identity.original_name
    options = _search_options(
        provider=active_provider,
        keyword=keyword,
        city=identity.city or "",
        original_name=identity.original_name,
        raise_when_unavailable=True,
    )
    return PlaceIdentitySuggestions(
        query=keyword,
        options=options,
        recommended_provider_place_id=options[0].provider_place_id if options else None,
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
    options = _search_options(
        provider=provider,
        keyword=original_name,
        city=city or "",
        original_name=original_name,
    )
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


def _search_options(
    *,
    provider: PoiDiscoveryProvider,
    keyword: str,
    city: str,
    original_name: str,
    raise_when_unavailable: bool = False,
) -> list[PlaceResolutionOption]:
    try:
        candidates = provider.search_text(keyword=keyword, city=city, offset=8)
    except PoiDiscoveryUnavailable as exc:
        if raise_when_unavailable:
            raise PlaceIdentityResolutionError("place_identity_provider_unavailable") from exc
        return []
    ranked = [
        (candidate, option)
        for candidate in candidates
        if (option := _option_from_candidate(candidate)) is not None
    ]
    ranked.sort(
        key=lambda item: _candidate_rank(
            candidate_name=item[0].name,
            query=keyword,
            original_name=original_name,
        ),
        reverse=True,
    )
    return [option for _, option in ranked[:4]]


def _normalise_search_query(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) > 160:
        raise PlaceIdentityResolutionError("place_identity_search_query_invalid")
    return normalized


def _candidate_rank(*, candidate_name: str | None, query: str, original_name: str) -> int:
    """Rank only by the user query and the original mention; provider order breaks ties."""

    name = _normalise_name(candidate_name or "")
    query_key = _normalise_name(query)
    original_key = _normalise_name(original_name)
    score = 0
    if query_key and name == query_key:
        score += 400
    elif query_key and query_key in name:
        score += 260
    elif query_key and name in query_key:
        score += 180
    if original_key and name == original_key:
        score += 220
    elif original_key and original_key in name:
        score += 120
    elif original_key and name in original_key:
        score += 80
    return score


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
