from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable

from app.schemas import NormalizedPOI, POIType, POIVisitStyle
from app.schemas.preference_policy import PlannerPreferencePolicy
from app.services.mock_normalizer import infer_poi_profile


LOW_WALKING_KEYWORDS = {"少走路", "不想走太多", "轻松一点", "轻松", "walk less"}
DINING_PRIORITY_KEYWORDS = {"本地美食", "美食优先", "吃为主", "当地美食", "food-first"}
SCENIC_PRIORITY_KEYWORDS = {"景点优先", "多看景点", "打卡景点", "scenic-first"}
RELAXED_PACE_KEYWORDS = {"轻松", "休闲", "慢一点", "慢慢玩", "别太赶", "别太紧", "relaxed"}
PACKED_PACE_KEYWORDS = {"特种兵", "高强度", "尽量排满", "多逛", "多玩", "packed", "full-on"}

STYLE_BUCKET_MUSEUM = "museum"
STYLE_BUCKET_OLD_STREET = "old_street"
STYLE_BUCKET_LANDMARK = "landmark"
STYLE_BUCKET_FOOD_STOP = "food_stop"
STYLE_BUCKET_NIGHT_VIEW = "night_view"
STYLE_BUCKET_ORDER = (
    STYLE_BUCKET_MUSEUM,
    STYLE_BUCKET_OLD_STREET,
    STYLE_BUCKET_LANDMARK,
    STYLE_BUCKET_FOOD_STOP,
    STYLE_BUCKET_NIGHT_VIEW,
)
STYLE_PREFERENCE_SOURCES = {"explicit", "inferred"}
STYLE_PREFERENCE_EVIDENCE = {"request_wording", "parser_explicit", "parser_inferred", "poi_mix"}

MUSEUM_STYLE_KEYWORDS = {"博物馆", "museum", "展览", "美术馆", "gallery"}
OLD_STREET_STYLE_KEYWORDS = {"老街", "古镇", "citywalk", "city walk", "漫步", "闲逛", "逛逛", "街区", "弄堂"}
LANDMARK_STYLE_KEYWORDS = {"地标", "打卡", "经典景点", "landmark"}
FOOD_STOP_STYLE_KEYWORDS = {"咖啡", "cafe", "coffee", "甜品", "下午茶", "小吃", "美食", "探店", "吃吃喝喝", "food stop", "food-stop"}
NIGHT_VIEW_STYLE_KEYWORDS = {"夜景", "夜游", "江景", "滨江", "河边", "riverside", "night view", "night-view", "晚上散步", "晚间散步", "evening stroll"}


@dataclass(frozen=True, slots=True)
class StylePreferenceSignal:
    explicit: frozenset[str] = frozenset()
    inferred: frozenset[str] = frozenset()

    def __bool__(self) -> bool:
        return bool(self.explicit or self.inferred)

    def combined(self) -> set[str]:
        return set(self.explicit | self.inferred)

    def source_for(self, style_bucket: str) -> str | None:
        if style_bucket in self.explicit:
            return "explicit"
        if style_bucket in self.inferred:
            return "inferred"
        return None


@dataclass(frozen=True, slots=True)
class StylePreferenceAttribution:
    signal: StylePreferenceSignal
    evidence: dict[str, str]


@dataclass(frozen=True, slots=True)
class StylePreferenceAttributionSummary:
    total_styles: int
    explicit_count: int
    inferred_count: int
    evidence_counts: dict[str, int]
    styles_by_source: dict[str, tuple[str, ...]]
    styles_by_evidence: dict[str, tuple[str, ...]]


def ordered_style_preferences(values: Iterable[str]) -> list[str]:
    value_set = set(values)
    return [style_bucket for style_bucket in STYLE_BUCKET_ORDER if style_bucket in value_set]


def style_preference_sources_from_signal(signal: StylePreferenceSignal) -> dict[str, str]:
    sources: dict[str, str] = {}
    for style_bucket in STYLE_BUCKET_ORDER:
        source = signal.source_for(style_bucket)
        if source is not None:
            sources[style_bucket] = source
    return sources


