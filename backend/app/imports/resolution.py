from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.imports.domain import (
    IMPORT_RESOLVER_VERSION,
    ExtractedMentionRecord,
    ResolutionDataState,
    ResolvedPlaceCandidateRecord,
    generate_resolution_candidate_id,
    normalize_mention_text,
    resolution_candidate_digest,
)
from app.schemas import POIType
from app.services.itinerary_completion_recommendation import CITY_CANDIDATES, CandidateSpec, normalize_city_name


class PlaceMentionResolver(Protocol):
    def resolve(self, *, mention: ExtractedMentionRecord, trip_context: dict) -> list[ResolvedPlaceCandidateRecord]:
        ...


@dataclass(frozen=True, slots=True)
class ScoredLocalCandidate:
    city: str
    candidate: CandidateSpec
    score: int


class DeterministicPlaceMentionResolver:
    def __init__(self, *, max_candidates: int = 5) -> None:
        self.max_candidates = max_candidates

    def resolve(self, *, mention: ExtractedMentionRecord, trip_context: dict) -> list[ResolvedPlaceCandidateRecord]:
        trip_city = normalize_city_name(str(trip_context.get("city") or "")) or None
        city_hint = normalize_city_name(mention.city_hint)
        search_cities = [city_hint or trip_city] if (city_hint or trip_city) else sorted(CITY_CANDIDATES)
        scored: list[ScoredLocalCandidate] = []
        for city in search_cities:
            if not city:
                continue
            for candidate in CITY_CANDIDATES.get(city, []):
                score = score_candidate(mention.raw_text, candidate)
                if score >= 35:
                    scored.append(ScoredLocalCandidate(city=city, candidate=candidate, score=score))

        scored.sort(key=lambda item: (-item.score, item.city, item.candidate.name))
        unique: dict[tuple[str, str], ScoredLocalCandidate] = {}
        for item in scored:
            unique.setdefault((item.city, item.candidate.name), item)
        top = list(unique.values())[: self.max_candidates]
        if not top:
            return [
                build_resolution_record(
                    mention=mention,
                    provider="local_candidate_catalog",
                    provider_place_id=None,
                    canonical_name=mention.normalized_text or mention.raw_text,
                    city=city_hint or trip_city,
                    candidate=None,
                    confidence=0.0,
                    state=ResolutionDataState.MISSING.value,
                    reason_codes=["no_candidate"],
                )
            ]

        ambiguous = len(top) > 1 and top[0].score - top[1].score < 8
        records: list[ResolvedPlaceCandidateRecord] = []
        for item in top:
            state = ResolutionDataState.RESOLVED.value
            reasons = ["local_catalog_match"]
            if ambiguous:
                state = ResolutionDataState.AMBIGUOUS.value
                reasons.append("ambiguous_same_name_or_branch")
            if trip_city and item.city != trip_city:
                state = ResolutionDataState.CROSS_CITY.value
                reasons.append("cross_city")
            if item.candidate.latitude is None or item.candidate.longitude is None:
                state = ResolutionDataState.PARTIAL.value
                reasons.append("missing_coordinates")
            records.append(
                build_resolution_record(
                    mention=mention,
                    provider="local_candidate_catalog",
                    provider_place_id=f"local:{item.city}:{normalize_mention_text(item.candidate.name)}",
                    canonical_name=item.candidate.name,
                    city=item.city,
                    candidate=item.candidate,
                    confidence=min(0.99, item.score / 100),
                    state=state,
                    reason_codes=reasons,
                )
            )
        return records


def score_candidate(name: str, candidate: CandidateSpec) -> int:
    target = normalize_mention_text(name)
    candidate_name = normalize_mention_text(candidate.name)
    if target == candidate_name:
        return 100
    if target and target in candidate_name:
        return 86
    if candidate_name and candidate_name in target:
        return 82
    shared = len(set(target) & set(candidate_name))
    return min(70, shared * 12 - abs(len(target) - len(candidate_name)) * 2)


def build_resolution_record(
    *,
    mention: ExtractedMentionRecord,
    provider: str,
    provider_place_id: str | None,
    canonical_name: str,
    city: str | None,
    candidate: CandidateSpec | None,
    confidence: float,
    state: str,
    reason_codes: list[str],
) -> ResolvedPlaceCandidateRecord:
    latitude = candidate.latitude if candidate else None
    longitude = candidate.longitude if candidate else None
    category = candidate.type.value if candidate and isinstance(candidate.type, POIType) else (str(candidate.type) if candidate else None)
    return ResolvedPlaceCandidateRecord(
        id=generate_resolution_candidate_id(),
        mention_id=mention.id,
        provider=provider,
        provider_place_id=provider_place_id,
        canonical_name=canonical_name,
        address_summary=city,
        administrative_area=city,
        city_code=city,
        latitude=latitude,
        longitude=longitude,
        category=category,
        confidence=confidence,
        resolution_reason_codes=reason_codes,
        data_state=state,
        candidate_digest=resolution_candidate_digest(
            provider=provider,
            provider_place_id=provider_place_id,
            canonical_name=canonical_name,
            latitude=latitude,
            longitude=longitude,
        ),
        created_at="",
    )
