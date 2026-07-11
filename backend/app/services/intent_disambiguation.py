from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.schemas.intent import (
    IntentDisambiguationSummary,
    ParsedTripIntentResponse,
    PlaceDisambiguationResolution,
)
from app.services.amap_client import GeocodingError, search_place_candidates
from app.services.itinerary_completion_recommendation import (
    CITY_CANDIDATES,
    normalize_city_name,
)
from app.services.llm_intent_parser import IntentParsingError, select_place_candidate_with_llm
from app.services.nl_parser import extract_city, normalize_parsed_trip_intent


CandidateProvider = Callable[[str, str, int], list[dict]]
CandidateSelector = Callable[[str | None, str | None, str, str, list[dict]], str | None]


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: dict
    score: int
    selection_source: str = "deterministic_candidate_rank"


def disambiguate_trip_intent(
    parsed_intent: ParsedTripIntentResponse,
    *,
    raw_text: str | None = None,
    city_hint: str | None = None,
    candidate_provider: CandidateProvider | None = None,
    llm_selector: CandidateSelector | None = None,
) -> ParsedTripIntentResponse:
    """
    Resolve parser strings against real place-search candidates when available.

    This stays above the deterministic scheduler:
    - Amap provides bounded real-world candidates.
    - Optional LLM disambiguation can only choose from those candidates.
    - If integrations are unavailable, the original parsed intent is preserved.
    """
    text_city = extract_city(raw_text, split_text_lines(raw_text)) if raw_text else None
    city = parsed_intent.city or text_city or city_hint
    summary = IntentDisambiguationSummary(
        city_hint=city_hint,
        resolved_city=city,
        city_source=(
            "parser"
            if parsed_intent.city
            else ("text_disambiguation" if text_city else ("hint" if city_hint else "missing"))
        ),
    )

    if not city:
        summary.warnings.append("No city available for real POI disambiguation.")
        return attach_disambiguation_summary(parsed_intent, summary)

    provider = candidate_provider or default_candidate_provider
    selector = llm_selector or default_llm_selector
    scenic_spots, scenic_resolutions = resolve_place_names(
        names=parsed_intent.scenic_spots,
        poi_type="scenic",
        city=city,
        raw_text=raw_text,
        candidate_provider=provider,
        llm_selector=selector,
    )
    restaurants, restaurant_resolutions = resolve_place_names(
        names=parsed_intent.restaurants,
        poi_type="restaurant",
        city=city,
        raw_text=raw_text,
        candidate_provider=provider,
        llm_selector=selector,
    )
    fixed_events = []
    fixed_resolutions: list[PlaceDisambiguationResolution] = []
    for event in parsed_intent.fixed_events:
        event_type = "restaurant" if event.category == "restaurant" else "scenic"
        resolved_names, resolutions = resolve_place_names(
            names=[event.name],
            poi_type=event_type,
            city=city,
            raw_text=raw_text,
            candidate_provider=provider,
            llm_selector=selector,
        )
        fixed_events.append(event.model_copy(update={"name": resolved_names[0]}))
        fixed_resolutions.extend(resolutions)

    summary.place_resolutions = [
        *scenic_resolutions,
        *restaurant_resolutions,
        *fixed_resolutions,
    ]
    if not summary.place_resolutions:
        summary.warnings.append(
            "No stronger POI disambiguation was available; keeping parsed place names."
        )

    return normalize_parsed_trip_intent(
        parsed_intent.model_copy(
            update={
                "city": city,
                "scenic_spots": scenic_spots,
                "restaurants": restaurants,
                "fixed_events": fixed_events,
                "disambiguation_summary": summary,
            }
        )
    )