def summarize_style_preference_attribution(
    attribution: StylePreferenceAttribution,
) -> StylePreferenceAttributionSummary:
    styles_by_source: dict[str, list[str]] = {
        "explicit": [],
        "inferred": [],
    }
    styles_by_evidence: dict[str, list[str]] = {
        "request_wording": [],
        "parser_explicit": [],
        "parser_inferred": [],
        "poi_mix": [],
    }
    evidence_counts = {
        "request_wording": 0,
        "parser_explicit": 0,
        "parser_inferred": 0,
        "poi_mix": 0,
    }

    for style_bucket in STYLE_BUCKET_ORDER:
        source = attribution.signal.source_for(style_bucket)
        if source is not None:
            styles_by_source[source].append(style_bucket)

        evidence = attribution.evidence.get(style_bucket)
        if evidence in styles_by_evidence:
            styles_by_evidence[evidence].append(style_bucket)
            evidence_counts[evidence] += 1

    explicit_styles = tuple(styles_by_source["explicit"])
    inferred_styles = tuple(styles_by_source["inferred"])
    return StylePreferenceAttributionSummary(
        total_styles=len(explicit_styles) + len(inferred_styles),
        explicit_count=len(explicit_styles),
        inferred_count=len(inferred_styles),
        evidence_counts=evidence_counts,
        styles_by_source={
            "explicit": explicit_styles,
            "inferred": inferred_styles,
        },
        styles_by_evidence={
            evidence: tuple(style_buckets)
            for evidence, style_buckets in styles_by_evidence.items()
        },
    )


def build_style_preference_debug_snapshot(
    attribution: StylePreferenceAttribution,
) -> tuple[str, ...]:
    snapshot: list[str] = []
    for style_bucket in STYLE_BUCKET_ORDER:
        source = attribution.signal.source_for(style_bucket)
        if source is None:
            continue
        evidence = attribution.evidence.get(style_bucket, "unknown")
        snapshot.append(f"{style_bucket}|{source}|{evidence}")
    return tuple(snapshot)


def build_style_preference_signal_from_sources(
    style_preference_sources: dict[str, str] | None,
) -> StylePreferenceSignal:
    if not style_preference_sources:
        return StylePreferenceSignal()

    explicit_styles = {
        style_bucket
        for style_bucket, source in style_preference_sources.items()
        if source == "explicit"
    }
    inferred_styles = {
        style_bucket
        for style_bucket, source in style_preference_sources.items()
        if source == "inferred"
    } - explicit_styles
    return StylePreferenceSignal(
        explicit=frozenset(explicit_styles),
        inferred=frozenset(inferred_styles),
    )


def normalize_style_preference_sources(
    values: dict[str, str] | None,
) -> dict[str, str]:
    if not values:
        return {}
    return {
        style_bucket: source
        for style_bucket in STYLE_BUCKET_ORDER
        if (source := values.get(style_bucket)) in STYLE_PREFERENCE_SOURCES
    }


def build_preference_policy(preferences: list[str]) -> PlannerPreferencePolicy:
    normalized = {preference.strip().casefold() for preference in preferences if preference.strip()}

    return PlannerPreferencePolicy(
        walking_tolerance="low" if contains_any(normalized, LOW_WALKING_KEYWORDS) else "normal",
        dining_priority="high" if contains_any(normalized, DINING_PRIORITY_KEYWORDS) else "normal",
        scenic_priority="high" if contains_any(normalized, SCENIC_PRIORITY_KEYWORDS) else "normal",
        pace=resolve_pace(normalized),
    )


def contains_any(values: set[str], keywords: set[str]) -> bool:
    lowered_keywords = {keyword.casefold() for keyword in keywords}
    return any(value in lowered_keywords for value in values)


def resolve_pace(values: set[str]) -> str:
    if contains_any(values, PACKED_PACE_KEYWORDS):
        return "packed"
    if contains_any(values, RELAXED_PACE_KEYWORDS):
        return "relaxed"
    return "balanced"


def infer_request_style_preferences(
    preferences: list[str],
    scenic_spots: Iterable[NormalizedPOI] = (),
    restaurants: Iterable[NormalizedPOI] = (),
) -> set[str]:
    return build_style_preference_signal(
        preferences=preferences,
        scenic_spots=scenic_spots,
        restaurants=restaurants,
    ).combined()


def build_style_preference_signal(
    *,
    preferences: list[str],
    scenic_spots: Iterable[NormalizedPOI] = (),
    restaurants: Iterable[NormalizedPOI] = (),
    parsed_style_preferences: Iterable[str] | None = None,
    parsed_style_preference_sources: dict[str, str] | None = None,
) -> StylePreferenceSignal:
    return build_style_preference_attribution(
        preferences=preferences,
        scenic_spots=scenic_spots,
        restaurants=restaurants,
        parsed_style_preferences=parsed_style_preferences,
        parsed_style_preference_sources=parsed_style_preference_sources,
    ).signal


def build_style_preference_attribution(
    *,
    preferences: list[str],
    scenic_spots: Iterable[NormalizedPOI] = (),
    restaurants: Iterable[NormalizedPOI] = (),
    parsed_style_preferences: Iterable[str] | None = None,
    parsed_style_preference_sources: dict[str, str] | None = None,
) -> StylePreferenceAttribution:
    explicit_styles = infer_explicit_style_preferences(preferences)
    return merge_style_preference_attribution(
        explicit_styles=explicit_styles,
        default_inferred_styles=infer_poi_mix_style_preferences(
            scenic_spots=scenic_spots,
            restaurants=restaurants,
        ),
        parsed_style_preferences=parsed_style_preferences,
        parsed_style_preference_sources=parsed_style_preference_sources,
    )


def infer_request_style_preferences_from_names(
    preferences: list[str],
    scenic_spot_names: Iterable[str] = (),
    restaurant_names: Iterable[str] = (),
) -> set[str]:
    return build_style_preference_signal_from_names(
        preferences=preferences,
        scenic_spot_names=scenic_spot_names,
        restaurant_names=restaurant_names,
    ).combined()


def build_style_preference_signal_from_names(
    *,
    preferences: list[str],
    scenic_spot_names: Iterable[str] = (),
    restaurant_names: Iterable[str] = (),
    parsed_style_preferences: Iterable[str] | None = None,
    parsed_style_preference_sources: dict[str, str] | None = None,
) -> StylePreferenceSignal:
    return build_style_preference_attribution_from_names(
        preferences=preferences,
        scenic_spot_names=scenic_spot_names,
        restaurant_names=restaurant_names,
        parsed_style_preferences=parsed_style_preferences,
        parsed_style_preference_sources=parsed_style_preference_sources,
    ).signal


def build_style_preference_attribution_from_names(
    *,
    preferences: list[str],
    scenic_spot_names: Iterable[str] = (),
    restaurant_names: Iterable[str] = (),
    parsed_style_preferences: Iterable[str] | None = None,
    parsed_style_preference_sources: dict[str, str] | None = None,
) -> StylePreferenceAttribution:
    explicit_styles = infer_explicit_style_preferences(preferences)
    return merge_style_preference_attribution(
        explicit_styles=explicit_styles,
        default_inferred_styles=infer_name_mix_style_preferences(
            scenic_spot_names=scenic_spot_names,
            restaurant_names=restaurant_names,
        ),
        parsed_style_preferences=parsed_style_preferences,
        parsed_style_preference_sources=parsed_style_preference_sources,
    )


def merge_style_preference_attribution(
    *,
    explicit_styles: set[str],
    default_inferred_styles: set[str],
    parsed_style_preferences: Iterable[str] | None = None,
    parsed_style_preference_sources: dict[str, str] | None = None,
) -> StylePreferenceAttribution:
    explicit = set(explicit_styles)
    evidence = {style_bucket: "request_wording" for style_bucket in explicit}
    normalized_sources = normalize_style_preference_sources(parsed_style_preference_sources)

    if normalized_sources:
        parsed_signal = build_style_preference_signal_from_sources(normalized_sources)
        for style_bucket in parsed_signal.explicit:
            if style_bucket not in explicit:
                explicit.add(style_bucket)
                evidence[style_bucket] = "parser_explicit"

        parsed_styles = set(parsed_style_preferences or ())
        inferred = set(parsed_signal.inferred)
        if parsed_styles:
            inferred |= parsed_styles - explicit
        for style_bucket in inferred:
            evidence.setdefault(style_bucket, "parser_inferred")
    elif parsed_style_preferences is not None:
        inferred = set(parsed_style_preferences) - explicit
        for style_bucket in inferred:
            evidence.setdefault(style_bucket, "parser_inferred")
    else:
        inferred = set(default_inferred_styles) - explicit

    inferred -= explicit
    for style_bucket in inferred:
        evidence.setdefault(style_bucket, "poi_mix")

    return StylePreferenceAttribution(
        signal=StylePreferenceSignal(
            explicit=frozenset(explicit),
            inferred=frozenset(inferred),
        ),
        evidence={
            style_bucket: evidence_source
            for style_bucket, evidence_source in evidence.items()
            if evidence_source in STYLE_PREFERENCE_EVIDENCE
        },
    )


def infer_explicit_style_preferences(preferences: list[str]) -> set[str]:
    normalized = [preference.strip().casefold() for preference in preferences if preference.strip()]
    if not normalized:
        return set()

    styles: set[str] = set()
    if any(matches_style_keyword(value, MUSEUM_STYLE_KEYWORDS) for value in normalized):
        styles.add(STYLE_BUCKET_MUSEUM)
    if any(matches_style_keyword(value, OLD_STREET_STYLE_KEYWORDS) for value in normalized):
        styles.add(STYLE_BUCKET_OLD_STREET)
    if any(matches_style_keyword(value, LANDMARK_STYLE_KEYWORDS) for value in normalized):
        styles.add(STYLE_BUCKET_LANDMARK)
    if any(matches_style_keyword(value, FOOD_STOP_STYLE_KEYWORDS) for value in normalized):
        styles.add(STYLE_BUCKET_FOOD_STOP)
    if any(matches_style_keyword(value, NIGHT_VIEW_STYLE_KEYWORDS) for value in normalized):
        styles.add(STYLE_BUCKET_NIGHT_VIEW)
    return styles


def infer_poi_mix_style_preferences(
    *,
    scenic_spots: Iterable[NormalizedPOI],
    restaurants: Iterable[NormalizedPOI],
) -> set[str]:
    style_counts: dict[str, int] = {}
    for poi in list(scenic_spots) + list(restaurants):
        style_bucket = style_bucket_for_poi(poi)
        if style_bucket is None:
            continue
        style_counts[style_bucket] = style_counts.get(style_bucket, 0) + 1

    if not style_counts:
        return set()

    max_count = max(style_counts.values())
    if max_count < 2:
        return set()

    return {
        style_bucket
        for style_bucket, count in style_counts.items()
        if count == max_count
    }


def infer_name_mix_style_preferences(
    *,
    scenic_spot_names: Iterable[str],
    restaurant_names: Iterable[str],
) -> set[str]:
    style_counts: dict[str, int] = {}
    for name in scenic_spot_names:
        style_bucket = style_bucket_for_name(name=name, poi_type=POIType.SCENIC)
        if style_bucket is None:
            continue
        style_counts[style_bucket] = style_counts.get(style_bucket, 0) + 1
    for name in restaurant_names:
        style_bucket = style_bucket_for_name(name=name, poi_type=POIType.RESTAURANT)
        if style_bucket is None:
            continue
        style_counts[style_bucket] = style_counts.get(style_bucket, 0) + 1

    if not style_counts:
        return set()

    max_count = max(style_counts.values())
    if max_count < 2:
        return set()

    return {
        style_bucket
        for style_bucket, count in style_counts.items()
        if count == max_count
    }


def matches_style_keyword(value: str, keywords: set[str]) -> bool:
    return any(keyword.casefold() in value for keyword in keywords)


def style_bucket_for_poi(poi: NormalizedPOI) -> str | None:
    visit_style = poi.profile.visit_style
    return style_bucket_for_visit_style(visit_style, poi.type)


def style_bucket_for_name(*, name: str, poi_type: POIType) -> str | None:
    visit_style = infer_poi_profile(name, poi_type).visit_style
    return style_bucket_for_visit_style(visit_style, poi_type)


def style_bucket_for_visit_style(
    visit_style: POIVisitStyle,
    poi_type: POIType,
) -> str | None:
    if visit_style == POIVisitStyle.MUSEUM:
        return STYLE_BUCKET_MUSEUM
    if visit_style in {POIVisitStyle.OLD_STREET, POIVisitStyle.LEISURE_DISTRICT}:
        return STYLE_BUCKET_OLD_STREET
    if visit_style in {POIVisitStyle.LANDMARK, POIVisitStyle.TEMPLE_PARK}:
        return STYLE_BUCKET_LANDMARK
    if visit_style in {POIVisitStyle.FOOD_STOP, POIVisitStyle.FOOD_DISTRICT} or poi_type == POIType.RESTAURANT:
        return STYLE_BUCKET_FOOD_STOP
    if visit_style == POIVisitStyle.NIGHT_VIEW:
        return STYLE_BUCKET_NIGHT_VIEW
    return None