def resolve_place_names(
    *,
    names: list[str],
    poi_type: str,
    city: str,
    raw_text: str | None,
    candidate_provider: CandidateProvider,
    llm_selector: CandidateSelector,
) -> tuple[list[str], list[PlaceDisambiguationResolution]]:
    resolved_names: list[str] = []
    resolutions: list[PlaceDisambiguationResolution] = []

    for name in names:
        candidates = safe_search_candidates(
            candidate_provider=candidate_provider,
            keyword=name,
            city=city,
        )
        if not candidates:
            resolved_names.append(name)
            continue

        ranked = rank_candidates(name=name, poi_type=poi_type, candidates=candidates)
        selected = select_ranked_candidate(
            name=name,
            poi_type=poi_type,
            city=city,
            raw_text=raw_text,
            ranked=ranked,
            llm_selector=llm_selector,
        )
        if selected is None:
            resolved_names.append(name)
            continue

        resolved_name = str(selected.candidate.get("name") or name)
        resolved_names.append(resolved_name)
        if resolved_name != name or selected.score >= 80:
            resolutions.append(
                PlaceDisambiguationResolution(
                    input_name=name,
                    resolved_name=resolved_name,
                    poi_type=poi_type,
                    city=city,
                    confidence=score_to_confidence(selected.score),
                    source=resolution_source(selected),
                    reason=build_resolution_reason(name, selected),
                    candidate_names=[
                        str(candidate.candidate.get("name") or "")
                        for candidate in ranked[:5]
                        if candidate.candidate.get("name")
                    ],
                )
            )

    return unique_preserve_order(resolved_names), resolutions


def safe_search_candidates(
    *,
    candidate_provider: CandidateProvider,
    keyword: str,
    city: str,
) -> list[dict]:
    try:
        return candidate_provider(keyword, city, 8)
    except GeocodingError:
        return []


def default_candidate_provider(keyword: str, city: str, offset: int) -> list[dict]:
    try:
        amap_candidates = search_place_candidates(keyword=keyword, city=city, offset=offset)
    except GeocodingError:
        amap_candidates = []
    if amap_candidates:
        return [with_candidate_source(candidate, "amap_place_search") for candidate in amap_candidates]
    return local_candidate_catalog_search(keyword=keyword, city=city, offset=offset)


def default_llm_selector(
    raw_text: str | None,
    city: str | None,
    poi_name: str,
    poi_type: str,
    candidates: list[dict],
) -> str | None:
    try:
        return select_place_candidate_with_llm(
            raw_text=raw_text,
            city=city,
            poi_name=poi_name,
            poi_type=poi_type,
            candidates=candidates,
        )
    except IntentParsingError:
        return None


def rank_candidates(
    *,
    name: str,
    poi_type: str,
    candidates: list[dict],
) -> list[RankedCandidate]:
    return sorted(
        [
            RankedCandidate(
                candidate=candidate,
                score=score_candidate(name=name, poi_type=poi_type, candidate=candidate),
                selection_source=str(
                    candidate.get("_candidate_source")
                    or "deterministic_candidate_rank"
                ),
            )
            for candidate in candidates
        ],
        key=lambda ranked: ranked.score,
        reverse=True,
    )


def select_ranked_candidate(
    *,
    name: str,
    poi_type: str,
    city: str,
    raw_text: str | None,
    ranked: list[RankedCandidate],
    llm_selector: CandidateSelector,
) -> RankedCandidate | None:
    if not ranked:
        return None

    top = ranked[0]
    runner_up_score = ranked[1].score if len(ranked) > 1 else 0
    if top.score >= 80 and top.score - runner_up_score >= 8:
        return top
    if top.score >= 92:
        return top

    selected_name = llm_selector(
        raw_text,
        city,
        name,
        poi_type,
        [candidate.candidate for candidate in ranked[:6]],
    )
    if not selected_name:
        return top if top.score >= 75 else None

    for candidate in ranked:
        if candidate.candidate.get("name") == selected_name:
            return RankedCandidate(
                candidate=candidate.candidate,
                score=min(candidate.score, 79),
                selection_source="llm_candidate_choice",
            )
    return top if top.score >= 75 else None


def score_candidate(*, name: str, poi_type: str, candidate: dict) -> int:
    target = normalize_name(name)
    candidate_name = normalize_name(str(candidate.get("name") or ""))
    candidate_type = str(candidate.get("type") or "")
    score = 0
    if candidate_name == target:
        score += 90
    elif target and target in candidate_name:
        score += 72
    elif candidate_name and candidate_name in target:
        score += 66
    else:
        shared_chars = len(set(target) & set(candidate_name))
        score += min(shared_chars * 6, 42)

    if poi_type == "restaurant" and looks_like_restaurant_type(candidate_type):
        score += 18
    if poi_type == "scenic" and looks_like_scenic_type(candidate_type):
        score += 14
    if candidate.get("business_area"):
        score += 2
    return min(score, 100)


def normalize_name(value: str) -> str:
    return (
        value.casefold()
        .replace("（", "(")
        .replace("）", ")")
        .replace("·", "")
        .replace(" ", "")
        .strip()
    )


def looks_like_restaurant_type(value: str) -> bool:
    return any(keyword in value for keyword in ("餐饮", "中餐", "小吃", "咖啡", "甜品", "快餐"))


def looks_like_scenic_type(value: str) -> bool:
    return any(keyword in value for keyword in ("风景名胜", "科教文化", "购物", "商务住宅", "公共设施"))


def score_to_confidence(score: int) -> str:
    if score >= 90:
        return "high"
    if score >= 75:
        return "medium"
    return "low"


def build_resolution_reason(name: str, selected: RankedCandidate) -> str:
    candidate_name = str(selected.candidate.get("name") or name)
    candidate_type = selected.candidate.get("type")
    address = selected.candidate.get("address")
    source_label = selected.selection_source.replace("_", " ")
    parts = [f"Resolved '{name}' to '{candidate_name}' from {source_label}."]
    if candidate_type:
        parts.append(f"Type: {candidate_type}.")
    if address:
        parts.append(f"Address: {address}.")
    return " ".join(parts)


def resolution_source(selected: RankedCandidate) -> str:
    if selected.selection_source in {"amap_place_search", "local_candidate_catalog"}:
        return selected.selection_source
    if selected.selection_source == "llm_candidate_choice":
        return "llm_candidate_choice"
    return "deterministic_candidate_rank"


def local_candidate_catalog_search(keyword: str, city: str, offset: int) -> list[dict]:
    normalized_city = normalize_city_name(city)
    candidate_pool = CITY_CANDIDATES.get(normalized_city or "", [])
    ranked = sorted(
        [
            (
                local_catalog_match_score(keyword, candidate.name, candidate.themes),
                candidate,
            )
            for candidate in candidate_pool
        ],
        key=lambda item: item[0],
        reverse=True,
    )
    return [
        {
            "name": candidate.name,
            "address": "local candidate catalog",
            "type": local_catalog_type(candidate.type.value),
            "business_area": ",".join(candidate.areas),
            "_candidate_source": "local_candidate_catalog",
        }
        for score, candidate in ranked[:offset]
        if score > 0
    ]


def local_catalog_match_score(keyword: str, candidate_name: str, themes: tuple[str, ...]) -> int:
    normalized_keyword = normalize_name(keyword)
    normalized_candidate = normalize_name(candidate_name)
    if normalized_keyword == normalized_candidate:
        return 100
    if normalized_keyword and normalized_keyword in normalized_candidate:
        return 86
    if normalized_candidate and normalized_candidate in normalized_keyword:
        return 78
    theme_score = max(
        (theme_keyword_score(normalized_keyword, theme) for theme in themes),
        default=0,
    )
    shared_chars = len(set(normalized_keyword) & set(normalized_candidate))
    return max(theme_score, min(shared_chars * 8, 56))


def theme_keyword_score(keyword: str, theme: str) -> int:
    theme_keywords = {
        "museum": ("博物馆", "展览", "自然", "museum"),
        "old_street": ("老街", "街区", "citywalk", "慢慢逛", "路"),
        "waterfront": ("夜景", "江景", "滨江", "外滩"),
        "street_food": ("小吃", "美食", "夜市", "吃"),
        "design": ("设计", "公馆", "新天地", "田子坊"),
        "garden": ("园林", "公园", "寺", "庙"),
        "night": ("夜景", "夜市", "晚上"),
    }
    return 62 if any(token in keyword for token in theme_keywords.get(theme, ())) else 0


def local_catalog_type(poi_type: str) -> str:
    if poi_type == "restaurant":
        return "餐饮服务;本地候选库"
    return "风景名胜;本地候选库"


def with_candidate_source(candidate: dict, source: str) -> dict:
    return {**candidate, "_candidate_source": source}


def split_text_lines(text: str | None) -> list[str]:
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def attach_disambiguation_summary(
    parsed_intent: ParsedTripIntentResponse,
    summary: IntentDisambiguationSummary,
) -> ParsedTripIntentResponse:
    return parsed_intent.model_copy(update={"disambiguation_summary": summary})


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique
