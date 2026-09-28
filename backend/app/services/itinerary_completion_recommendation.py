from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time
from functools import cmp_to_key
from math import atan2, cos, isfinite, radians, sin, sqrt

from app.schemas import (
    POIVisitStyle,
    CompletionCandidateTrace,
    CompletionDecisionEvidence,
    DayItinerary,
    DayTimeBlock,
    HotelStay,
    ItineraryCompletionOption,
    ItineraryCompletionRecommendation,
    ItineraryResponse,
    MealAdjacentRouteEvidence,
    MealCoverageStatus,
    MealRole,
    MealRouteEvidence,
    PlannerPreferencePolicy,
    POIType,
    ReplacementRouteImpact,
    ReplacementRouteLegEvidence,
    ScheduledPOI,
    ScheduledPOISourceType,
    SparseDaySummary,
    TimeBlockType,
    VerifiedPlaceRef,
)
from app.services.amap_direction import RoutePlanningError, get_walking_route
from app.services.amap_client import GEOCODE_CACHE
from app.services.mock_normalizer import infer_poi_profile
from app.services.meal_rhythm import (
    MEAL_RHYTHM_POLICY,
    MealRhythmDiagnostics,
    assess_meal_rhythm,
    is_meal_capable_item,
    is_meal_capable_category,
    meal_role_label,
    meal_window,
    minutes,
)
from app.services.preference_policy import StylePreferenceSignal
from app.services.poi_discovery_provider import (
    PoiDiscoveryCandidate,
    PoiDiscoveryProvider,
    PoiDiscoveryUnavailable,
    default_poi_discovery_provider,
)


@dataclass(frozen=True, slots=True)
class CandidateSpec:
    name: str
    type: POIType
    block_types: tuple[TimeBlockType, ...]
    areas: tuple[str, ...]
    themes: tuple[str, ...]
    duration_minutes: int
    profile_intensity: str
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True, slots=True)
class BlockFullnessSignal:
    block_type: TimeBlockType
    occupied_minutes: int
    meaningful: bool
    underfilled: bool


@dataclass(frozen=True, slots=True)
class CompletionTaskActionResult:
    itinerary: ItineraryResponse
    task_id: str
    applied: bool
    summary: str
    inserted_item: ScheduledPOI | None = None


ScoredCandidate = tuple[
    int,
    float,
    float,
    int,
    int,
    int,
    int,
    tuple[int, int, int, int],
    int,
    int,
    float,
    CandidateSpec,
]


AREA_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bund": ("外滩", "bfc", "南京路"),
    "old_town": ("豫园", "城隍庙", "老城厢"),
    "french_concession": ("武康路", "思南", "新天地", "田子坊", "复兴公园"),
    "jingan": ("静安寺", "自然博物馆"),
    "people_square": ("上海博物馆", "人民广场", "南京路"),
    "lujiazui": ("陆家嘴", "东方明珠", "滨江"),
}

THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "museum": ("博物馆", "museum"),
    "old_street": ("老街", "武康路", "思南", "田子坊", "弄堂"),
    "waterfront": ("外滩", "滨江", "江边", "river", "bund"),
    "street_food": ("小吃", "汤包", "夜市", "food", "美食"),
    "design": ("新天地", "田子坊", "公馆", "设计"),
    "garden": ("豫园", "公园", "寺"),
    "night": ("夜", "枫径", "步行街"),
}


CITY_COORDINATE_HINTS: dict[tuple[str, str], tuple[float, float]] = {
    ("上海", "上海自然博物馆"): (31.23349, 121.45862),
    ("上海", "静安寺"): (31.22346, 121.44531),
    ("上海", "思南公馆"): (31.214509, 121.468956),
    ("上海", "新天地"): (31.21943, 121.47529),
    ("上海", "田子坊"): (31.21103, 121.47055),
    ("上海", "上海博物馆"): (31.23041, 121.4737),
    ("上海", "陆家嘴滨江步道"): (31.23958, 121.50772),
    ("上海", "南京路步行街"): (31.236831, 121.483088),
    ("上海", "人民广场本帮菜午餐"): (31.23043, 121.47512),
    ("上海", "豫园"): (31.225312, 121.487633),
    ("上海", "城隍庙小吃街"): (31.22738, 121.49058),
    ("上海", "BFC 外滩枫径"): (31.23374, 121.49759),
    ("上海", "武康路咖啡街区"): (31.20458, 121.44284),
    ("上海", "外滩源散步"): (31.23918, 121.49095),
    ("上海", "愚园路街区"): (31.22284, 121.43883),
    ("上海", "上生新所"): (31.21191, 121.42291),
    ("上海", "徐家汇书院"): (31.19041, 121.43656),
    ("上海", "巨鹿路餐酒馆"): (31.22141, 121.45911),
    ("上海", "安福路咖啡小馆"): (31.21598, 121.44651),
    ("杭州", "西湖风景名胜区"): (30.24259, 120.14187),
    ("杭州", "灵隐寺"): (30.24011, 120.1022),
    ("杭州", "法喜寺"): (30.21968, 120.10776),
    ("杭州", "南宋御街"): (30.24678, 120.17085),
    ("杭州", "河坊街小吃街"): (30.24204, 120.17331),
    ("杭州", "西溪国家湿地公园"): (30.26959, 120.06351),
    ("杭州", "良渚博物院"): (30.37903, 120.02567),
    ("杭州", "龙井村茶歇"): (30.21829, 120.10924),
    ("杭州", "湖滨银泰夜景"): (30.25739, 120.16089),
    ("杭州", "武林夜市"): (30.27431, 120.16548),
    ("杭州", "小河直街"): (30.30423, 120.14561),
    ("杭州", "中国茶叶博物馆"): (30.22869, 120.10484),
    ("杭州", "大兜路历史街区"): (30.29721, 120.15102),
    ("杭州", "青芝坞餐厅"): (30.26049, 120.12745),
    ("杭州", "满觉陇茶歇"): (30.21477, 120.11953),
    ("杭州", "钱江新城灯光秀"): (30.24167, 120.21201),
}

AUTO_FILL_INSERTION_LIMIT = 3
COMPLETION_PREVIEW_MIN_CANDIDATES_BEFORE_SEARCH = 2
COMPLETION_PREVIEW_SEARCH_OFFSET = 8
COMPLETION_PREVIEW_SEARCH_POOL_LIMIT = 16
COMPLETION_PREVIEW_AROUND_SEARCH_RADIUS_METERS = 3500
MAX_SAFE_REPLACEMENT_ROUTE_INCREASE_SECONDS = 30 * 60
THINNEST_DAY_EARLY_AUTOFILL_SLOTS = 2
BOUNDARY_INSERTION_BUFFER_MINUTES = 15
MIDDLE_INSERTION_BUFFER_MINUTES = 20
EVENING_BLOCK_EXTRA_BUFFER_MINUTES = 10
RESTAURANT_BUFFER_DISCOUNT_MINUTES = 5
LIGHT_SCENIC_PROFILE_BUFFER_DISCOUNT_MINUTES = 5
HEAVY_SCENIC_PROFILE_BUFFER_EXTRA_MINUTES = 10
EXISTING_HEAVY_BLOCK_HEAVY_CANDIDATE_EXTRA_BUFFER_MINUTES = 15
EXISTING_HEAVY_BLOCK_MEDIUM_CANDIDATE_EXTRA_BUFFER_MINUTES = 5
HIGH_SCENIC_BLOCK_LOAD_EXTRA_BUFFER_MINUTES = 10
MODERATE_SCENIC_BLOCK_SATURATION_EXTRA_BUFFER_MINUTES = 10
HIGH_SCENIC_BLOCK_SATURATION_EXTRA_BUFFER_MINUTES = 20
DEFAULT_MODERATE_BLOCK_SATURATION_THRESHOLD = 0.5
DEFAULT_HIGH_BLOCK_SATURATION_THRESHOLD = 0.7
EVENING_MODERATE_BLOCK_SATURATION_THRESHOLD = 0.4
EVENING_HIGH_BLOCK_SATURATION_THRESHOLD = 0.6
MIDDLE_INSERTION_SATURATION_EXTRA_BUFFER_MINUTES = 5
LONG_SCENIC_DURATION_MINUTES = 120
LONG_SCENIC_SATURATION_EXTRA_BUFFER_MINUTES = 10
MIN_NORMALIZED_DETOUR_BASELINE_COST = 600.0
NORMALIZED_DETOUR_RATIO_TIE_EPSILON = 0.005
ABSOLUTE_DETOUR_DELTA_TIE_EPSILON = 30.0
PREFERENCE_ALIGNMENT_SCORE_CLOSE_GAP = 1
MEAL_REPAIR_PREFERENCE_ROUTE_CLOSE_DELTA_SECONDS = 480.0
MEAL_REPAIR_PREFERENCE_ROUTE_CLOSE_RATIO = 0.2
STRONG_ROUTE_DATA_QUALITY_TIER = 0
FALLBACK_ROUTE_DATA_QUALITY_TIER = 1
MISSING_ROUTE_DATA_QUALITY_TIER = 99
ALL_STRONG_ROUTE_EVIDENCE_TIER = 0
MIXED_ROUTE_EVIDENCE_TIER = 1
ALL_FALLBACK_ROUTE_EVIDENCE_TIER = 2
MISSING_ROUTE_EVIDENCE_TIER = 99
BASELINE_STRONG_MIXED_ROUTE_SOURCE_TIER = 0
BASELINE_FALLBACK_MIXED_ROUTE_SOURCE_TIER = 1
NEUTRAL_ROUTE_SOURCE_TIER = 0
MISSING_ROUTE_SOURCE_TIER = 99
BOTH_SIDE_LEGS_STRONG_TIER = 0
ONE_SIDE_STRONG_ONE_FALLBACK_TIER = 1
OTHER_SIDE_LEG_SYMMETRY_TIER = 0
MISSING_SIDE_LEG_SYMMETRY_TIER = 99
INBOUND_STRONG_DIRECTIONALITY_TIER = 0
STYLE_BUCKET_MUSEUM = "museum"
STYLE_BUCKET_OLD_STREET = "old_street"
STYLE_BUCKET_LANDMARK = "landmark"
STYLE_BUCKET_FOOD_STOP = "food_stop"
STYLE_BUCKET_NIGHT_VIEW = "night_view"
OUTBOUND_STRONG_DIRECTIONALITY_TIER = 1
NEUTRAL_DIRECTIONALITY_TIER = 0
MISSING_DIRECTIONALITY_TIER = 99


def normalize_city_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("市"):
        normalized = normalized[:-1]
    return normalized or None


def resolve_candidate_coordinates(
    name: str,
    city: str | None,
) -> tuple[float | None, float | None]:
    normalized_city = normalize_city_name(city)
    if normalized_city is not None:
        if (name, normalized_city) in GEOCODE_CACHE:
            return GEOCODE_CACHE[(name, normalized_city)]

    if (name, None) in GEOCODE_CACHE:
        return GEOCODE_CACHE[(name, None)]

    normalized_name = name.casefold()
    fuzzy_matches: list[tuple[int, float, float]] = []
    for (cached_name, cached_city), (latitude, longitude) in GEOCODE_CACHE.items():
        if normalized_city is not None and cached_city not in {normalized_city, None}:
            continue
        cached_normalized_name = cached_name.casefold()
        if normalized_name in cached_normalized_name or cached_normalized_name in normalized_name:
            fuzzy_matches.append((abs(len(cached_name) - len(name)), latitude, longitude))

    if fuzzy_matches:
        fuzzy_matches.sort(key=lambda item: item[0])
        _name_delta, latitude, longitude = fuzzy_matches[0]
        return latitude, longitude

    hinted = CITY_COORDINATE_HINTS.get((normalized_city or "", name))
    if hinted is not None:
        return hinted

    return None, None


def build_candidate(
    *,
    name: str,
    poi_type: POIType,
    block_types: tuple[TimeBlockType, ...],
    areas: tuple[str, ...],
    themes: tuple[str, ...],
    city: str | None = None,
) -> CandidateSpec:
    latitude, longitude = resolve_candidate_coordinates(name=name, city=city)
    profile = infer_poi_profile(name, poi_type)
    return CandidateSpec(
        name=name,
        type=poi_type,
        block_types=block_types,
        areas=areas,
        themes=themes,
        duration_minutes=profile.typical_duration_minutes,
        profile_intensity=profile.intensity,
        latitude=latitude,
        longitude=longitude,
    )


CITY_CANDIDATES: dict[str, list[CandidateSpec]] = {
    "上海": [
        build_candidate(
            name="豫园",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.MORNING, TimeBlockType.AFTERNOON),
            areas=("old_town",),
            themes=("old_street", "garden"),
            city="上海",
        ),
        build_candidate(
            name="上海自然博物馆",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.MORNING, TimeBlockType.AFTERNOON),
            areas=("jingan",),
            themes=("museum",),
            city="上海",
        ),
        build_candidate(
            name="静安寺",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.MORNING, TimeBlockType.AFTERNOON),
            areas=("jingan",),
            themes=("garden", "old_street"),
            city="上海",
        ),
        build_candidate(
            name="思南公馆",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.MORNING, TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("french_concession",),
            themes=("old_street", "design"),
            city="上海",
        ),
        build_candidate(
            name="新天地",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("french_concession",),
            themes=("design", "old_street"),
            city="上海",
        ),
        build_candidate(
            name="田子坊",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("french_concession",),
            themes=("design", "old_street"),
            city="上海",
        ),
        build_candidate(
            name="上海博物馆",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.AFTERNOON,),
            areas=("people_square",),
            themes=("museum",),
            city="上海",
        ),
        build_candidate(
            name="陆家嘴滨江步道",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("lujiazui",),
            themes=("waterfront",),
            city="上海",
        ),
        build_candidate(
            name="南京路步行街",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.EVENING,),
            areas=("bund", "people_square"),
            themes=("night", "street_food"),
            city="上海",
        ),
        build_candidate(
            name="人民广场本帮菜午餐",
            poi_type=POIType.RESTAURANT,
            block_types=(TimeBlockType.AFTERNOON,),
            areas=("people_square",),
            themes=("street_food",),
            city="上海",
        ),
        build_candidate(
            name="城隍庙小吃街",
            poi_type=POIType.RESTAURANT,
            block_types=(TimeBlockType.EVENING,),
            areas=("old_town",),
            themes=("street_food", "night"),
            city="上海",
        ),
        build_candidate(
            name="BFC 外滩枫径",
            poi_type=POIType.RESTAURANT,
            block_types=(TimeBlockType.EVENING,),
            areas=("bund",),
            themes=("night", "street_food", "waterfront"),
            city="上海",
        ),
        build_candidate(
            name="武康路咖啡街区",
            poi_type=POIType.RESTAURANT,
            block_types=(TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("french_concession",),
            themes=("design", "street_food", "old_street"),
            city="上海",
        ),
        build_candidate(
            name="愚园路街区",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("jingan",),
            themes=("old_street", "design"),
            city="上海",
        ),
        build_candidate(
            name="上生新所",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("french_concession",),
            themes=("design", "old_street"),
            city="上海",
        ),
        build_candidate(
            name="徐家汇书院",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.AFTERNOON,),
            areas=("xujiahui",),
            themes=("museum", "design"),
            city="上海",
        ),
        build_candidate(
            name="巨鹿路餐酒馆",
            poi_type=POIType.RESTAURANT,
            block_types=(TimeBlockType.EVENING,),
            areas=("french_concession",),
            themes=("night", "street_food"),
            city="上海",
        ),
    ],
    "杭州": [
        build_candidate(
            name="西湖风景名胜区",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.MORNING, TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("west_lake",),
            themes=("waterfront", "landmark", "garden"),
            city="杭州",
        ),
        build_candidate(
            name="灵隐寺",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.MORNING, TimeBlockType.AFTERNOON),
            areas=("lingyin",),
            themes=("garden", "old_street", "landmark"),
            city="杭州",
        ),
        build_candidate(
            name="法喜寺",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.MORNING, TimeBlockType.AFTERNOON),
            areas=("lingyin",),
            themes=("garden", "old_street"),
            city="杭州",
        ),
        build_candidate(
            name="南宋御街",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("old_town",),
            themes=("old_street", "street_food"),
            city="杭州",
        ),
        build_candidate(
            name="西溪国家湿地公园",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.MORNING, TimeBlockType.AFTERNOON),
            areas=("xixi",),
            themes=("garden", "waterfront"),
            city="杭州",
        ),
        build_candidate(
            name="良渚博物院",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.MORNING, TimeBlockType.AFTERNOON),
            areas=("liangzhu",),
            themes=("museum", "landmark"),
            city="杭州",
        ),
        build_candidate(
            name="龙井村茶歇",
            poi_type=POIType.RESTAURANT,
            block_types=(TimeBlockType.AFTERNOON,),
            areas=("lingyin", "longjing"),
            themes=("garden", "street_food"),
            city="杭州",
        ),
        build_candidate(
            name="河坊街小吃街",
            poi_type=POIType.RESTAURANT,
            block_types=(TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("old_town",),
            themes=("street_food", "old_street"),
            city="杭州",
        ),
        build_candidate(
            name="湖滨银泰夜景",
            poi_type=POIType.RESTAURANT,
            block_types=(TimeBlockType.EVENING,),
            areas=("west_lake", "hubin"),
            themes=("night", "street_food", "waterfront"),
            city="杭州",
        ),
        build_candidate(
            name="武林夜市",
            poi_type=POIType.RESTAURANT,
            block_types=(TimeBlockType.EVENING,),
            areas=("wulin",),
            themes=("night", "street_food"),
            city="杭州",
        ),
        build_candidate(
            name="小河直街",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("old_town",),
            themes=("old_street", "design"),
            city="杭州",
        ),
        build_candidate(
            name="中国茶叶博物馆",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.MORNING, TimeBlockType.AFTERNOON),
            areas=("longjing",),
            themes=("museum", "garden"),
            city="杭州",
        ),
        build_candidate(
            name="大兜路历史街区",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("old_town",),
            themes=("old_street", "street_food"),
            city="杭州",
        ),
        build_candidate(
            name="青芝坞餐厅",
            poi_type=POIType.RESTAURANT,
            block_types=(TimeBlockType.AFTERNOON, TimeBlockType.EVENING),
            areas=("west_lake",),
            themes=("street_food", "garden"),
            city="杭州",
        ),
        build_candidate(
            name="满觉陇茶歇",
            poi_type=POIType.RESTAURANT,
            block_types=(TimeBlockType.AFTERNOON,),
            areas=("longjing",),
            themes=("garden", "street_food"),
            city="杭州",
        ),
        build_candidate(
            name="钱江新城灯光秀",
            poi_type=POIType.SCENIC,
            block_types=(TimeBlockType.EVENING,),
            areas=("qianjiang",),
            themes=("night", "waterfront"),
            city="杭州",
        ),
    ],
}

DEFAULT_CANDIDATES: list[CandidateSpec] = [
    build_candidate(
        name="老城漫步补点",
        poi_type=POIType.SCENIC,
        block_types=(TimeBlockType.MORNING, TimeBlockType.AFTERNOON),
        areas=("central",),
        themes=("old_street",),
    ),
    build_candidate(
        name="城市博物馆补点",
        poi_type=POIType.SCENIC,
        block_types=(TimeBlockType.MORNING, TimeBlockType.AFTERNOON),
        areas=("central",),
        themes=("museum",),
    ),
    build_candidate(
        name="本地设计街区",
        poi_type=POIType.SCENIC,
        block_types=(TimeBlockType.AFTERNOON,),
        areas=("central",),
        themes=("design", "old_street"),
    ),
    build_candidate(
        name="本地午餐补点",
        poi_type=POIType.RESTAURANT,
        block_types=(TimeBlockType.AFTERNOON,),
        areas=("central",),
        themes=("street_food",),
    ),
    build_candidate(
        name="Food street dinner",
        poi_type=POIType.RESTAURANT,
        block_types=(TimeBlockType.EVENING,),
        areas=("central",),
        themes=("street_food", "night"),
    ),
    build_candidate(
        name="Riverfront evening walk",
        poi_type=POIType.SCENIC,
        block_types=(TimeBlockType.EVENING,),
        areas=("central",),
        themes=("waterfront", "night"),
    ),
]


def build_itinerary_completion_recommendation(
    itinerary: ItineraryResponse,
    preference_policy: PlannerPreferencePolicy | None = None,
    request_style_preferences: StylePreferenceSignal | set[str] | None = None,
) -> ItineraryCompletionRecommendation | None:
    sparse_days = summarize_sparse_days(itinerary.days, preference_policy)
    if not sparse_days:
        return None

    scheduled_items = [
        item
        for day in itinerary.days
        for block in day.blocks
        for item in block.items
    ]
    existing_names = {item.name for item in scheduled_items}
    inferred_city = infer_itinerary_city(itinerary, scheduled_items)
    city_candidates = CITY_CANDIDATES.get(inferred_city or "", [])
    trip_signal = build_signal_profile(scheduled_items)
    request_style_signal = normalize_style_preference_signal(request_style_preferences)
    trip_style_preferences = (
        request_style_signal
        if request_style_signal is not None
        else StylePreferenceSignal(
            inferred=frozenset(infer_dominant_style_preferences(scheduled_items))
        )
    )
    trip_centroid = build_centroid(scheduled_items)
    options: list[ItineraryCompletionOption] = []
    used_names: set[str] = set()

    for sparse_day in sparse_days:
        day_details = next(day for day in itinerary.days if day.day == sparse_day.day)
        day_items = [item for block in day_details.blocks for item in block.items]
        day_signal = build_signal_profile(day_items)
        day_centroid = build_centroid(day_items) or trip_centroid
        fullness_by_block = {
            signal.block_type: signal
            for signal in build_day_fullness_signals(day_details)
        }
        candidate_blocks = infer_fillable_blocks(
            day_details=day_details,
            city_candidates=city_candidates,
        )

        for block_type in candidate_blocks:
            target_block = next(
                (block for block in day_details.blocks if block.block_type == block_type),
                None,
            )
            if target_block is None:
                continue
            active_candidate_pool = city_candidates
            candidate = choose_candidate(
                candidates=city_candidates,
                day_details=day_details,
                target_block=target_block,
                block_type=block_type,
                existing_names=existing_names,
                used_names=used_names,
                day_signal=day_signal,
                trip_signal=trip_signal,
                style_preferences=trip_style_preferences,
                day_centroid=day_centroid,
                trip_centroid=trip_centroid,
                preference_policy=preference_policy,
            )
            if candidate is None:
                continue

            decision_evidence = build_completion_decision_evidence(
                block_type=block_type,
                candidate=candidate,
                day_items=day_items,
                candidate_pool=active_candidate_pool,
                day_details=day_details,
                target_block=target_block,
                existing_names=existing_names,
                used_names=used_names,
                trip_signal=trip_signal,
                day_centroid=day_centroid,
                trip_centroid=trip_centroid,
                style_preferences=trip_style_preferences,
                day_signal=day_signal,
                fullness_signal=fullness_by_block.get(block_type),
                request_style_preferences=request_style_signal,
                preference_policy=preference_policy,
            )
            used_names.add(candidate.name)
            options.append(
                ItineraryCompletionOption(
                    name=candidate.name,
                    type=candidate.type,
                    suggested_day=sparse_day.day,
                    suggested_block=block_type,
                    reasoning_summary=build_reasoning_summary(
                        day=sparse_day.day,
                        block_type=block_type,
                        candidate=candidate,
                        day_items=day_items,
                        candidate_pool=active_candidate_pool,
                        day_signal=day_signal,
                        fullness_signal=fullness_by_block.get(block_type),
                        sparse_day_rank=sparse_days.index(sparse_day),
                        sparse_day_count=len(sparse_days),
                        day_fullness_signals=list(fullness_by_block.values()),
                        request_style_preferences=request_style_signal,
                        preference_policy=preference_policy,
                    ),
                    itinerary_relation_summary=build_itinerary_relation_summary(
                        day=sparse_day.day,
                        block_type=block_type,
                        candidate=candidate,
                        day_items=day_items,
                    ),
                    decision_evidence=decision_evidence,
                )
            )
            if len(options) >= 6:
                break

        if len(options) >= 6:
            break

    if not options:
        return None

    return ItineraryCompletionRecommendation(
        summary=build_summary(
            sparse_days=sparse_days,
            options=options,
            total_day_count=len(itinerary.days),
        ),
        sparse_days=sparse_days,
        options=options,
    )


def apply_completion_recommendation_autofill(
    itinerary: ItineraryResponse,
    recommendation: ItineraryCompletionRecommendation,
) -> ItineraryResponse:
    updated_itinerary = itinerary.model_copy(deep=True)
    inserted_names: set[str] = set()
    inserted_blocks: set[tuple[int, TimeBlockType]] = set()

    for option in prioritized_autofill_options(recommendation):
        if len(inserted_names) >= AUTO_FILL_INSERTION_LIMIT:
            break

        target_day = next(
            (day for day in updated_itinerary.days if day.day == option.suggested_day),
            None,
        )
        if target_day is None:
            continue

        target_block = next(
            (block for block in target_day.blocks if block.block_type == option.suggested_block),
            None,
        )
        block_key = (option.suggested_day, option.suggested_block)
        if target_block is None or block_key in inserted_blocks:
            continue
        if option.name in inserted_names:
            continue
        if option.type == POIType.RESTAURANT:
            protected_meal_role = (
                MealRole.LUNCH
                if target_block.block_type == TimeBlockType.AFTERNOON
                else MealRole.DINNER
                if target_block.block_type == TimeBlockType.EVENING
                else None
            )
            protected_slot = next(
                (
                    slot
                    for day_summary in (updated_itinerary.meal_rhythm.days if updated_itinerary.meal_rhythm else [])
                    if day_summary.day == target_day.day
                    for slot in day_summary.slots
                    if slot.role == protected_meal_role
                ),
                None,
            )
            if (
                protected_slot is not None
                and protected_slot.status != MealCoverageStatus.NOT_APPLICABLE
            ) or any(is_meal_capable_item(item) for item in target_block.items):
                continue

        autofilled_item = build_autofilled_item(
            itinerary=updated_itinerary,
            day=target_day,
            option=option,
        )
        if autofilled_item is None:
            continue

        target_block.items.append(autofilled_item)
        target_block.items.sort(key=lambda item: (item.start_time, item.end_time, item.name))
        inserted_names.add(option.name)
        inserted_blocks.add(block_key)

    return updated_itinerary


def apply_completion_task_action(
    *,
    itinerary: ItineraryResponse,
    task_id: str,
    day: int | None = None,
    block_type: TimeBlockType | None = None,
    selected_candidate: ItineraryCompletionOption | None = None,
    completion_candidate_history: list[ItineraryCompletionOption] | None = None,
    preference_policy: PlannerPreferencePolicy | None = None,
    request_style_preferences: StylePreferenceSignal | set[str] | None = None,
) -> CompletionTaskActionResult:
    normalized_task_id = task_id.strip()
    if normalized_task_id == "repair_meal_anchor":
        return apply_repair_meal_anchor_task(
            itinerary=itinerary,
            task_id=normalized_task_id,
            day=day,
            block_type=block_type,
            selected_candidate=selected_candidate,
            completion_candidate_history=completion_candidate_history,
            preference_policy=preference_policy,
            request_style_preferences=request_style_preferences,
        )
    if normalized_task_id == "repair_evening_close":
        return apply_completion_candidate_task(
            itinerary=itinerary,
            task_id=normalized_task_id,
            day=day,
            block_type=block_type or TimeBlockType.EVENING,
            selected_candidate=selected_candidate,
            completion_candidate_history=completion_candidate_history,
            preference_policy=preference_policy,
            request_style_preferences=ensure_task_style_preference(
                request_style_preferences,
                STYLE_BUCKET_NIGHT_VIEW,
            ),
        )
    if normalized_task_id == "repair_sparse_block":
        return apply_completion_candidate_task(
            itinerary=itinerary,
            task_id=normalized_task_id,
            day=day,
            block_type=block_type,
            selected_candidate=selected_candidate,
            completion_candidate_history=completion_candidate_history,
            preference_policy=preference_policy,
            request_style_preferences=request_style_preferences,
        )

    return CompletionTaskActionResult(
        itinerary=itinerary,
        task_id=normalized_task_id,
        applied=False,
        summary=f"Unsupported completion task: {normalized_task_id}.",
    )


def apply_repair_meal_anchor_task(
    *,
    itinerary: ItineraryResponse,
    task_id: str,
    day: int | None,
    block_type: TimeBlockType | None,
    selected_candidate: ItineraryCompletionOption | None,
    completion_candidate_history: list[ItineraryCompletionOption] | None,
    preference_policy: PlannerPreferencePolicy | None,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
) -> CompletionTaskActionResult:
    updated_itinerary = itinerary.model_copy(deep=True)
    target = resolve_meal_task_target(
        itinerary=updated_itinerary,
        day=day,
        block_type=block_type,
    )
    if target is None:
        return CompletionTaskActionResult(
            itinerary=updated_itinerary,
            task_id=task_id,
            applied=False,
            summary="这条补全任务没有找到缺失的午餐或晚餐锚点。",
        )

    target_day, target_block = target
    scheduled_items = flatten_scheduled_items(updated_itinerary.days)
    restaurant_candidates = supplement_candidates_from_options(
        restaurant_candidates_for_itinerary(updated_itinerary, scheduled_items),
        completion_candidate_history or [],
        city=infer_itinerary_city(updated_itinerary, scheduled_items),
        target_day=target_day.day,
        target_block=target_block.block_type,
        poi_type=POIType.RESTAURANT,
    )
    ranked_candidates = rank_meal_repair_candidates(
        candidates=restaurant_candidates,
        day_details=target_day,
        target_block=target_block,
        block_type=target_block.block_type,
        existing_names={item.name for item in scheduled_items},
        used_names=set(),
        day_signal=build_signal_profile([item for block in target_day.blocks for item in block.items]),
        trip_signal=build_signal_profile(scheduled_items),
        day_centroid=build_centroid([item for block in target_day.blocks for item in block.items]),
        trip_centroid=build_centroid(scheduled_items),
        style_preferences=request_style_preferences,
        preference_policy=preference_policy,
    )
    candidate = select_candidate_from_ranked_options(
        ranked_candidates,
        selected_candidate,
        allow_zero_score=not any(block.items for block in target_day.blocks),
    ) if selected_candidate is not None else first_ranked_candidate(
        ranked_candidates,
        allow_zero_score=not any(block.items for block in target_day.blocks),
    )
    if candidate is None:
        block_label = format_block_label(target_block.block_type)
        summary = (
            f"所选候选已经不适合第 {target_day.day} 天{block_label}时段。"
            if selected_candidate is not None
            else f"第 {target_day.day} 天{block_label}时段暂时没有找到顺路的餐食候选。"
        )
        return CompletionTaskActionResult(
            itinerary=updated_itinerary,
            task_id=task_id,
            applied=False,
            summary=summary,
        )

    option = build_task_completion_option(
        candidate=candidate,
        day=target_day,
        target_block=target_block,
        candidate_pool=restaurant_candidates,
        preference_policy=preference_policy,
        request_style_preferences=request_style_preferences,
    )
    inserted_item = build_meal_repair_item(
        itinerary=updated_itinerary,
        day=target_day,
        target_block=target_block,
        candidate=candidate,
        option=option,
        request_style_preferences=request_style_preferences,
        preference_policy=preference_policy,
    )
    if inserted_item is None:
        block_label = format_block_label(target_block.block_type)
        return CompletionTaskActionResult(
            itinerary=updated_itinerary,
            task_id=task_id,
            applied=False,
            summary=f"第 {target_day.day} 天{block_label}时段没有足够空间插入餐食锚点。",
        )

    inserted_item.source_label = "补全任务：餐食锚点"
    inserted_item.source_reason = append_sentence_prefix(
        inserted_item.source_reason,
        "来自补全任务：系统修复了缺失的餐食锚点。",
    )
    target_block.items.append(inserted_item)
    target_block.items.sort(key=lambda item: (item.start_time, item.end_time, item.name))
    block_label = format_block_label(target_block.block_type)
    return CompletionTaskActionResult(
        itinerary=updated_itinerary,
        task_id=task_id,
        applied=True,
        summary=f"已把 {inserted_item.name} 补入第 {target_day.day} 天{block_label}时段，作为顺路的餐食锚点。",
        inserted_item=inserted_item,
    )


def apply_completion_candidate_task(
    *,
    itinerary: ItineraryResponse,
    task_id: str,
    day: int | None,
    block_type: TimeBlockType | None,
    selected_candidate: ItineraryCompletionOption | None,
    completion_candidate_history: list[ItineraryCompletionOption] | None,
    preference_policy: PlannerPreferencePolicy | None,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
) -> CompletionTaskActionResult:
    updated_itinerary = itinerary.model_copy(deep=True)
    target = resolve_completion_candidate_task_target(
        itinerary=updated_itinerary,
        task_id=task_id,
        day=day,
        block_type=block_type,
    )
    if target is None:
        return CompletionTaskActionResult(
            itinerary=updated_itinerary,
            task_id=task_id,
            applied=False,
            summary="这条补全任务没有找到适合修复的空档时段。",
        )

    target_day, target_block = target
    scheduled_items = flatten_scheduled_items(updated_itinerary.days)
    candidate_pool = supplement_candidates_from_options(
        candidate_pool_for_task(
            itinerary=updated_itinerary,
            scheduled_items=scheduled_items,
            task_id=task_id,
            target_block=target_block,
        ),
        completion_candidate_history or [],
        city=infer_itinerary_city(updated_itinerary, scheduled_items),
        target_day=target_day.day,
        target_block=target_block.block_type,
    )
    day_items = [item for block in target_day.blocks for item in block.items]
    ranked_candidates = rank_candidates_for_block(
        candidates=candidate_pool,
        day_details=target_day,
        target_block=target_block,
        block_type=target_block.block_type,
        existing_names={item.name for item in scheduled_items},
        used_names=set(),
        day_signal=build_signal_profile(day_items),
        trip_signal=build_signal_profile(scheduled_items),
        style_preferences=request_style_preferences,
        day_centroid=build_centroid(day_items),
        trip_centroid=build_centroid(scheduled_items),
        preference_policy=preference_policy,
    )
    candidate = select_candidate_from_ranked_options(
        ranked_candidates,
        selected_candidate,
        allow_zero_score=not day_items,
    ) if selected_candidate is not None else first_ranked_candidate(
        ranked_candidates,
        allow_zero_score=not day_items,
    )
    if candidate is None:
        block_label = format_block_label(target_block.block_type)
        summary = (
            f"所选候选已经不适合第 {target_day.day} 天{block_label}时段。"
            if selected_candidate is not None
            else f"第 {target_day.day} 天{block_label}时段暂时没有找到不会挤压行程的候选。"
        )
        return CompletionTaskActionResult(
            itinerary=updated_itinerary,
            task_id=task_id,
            applied=False,
            summary=summary,
        )

    option = build_task_completion_option(
        candidate=candidate,
        day=target_day,
        target_block=target_block,
        candidate_pool=candidate_pool,
        preference_policy=preference_policy,
        request_style_preferences=request_style_preferences,
    )
    inserted_item = build_autofilled_item(
        itinerary=updated_itinerary,
        day=target_day,
        option=option,
    )
    if inserted_item is None:
        block_label = format_block_label(target_block.block_type)
        return CompletionTaskActionResult(
            itinerary=updated_itinerary,
            task_id=task_id,
            applied=False,
            summary=f"第 {target_day.day} 天{block_label}时段没有足够空间插入这个补全候选。",
        )

    inserted_item.source_label = source_label_for_completion_task(task_id)
    inserted_item.source_reason = append_sentence_prefix(
        inserted_item.source_reason,
        "来自补全任务：系统根据当前空档、顺路程度和偏好插入这个地点。",
    )
    target_block.items.append(inserted_item)
    target_block.items.sort(key=lambda item: (item.start_time, item.end_time, item.name))
    block_label = format_block_label(target_block.block_type)
    return CompletionTaskActionResult(
        itinerary=updated_itinerary,
        task_id=task_id,
        applied=True,
        summary=f"已把 {inserted_item.name} 补入第 {target_day.day} 天{block_label}时段。",
        inserted_item=inserted_item,
    )


def preview_completion_task_candidates(
    *,
    itinerary: ItineraryResponse,
    task_id: str,
    day: int | None = None,
    block_type: TimeBlockType | None = None,
    completion_candidate_history: list[ItineraryCompletionOption] | None = None,
    preference_policy: PlannerPreferencePolicy | None = None,
    request_style_preferences: StylePreferenceSignal | set[str] | None = None,
    limit: int = 4,
    poi_discovery_provider: PoiDiscoveryProvider | None = None,
    minimum_options_before_search: int = COMPLETION_PREVIEW_MIN_CANDIDATES_BEFORE_SEARCH,
) -> tuple[
    int | None,
    TimeBlockType | None,
    str,
    list[ItineraryCompletionOption],
    str | None,
    str | None,
]:
    normalized_task_id = task_id.strip()
    effective_style_preferences = request_style_preferences
    if normalized_task_id == "repair_evening_close":
        effective_style_preferences = ensure_task_style_preference(
            request_style_preferences,
            STYLE_BUCKET_NIGHT_VIEW,
        )
    if normalized_task_id == "repair_meal_anchor":
        target = resolve_meal_task_target(
            itinerary=itinerary,
            day=day,
            block_type=block_type,
        )
    else:
        target = resolve_completion_candidate_task_target(
            itinerary=itinerary,
            task_id=normalized_task_id,
            day=day,
            block_type=(
                block_type or TimeBlockType.EVENING
                if normalized_task_id == "repair_evening_close"
                else block_type
            ),
        )
    if target is None:
        return None, None, "No suitable target block was found for this completion task.", [], None, "empty"

    target_day, target_block = target
    scheduled_items = flatten_scheduled_items(itinerary.days)
    day_items = [item for block in target_day.blocks for item in block.items]
    city = infer_itinerary_city(itinerary, scheduled_items)
    discovery_provider = poi_discovery_provider or default_poi_discovery_provider()
    discovery_capability = discovery_provider.capability()
    local_catalog_allowed = (
        discovery_capability.poi_discovery_enabled
        or discovery_capability.catalog_fallback_enabled
        or not discovery_capability.required
    )

    if normalized_task_id == "repair_meal_anchor":
        base_candidates = (
            restaurant_candidates_for_itinerary(itinerary, scheduled_items)
            if local_catalog_allowed
            else []
        )
        candidate_pool = supplement_candidates_from_options(
            base_candidates,
            completion_candidate_history or [],
            city=city,
            target_day=target_day.day,
            target_block=target_block.block_type,
            poi_type=POIType.RESTAURANT,
        )
    else:
        base_candidates = (
            candidate_pool_for_task(
                itinerary=itinerary,
                scheduled_items=scheduled_items,
                task_id=normalized_task_id,
                target_block=target_block,
            )
            if local_catalog_allowed
            else []
        )
        candidate_pool = supplement_candidates_from_options(
            base_candidates,
            completion_candidate_history or [],
            city=city,
            target_day=target_day.day,
            target_block=target_block.block_type,
        )

    def ranked_preview_candidates(pool: list[CandidateSpec]) -> list[CandidateSpec]:
        if normalized_task_id == "repair_meal_anchor":
            ranked = rank_meal_repair_candidates(
                candidates=pool,
                day_details=target_day,
                target_block=target_block,
                block_type=target_block.block_type,
                existing_names={item.name for item in scheduled_items},
                used_names=set(),
                day_signal=build_signal_profile(day_items),
                trip_signal=build_signal_profile(scheduled_items),
                day_centroid=build_centroid(day_items),
                trip_centroid=build_centroid(scheduled_items),
                style_preferences=effective_style_preferences,
                preference_policy=preference_policy,
            )
        else:
            ranked = rank_candidates_for_block(
                candidates=pool,
                day_details=target_day,
                target_block=target_block,
                block_type=target_block.block_type,
                existing_names={item.name for item in scheduled_items},
                used_names=set(),
                day_signal=build_signal_profile(day_items),
                trip_signal=build_signal_profile(scheduled_items),
                day_centroid=build_centroid(day_items),
                trip_centroid=build_centroid(scheduled_items),
                style_preferences=effective_style_preferences,
                preference_policy=preference_policy,
            )
        return ranked_candidates_to_candidates(
            ranked,
            allow_zero_score=not day_items,
        )

    preview_candidates = ranked_preview_candidates(candidate_pool)
    searched_candidates: list[CandidateSpec] = []
    search_status: str | None = None
    discovery_status: str | None = None
    if len(preview_candidates) < minimum_options_before_search:
        searched_candidates, search_status, discovery_status = search_completion_task_candidate_specs(
            itinerary=itinerary,
            task_id=normalized_task_id,
            city=city,
            target_day=target_day,
            target_block=target_block.block_type,
            provider=discovery_provider,
        )
        if searched_candidates:
            candidate_pool = merge_candidate_specs(candidate_pool, searched_candidates)
            preview_candidates = ranked_preview_candidates(candidate_pool)

    options = [
        build_task_completion_option(
            candidate=candidate,
            day=target_day,
            target_block=target_block,
            candidate_pool=candidate_pool,
            preference_policy=preference_policy,
            request_style_preferences=effective_style_preferences,
        )
        for candidate in preview_candidates[: max(1, limit)]
    ]
    summary = (
        f"Found {len(options)} route-compatible candidate(s) for Day {target_day.day} "
        f"{target_block.block_type.value}."
        if options
        else f"No route-compatible candidates are currently available for Day {target_day.day} {target_block.block_type.value}."
    )
    source_summary = build_completion_preview_source_summary(
        base_count=len(base_candidates),
        history_count=count_targeted_completion_history_options(
            completion_candidate_history or [],
            target_day=target_day.day,
            target_block=target_block.block_type,
            poi_type=POIType.RESTAURANT if normalized_task_id == "repair_meal_anchor" else None,
        ),
        search_count=len(searched_candidates),
        search_status=search_status,
        discovery_status=discovery_status,
    )
    final_discovery_status = normalize_completion_discovery_status(
        discovery_status=discovery_status,
        has_options=bool(options),
        used_search=bool(searched_candidates),
    )
    return (
        target_day.day,
        target_block.block_type,
        summary,
        options,
        source_summary,
        final_discovery_status,
    )


def preview_safe_replace_candidates(
    *,
    itinerary: ItineraryResponse,
    stop_id: str,
    preference_policy: PlannerPreferencePolicy | None = None,
    request_style_preferences: StylePreferenceSignal | set[str] | None = None,
    poi_discovery_provider: PoiDiscoveryProvider | None = None,
    limit: int = 3,
) -> tuple[
    int | None,
    TimeBlockType | None,
    str,
    list[ItineraryCompletionOption],
    str | None,
    str | None,
]:
    """Return a bounded provider-backed set for one verified flexible stop."""

    located = find_scheduled_stop(itinerary, stop_id)
    if located is None:
        return None, None, "The selected stop no longer exists.", [], None, "empty"
    day, block, target = located
    source_type = target.source_type.value
    if (
        target.is_fixed
        or source_type not in {"auto_seeded_poi", "auto_seeded_meal", "auto_filled"}
        or target.source_label == "必去"
        or not target.stable_id
        or not target.canonical_place_id
        or target.verified_place is None
    ):
        return (
            day.day,
            block.block_type,
            "This stop is protected or does not yet have a verified place identity.",
            [],
            "Only verified system-suggested stops can be replaced.",
            "empty",
        )

    provider = poi_discovery_provider or default_poi_discovery_provider()
    capability = provider.capability()
    if not capability.poi_discovery_enabled:
        return (
            day.day,
            block.block_type,
            "Verified replacement discovery is currently unavailable.",
            [],
            "No unverified catalog fallback is used for replacement.",
            "empty",
        )

    keyword = "餐厅" if target.type == POIType.RESTAURANT else (target.verified_place.category or target.name)
    try:
        places = provider.search_around(
            keyword=keyword,
            city=target.city or "",
            latitude=target.latitude,
            longitude=target.longitude,
            radius=COMPLETION_PREVIEW_AROUND_SEARCH_RADIUS_METERS,
            offset=COMPLETION_PREVIEW_SEARCH_OFFSET,
        )
    except PoiDiscoveryUnavailable:
        return (
            day.day,
            block.block_type,
            "Verified replacement discovery is currently unavailable.",
            [],
            "The provider request failed; the current route remains unchanged.",
            "empty",
        )

    options: list[ItineraryCompletionOption] = []
    seen_ids: set[str] = set()
    scheduled_provider_ids = {
        item.canonical_place_id
        for itinerary_day in itinerary.days
        for scheduled_block in itinerary_day.blocks
        for item in scheduled_block.items
        if item.stable_id != target.stable_id and item.canonical_place_id
    }
    scheduled_names = {
        item.name.strip()
        for itinerary_day in itinerary.days
        for scheduled_block in itinerary_day.blocks
        for item in scheduled_block.items
        if item.stable_id != target.stable_id
    }
    display_limit = max(0, min(limit, 3))
    for place in places[:COMPLETION_PREVIEW_SEARCH_OFFSET]:
        if (
            not place.provider_place_id
            or not place.name
            or place.latitude is None
            or place.longitude is None
            or place.provider_place_id == target.canonical_place_id
            or place.name.strip() == target.name.strip()
            or place.provider_place_id in scheduled_provider_ids
            or place.name.strip() in scheduled_names
            or place.provider_place_id in seen_ids
            or not replacement_candidate_category_compatible(target.type, place)
        ):
            continue
        seen_ids.add(place.provider_place_id)
        impact = replacement_route_impact(
            day=day,
            target=target,
            candidate_name=place.name,
            candidate_latitude=float(place.latitude),
            candidate_longitude=float(place.longitude),
        )
        if not replacement_route_is_actionable(day=day, target=target, impact=impact):
            continue
        verified_place = VerifiedPlaceRef(
            stable_id=f"amap:{place.provider_place_id}",
            original_name=place.name,
            canonical_name=place.name,
            provider="amap",
            provider_place_id=place.provider_place_id,
            latitude=float(place.latitude),
            longitude=float(place.longitude),
            category=place.type,
        )
        options.append(
            ItineraryCompletionOption(
                stable_id=verified_place.stable_id,
                name=place.name,
                type=target.type,
                suggested_day=day.day,
                suggested_block=block.block_type,
                reasoning_summary=replacement_candidate_summary(
                    impact=impact,
                    option_name=place.name,
                    option_type=target.type,
                    request_style_preferences=request_style_preferences,
                ),
                itinerary_relation_summary="只替换这一站，并重新检查它前后的两段路线。",
                verified_place=verified_place,
                route_impact=impact,
            )
        )

    options.sort(
        key=cmp_to_key(
            lambda left, right: compare_safe_replace_candidates(
                left=left,
                right=right,
                preference_policy=preference_policy,
                request_style_preferences=request_style_preferences,
            )
        )
    )
    bounded = options[:display_limit]
    return (
        day.day,
        block.block_type,
        f"Found {len(bounded)} verified replacement candidate(s).",
        bounded,
        "Candidates came from the existing POI provider and were checked against the adjacent route legs.",
        "route_context" if bounded else "empty",
    )


def compare_safe_replace_candidates(
    *,
    left: ItineraryCompletionOption,
    right: ItineraryCompletionOption,
    preference_policy: PlannerPreferencePolicy | None,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
) -> int:
    """Keep verified route safety primary, then honor a close-route food preference."""

    preference_ranking = compare_safe_replace_preference_alignment(
        left=left,
        right=right,
        preference_policy=preference_policy,
        request_style_preferences=request_style_preferences,
    )
    if preference_ranking and safe_replace_routes_are_close(
        left.route_impact,
        right.route_impact,
    ):
        return preference_ranking

    left_route = (
        left.route_impact.delta_duration_s,
        left.route_impact.after_duration_s,
        replacement_route_distance(left.route_impact),
        left.verified_place.provider_place_id,
    )
    right_route = (
        right.route_impact.delta_duration_s,
        right.route_impact.after_duration_s,
        replacement_route_distance(right.route_impact),
        right.verified_place.provider_place_id,
    )
    if left_route != right_route:
        return -1 if left_route < right_route else 1
    if preference_ranking:
        return preference_ranking
    return 0


def compare_safe_replace_preference_alignment(
    *,
    left: ItineraryCompletionOption,
    right: ItineraryCompletionOption,
    preference_policy: PlannerPreferencePolicy | None,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
) -> int:
    left_key = safe_replace_preference_alignment_key(
        option=left,
        preference_policy=preference_policy,
        request_style_preferences=request_style_preferences,
    )
    right_key = safe_replace_preference_alignment_key(
        option=right,
        preference_policy=preference_policy,
        request_style_preferences=request_style_preferences,
    )
    if left_key == right_key:
        return 0
    return -1 if left_key < right_key else 1


def safe_replace_preference_alignment_key(
    *,
    option: ItineraryCompletionOption,
    preference_policy: PlannerPreferencePolicy | None,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
) -> tuple[int, int]:
    """Rank only verified candidates; this never admits a candidate or changes a route."""

    style_signal = normalize_style_preference_signal(request_style_preferences)
    profile = infer_poi_profile(option.name, option.type)
    food_style_rank = 1
    if style_signal and style_signal.source_for(STYLE_BUCKET_FOOD_STOP) == "explicit":
        food_style_rank = 0 if profile.visit_style == POIVisitStyle.FOOD_DISTRICT else 1

    dining_rank = 1
    if preference_policy is not None and preference_policy.dining_priority == "high":
        dining_rank = 0 if profile.visit_style == POIVisitStyle.FOOD_DISTRICT else 1
    return food_style_rank, dining_rank


def safe_replace_preference_reason(
    *,
    option_name: str,
    option_type: POIType,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
) -> str:
    style_signal = normalize_style_preference_signal(request_style_preferences)
    profile = infer_poi_profile(option_name, option_type)
    if (
        style_signal
        and style_signal.source_for(STYLE_BUCKET_FOOD_STOP) == "explicit"
        and profile.visit_style == POIVisitStyle.FOOD_DISTRICT
    ):
        return "它也贴合你明确提到的本地小吃偏好。"
    return ""


def replacement_candidate_summary(
    *,
    impact: ReplacementRouteImpact,
    option_name: str,
    option_type: POIType,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
) -> str:
    route_reason = replacement_candidate_reason(impact)
    preference_reason = safe_replace_preference_reason(
        option_name=option_name,
        option_type=option_type,
        request_style_preferences=request_style_preferences,
    )
    return append_sentence_prefix(route_reason, preference_reason) if preference_reason else route_reason


def safe_replace_routes_are_close(
    left: ReplacementRouteImpact,
    right: ReplacementRouteImpact,
) -> bool:
    if left.delta_duration_s is None or right.delta_duration_s is None:
        return False
    return abs(left.delta_duration_s - right.delta_duration_s) <= MEAL_REPAIR_PREFERENCE_ROUTE_CLOSE_DELTA_SECONDS


def replacement_candidate_category_compatible(
    target_type: POIType,
    place: PoiDiscoveryCandidate,
) -> bool:
    """Apply the existing same-type replacement boundary to AMap categories."""

    typecode = (place.typecode or "").strip()
    if target_type == POIType.RESTAURANT:
        return typecode.startswith("05")
    if target_type == POIType.SCENIC:
        return typecode.startswith(("11", "14"))
    return False


def replacement_route_is_actionable(
    *,
    day: DayItinerary,
    target: ScheduledPOI,
    impact: ReplacementRouteImpact,
) -> bool:
    ordered = sorted(
        (item for block in day.blocks for item in block.items),
        key=lambda item: (item.start_time, item.end_time, item.name),
    )
    target_index = next(index for index, item in enumerate(ordered) if item.stable_id == target.stable_id)
    has_successor = target_index + 1 < len(ordered)
    return bool(
        impact.safe_to_apply
        and impact.blocking_reason is None
        and impact.before_duration_s is not None
        and impact.after_duration_s is not None
        and impact.delta_duration_s is not None
        and impact.delta_duration_s <= MAX_SAFE_REPLACEMENT_ROUTE_INCREASE_SECONDS
        and impact.inbound is not None
        and (not has_successor or impact.outbound is not None)
    )


def replacement_route_distance(impact: ReplacementRouteImpact) -> int:
    return sum(
        leg.distance_m
        for leg in (impact.inbound, impact.outbound)
        if leg is not None
    )


def find_scheduled_stop(
    itinerary: ItineraryResponse,
    stop_id: str,
) -> tuple[DayItinerary, DayTimeBlock, ScheduledPOI] | None:
    for day in itinerary.days:
        for block in day.blocks:
            for item in block.items:
                if item.stable_id == stop_id:
                    return day, block, item
    return None


def replacement_route_impact(
    *,
    day: DayItinerary,
    target: ScheduledPOI,
    candidate_name: str,
    candidate_latitude: float,
    candidate_longitude: float,
) -> ReplacementRouteImpact:
    ordered = sorted(
        (item for block in day.blocks for item in block.items),
        key=lambda item: (item.start_time, item.end_time, item.name),
    )
    target_index = next(index for index, item in enumerate(ordered) if item.stable_id == target.stable_id)
    previous = ordered[target_index - 1] if target_index > 0 else day.hotel
    following = ordered[target_index + 1] if target_index + 1 < len(ordered) else None
    inbound = verified_replacement_leg(
        from_name=previous.name,
        from_latitude=previous.latitude,
        from_longitude=previous.longitude,
        to_name=candidate_name,
        to_latitude=candidate_latitude,
        to_longitude=candidate_longitude,
    )
    outbound = (
        verified_replacement_leg(
            from_name=candidate_name,
            from_latitude=candidate_latitude,
            from_longitude=candidate_longitude,
            to_name=following.name,
            to_latitude=following.latitude,
            to_longitude=following.longitude,
        )
        if following is not None
        else None
    )
    before_parts = [target.travel_duration_s]
    if following is not None:
        before_parts.append(following.travel_duration_s)
    before_duration = sum(part for part in before_parts if part is not None) if any(part is not None for part in before_parts) else None
    if inbound is None or (following is not None and outbound is None):
        return ReplacementRouteImpact(
            safe_to_apply=False,
            before_duration_s=before_duration,
            blocking_reason="route_unavailable",
        )

    after_duration = inbound.duration_s + (outbound.duration_s if outbound is not None else 0)
    inbound_budget = confirmed_adjacent_route_budget(
        item=target,
        expected_from_name=previous.name,
    ) + (
        seconds_between(previous.end_time, target.start_time)
        if isinstance(previous, ScheduledPOI)
        else 0
    )
    outbound_budget = (
        confirmed_adjacent_route_budget(
            item=following,
            expected_from_name=target.name,
        )
        + seconds_between(target.end_time, following.start_time)
        if following is not None
        else None
    )
    blocking_reason = replacement_timing_conflict(
        following=following,
        inbound_duration_s=inbound.duration_s,
        outbound_duration_s=outbound.duration_s if outbound is not None else None,
        inbound_budget_s=inbound_budget,
        outbound_budget_s=outbound_budget,
    )
    return ReplacementRouteImpact(
        safe_to_apply=blocking_reason is None,
        before_duration_s=before_duration,
        after_duration_s=after_duration,
        delta_duration_s=after_duration - before_duration if before_duration is not None else None,
        inbound=inbound,
        outbound=outbound,
        blocking_reason=blocking_reason,
    )


def verified_replacement_leg(
    *,
    from_name: str,
    from_latitude: float,
    from_longitude: float,
    to_name: str,
    to_latitude: float,
    to_longitude: float,
) -> ReplacementRouteLegEvidence | None:
    try:
        route = get_walking_route(
            origin_lat=from_latitude,
            origin_lng=from_longitude,
            dest_lat=to_latitude,
            dest_lng=to_longitude,
        )
    except RoutePlanningError:
        return None
    distance_m = int(route.get("distance_m") or 0)
    duration_s = int(route.get("duration_s") or 0)
    if distance_m <= 0 or duration_s <= 0:
        return None
    return ReplacementRouteLegEvidence(
        from_name=from_name,
        to_name=to_name,
        distance_m=distance_m,
        duration_s=duration_s,
        provider="amap",
    )


def replacement_timing_conflict(
    *,
    following: ScheduledPOI | None,
    inbound_duration_s: int,
    outbound_duration_s: int | None,
    inbound_budget_s: int,
    outbound_budget_s: int | None,
) -> str | None:
    if inbound_duration_s > inbound_budget_s:
        return "time_slot_conflict"
    if (
        following is not None
        and outbound_duration_s is not None
        and outbound_budget_s is not None
        and outbound_duration_s > outbound_budget_s
    ):
        return "fixed_event_at_risk" if following.is_fixed else "time_slot_conflict"
    return None


def confirmed_adjacent_route_budget(
    *,
    item: ScheduledPOI,
    expected_from_name: str,
) -> int:
    if (
        item.travel_data_status != "confirmed"
        or item.travel_duration_s is None
        or item.travel_duration_s <= 0
        or not item.travel_from_name
        or item.travel_from_name.strip() != expected_from_name.strip()
    ):
        return 0
    return item.travel_duration_s


def seconds_between(start: time, end: time) -> int:
    return max(0, (end.hour * 3600 + end.minute * 60 + end.second) - (start.hour * 3600 + start.minute * 60 + start.second))


def replacement_candidate_reason(impact: ReplacementRouteImpact) -> str:
    if impact.blocking_reason == "fixed_event_at_risk":
        return "这个地点是真实候选，但可能赶不上后面的固定安排。"
    if not impact.safe_to_apply:
        return "这个地点是真实候选，但当前路线证据还不足以安全换入。"
    if impact.delta_duration_s is not None and impact.delta_duration_s < 0:
        return "它仍适合当前时段，而且前后两段路程更短。"
    if impact.delta_duration_s is not None and impact.delta_duration_s > 0:
        return "它适合当前时段；路线会稍长，但仍能接上后面的安排。"
    return "它适合当前时段，并且前后路线已经确认。"


def search_completion_task_candidate_specs(
    *,
    itinerary: ItineraryResponse,
    task_id: str,
    city: str | None,
    target_day: DayItinerary,
    target_block: TimeBlockType,
    provider: PoiDiscoveryProvider | None,
) -> tuple[list[CandidateSpec], str, str]:
    if not city:
        return [], "无法确定城市，当前使用本地候选模式。", "local_only"

    discovery_provider = provider or default_poi_discovery_provider()
    capability = discovery_provider.capability()
    if not capability.poi_discovery_enabled:
        missing = "、".join(capability.missing_config) or "POI provider config"
        if capability.required and not capability.catalog_fallback_enabled:
            return [], f"实时地点发现是必需能力但未配置（缺少 {missing}），不会展示占位候选。", "empty"
        return [], f"当前未启用实时地点发现（缺少 {missing}），只使用已解析地点和历史候选。", "local_only"

    candidates: list[CandidateSpec] = []
    seen: set[tuple[str, POIType]] = set()
    route_center = completion_task_route_search_center(
        itinerary=itinerary,
        day=target_day,
        target_block=find_block(target_day, target_block),
    )

    def add_places(places: list[PoiDiscoveryCandidate], keyword: str) -> None:
        for place in places:
            candidate = candidate_spec_from_place_search_result(
                place=place,
                task_id=task_id,
                keyword=keyword,
                target_block=target_block,
                city=city,
            )
            if candidate is None:
                continue
            key = (candidate.name, candidate.type)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)

    around_error: PoiDiscoveryUnavailable | None = None
    if route_center is not None:
        try:
            for keyword in completion_task_search_keywords(task_id, target_block):
                add_places(
                    discovery_provider.search_around(
                        keyword=keyword,
                        city=city,
                        latitude=route_center[0],
                        longitude=route_center[1],
                        radius=COMPLETION_PREVIEW_AROUND_SEARCH_RADIUS_METERS,
                        offset=COMPLETION_PREVIEW_SEARCH_OFFSET,
                    ),
                    keyword,
                )
                if len(candidates) >= COMPLETION_PREVIEW_SEARCH_POOL_LIMIT:
                    return (
                        candidates,
                        "已根据当前路线附近位置补充候选，并继续通过顺路与时间适配排序。",
                        "route_context",
                    )
        except PoiDiscoveryUnavailable as exc:
            around_error = exc

    if candidates:
        return (
            candidates,
            "已根据当前路线附近位置补充候选，并继续通过顺路与时间适配排序。",
            "route_context",
        )

    try:
        for keyword in completion_task_search_keywords(task_id, target_block):
            add_places(
                discovery_provider.search_text(
                    keyword=keyword,
                    city=city,
                    offset=COMPLETION_PREVIEW_SEARCH_OFFSET,
                ),
                keyword,
            )
            if len(candidates) >= COMPLETION_PREVIEW_SEARCH_POOL_LIMIT:
                return candidates, "已用城市 POI 搜索补充候选，并继续通过顺路与时间适配排序。", "city_text"
    except PoiDiscoveryUnavailable as exc:
        reason = around_error or exc
        return [], f"Amap 搜索暂不可用，当前使用本地候选模式：{reason}", "local_only"

    if candidates:
        return candidates, "已用城市 POI 搜索补充候选，并继续通过顺路与时间适配排序。", "city_text"
    if around_error is not None:
        return [], f"路线附近搜索暂不可用，城市搜索也没有找到可用候选：{around_error}", "empty"
    return [], "Amap 搜索没有找到可用于该 block 的补充候选。", "empty"


def completion_task_route_search_center(
    *,
    itinerary: ItineraryResponse,
    day: DayItinerary,
    target_block: DayTimeBlock | None,
) -> tuple[float, float] | None:
    if target_block is not None:
        anchors = [
            anchor
            for anchor in (
                previous_route_context_anchor(day=day, target_block=target_block),
                next_route_context_anchor(day=day, target_block=target_block),
            )
            if anchor is not None and anchor.latitude is not None and anchor.longitude is not None
        ]
        if len(anchors) >= 2:
            return (
                sum(anchor.latitude for anchor in anchors) / len(anchors),
                sum(anchor.longitude for anchor in anchors) / len(anchors),
            )
        if len(anchors) == 1:
            return anchors[0].latitude, anchors[0].longitude

    day_centroid = build_centroid([item for block in day.blocks for item in block.items])
    if day_centroid is not None:
        return day_centroid
    if day.hotel.latitude is not None and day.hotel.longitude is not None:
        return day.hotel.latitude, day.hotel.longitude
    if itinerary.hotel and itinerary.hotel.latitude is not None and itinerary.hotel.longitude is not None:
        return itinerary.hotel.latitude, itinerary.hotel.longitude
    return None


def previous_route_context_anchor(
    *,
    day: DayItinerary,
    target_block: DayTimeBlock,
) -> ScheduledPOI | HotelStay | None:
    previous_items = [
        item
        for block in day.blocks
        if block.start_time < target_block.start_time
        for item in block.items
        if item.latitude is not None and item.longitude is not None
    ]
    if previous_items:
        return max(previous_items, key=lambda item: (item.end_time, item.start_time, item.name))
    return day.hotel if day.hotel.latitude is not None and day.hotel.longitude is not None else None


def next_route_context_anchor(
    *,
    day: DayItinerary,
    target_block: DayTimeBlock,
) -> ScheduledPOI | HotelStay | None:
    following_items = [
        item
        for block in day.blocks
        if block.start_time > target_block.start_time
        for item in block.items
        if item.latitude is not None and item.longitude is not None
    ]
    if following_items:
        return min(following_items, key=lambda item: (item.start_time, item.end_time, item.name))
    return day.hotel if day.hotel.latitude is not None and day.hotel.longitude is not None else None


def completion_task_search_keywords(
    task_id: str,
    target_block: TimeBlockType,
) -> tuple[str, ...]:
    if task_id == "repair_meal_anchor":
        return ("午餐", "餐厅") if target_block == TimeBlockType.AFTERNOON else ("晚餐", "餐厅")
    if task_id == "repair_evening_close":
        return ("夜景", "夜市", "散步", "餐厅")
    return ("景点", "街区", "博物馆", "咖啡")


def candidate_spec_from_place_search_result(
    *,
    place: PoiDiscoveryCandidate,
    task_id: str,
    keyword: str,
    target_block: TimeBlockType,
    city: str,
) -> CandidateSpec | None:
    name = place.name
    latitude = place.latitude
    longitude = place.longitude
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return None

    normalized_name = name.strip()
    normalized_city = city.strip() if city else None
    coordinates = (float(latitude), float(longitude))
    GEOCODE_CACHE[(normalized_name, normalized_city)] = coordinates
    GEOCODE_CACHE[(normalized_name, None)] = coordinates

    poi_type = infer_place_search_poi_type(
        place=place,
        task_id=task_id,
        keyword=keyword,
    )
    profile = infer_poi_profile(normalized_name, poi_type)
    business_area = place.business_area
    areas = (business_area.strip(),) if isinstance(business_area, str) and business_area.strip() else ()
    return CandidateSpec(
        name=normalized_name,
        type=poi_type,
        block_types=(target_block,),
        areas=areas,
        themes=infer_place_search_themes(
            name=name,
            category=place.type or "",
            keyword=keyword,
        ),
        duration_minutes=profile.typical_duration_minutes,
        profile_intensity=profile.intensity,
        latitude=coordinates[0],
        longitude=coordinates[1],
    )


def infer_place_search_poi_type(
    *,
    place: PoiDiscoveryCandidate,
    task_id: str,
    keyword: str,
) -> POIType:
    if task_id == "repair_meal_anchor":
        return POIType.RESTAURANT
    text = f"{place.name or ''} {place.type or ''} {keyword}"
    if any(token in text for token in ("餐饮", "美食", "餐厅", "小吃", "咖啡", "茶饮")):
        return POIType.RESTAURANT
    return POIType.SCENIC


def infer_place_search_themes(
    *,
    name: str,
    category: str,
    keyword: str,
) -> tuple[str, ...]:
    text = f"{name} {category} {keyword}".casefold()
    themes: list[str] = []
    for theme, tokens in THEME_KEYWORDS.items():
        if any(token.casefold() in text for token in tokens):
            themes.append(theme)
    if keyword in {"夜景", "夜市"} and "night" not in themes:
        themes.append("night")
    if keyword == "街区" and "old_street" not in themes:
        themes.append("old_street")
    if keyword == "博物馆" and "museum" not in themes:
        themes.append("museum")
    if keyword in {"午餐", "晚餐", "餐厅", "咖啡"} and "street_food" not in themes:
        themes.append("street_food")
    return tuple(themes)


def merge_candidate_specs(
    *candidate_groups: list[CandidateSpec],
) -> list[CandidateSpec]:
    by_key: dict[tuple[str, POIType], CandidateSpec] = {}
    for group in candidate_groups:
        for candidate in group:
            by_key.setdefault((candidate.name, candidate.type), candidate)
    return list(by_key.values())


def count_targeted_completion_history_options(
    options: list[ItineraryCompletionOption],
    *,
    target_day: int,
    target_block: TimeBlockType,
    poi_type: POIType | None = None,
) -> int:
    return sum(
        1
        for option in options
        if option.suggested_day == target_day
        and option.suggested_block == target_block
        and (poi_type is None or option.type == poi_type)
    )


def build_completion_preview_source_summary(
    *,
    base_count: int,
    history_count: int,
    search_count: int,
    search_status: str | None,
    discovery_status: str | None,
) -> str:
    sources: list[str] = []
    if base_count:
        sources.append(f"本地候选 {base_count} 个")
    if history_count:
        sources.append(f"历史候选 {history_count} 个")
    if search_count:
        source_label = "路线附近搜索补充" if discovery_status == "route_context" else "城市搜索补充"
        sources.append(f"{source_label} {search_count} 个")
    elif search_status:
        sources.append(search_status)
    if not sources:
        sources.append("暂时没有找到稳妥候选；不会展示占位地点。")
    return "；".join(sources)


def normalize_completion_discovery_status(
    *,
    discovery_status: str | None,
    has_options: bool,
    used_search: bool,
) -> str:
    if discovery_status == "empty":
        return "empty"
    if used_search and discovery_status in {"route_context", "city_text"}:
        return discovery_status
    if not has_options:
        return "empty"
    return "local_only"


def rank_meal_repair_candidates(
    *,
    candidates: list[CandidateSpec],
    day_details: DayItinerary,
    target_block: DayTimeBlock,
    block_type: TimeBlockType,
    existing_names: set[str],
    used_names: set[str],
    day_signal: tuple[set[str], set[str]],
    trip_signal: tuple[set[str], set[str]],
    day_centroid: tuple[float, float] | None,
    trip_centroid: tuple[float, float] | None,
    style_preferences: StylePreferenceSignal | set[str] | None = None,
    preference_policy: PlannerPreferencePolicy | None = None,
) -> list[ScoredCandidate]:
    scored_candidates = rank_candidates_for_block(
        candidates=candidates,
        day_details=day_details,
        target_block=target_block,
        block_type=block_type,
        existing_names=existing_names,
        used_names=used_names,
        day_signal=day_signal,
        trip_signal=trip_signal,
        day_centroid=day_centroid,
        trip_centroid=trip_centroid,
        style_preferences=style_preferences,
        preference_policy=preference_policy,
    )
    previous_anchor = meal_previous_anchor(day=day_details, target_block=target_block)
    next_anchor = meal_next_anchor(day=day_details, target_block=target_block)
    return sorted(
        scored_candidates,
        key=cmp_to_key(
            lambda left, right: compare_meal_repair_candidates(
                left=left,
                right=right,
                previous_anchor=previous_anchor,
                next_anchor=next_anchor,
                block_type=block_type,
                style_preferences=style_preferences,
                preference_policy=preference_policy,
            )
        ),
    )


def ranked_candidates_to_candidates(
    ranked_candidates: list[ScoredCandidate],
    *,
    allow_zero_score: bool,
) -> list[CandidateSpec]:
    return [
        candidate
        for score, *_rest, candidate in ranked_candidates
        if score > 0 or allow_zero_score
    ]


def first_ranked_candidate(
    ranked_candidates: list[ScoredCandidate],
    *,
    allow_zero_score: bool,
) -> CandidateSpec | None:
    candidates = ranked_candidates_to_candidates(
        ranked_candidates,
        allow_zero_score=allow_zero_score,
    )
    return candidates[0] if candidates else None


def select_candidate_from_ranked_options(
    ranked_candidates: list[ScoredCandidate],
    selected_candidate: ItineraryCompletionOption | None,
    *,
    allow_zero_score: bool,
) -> CandidateSpec | None:
    if selected_candidate is None:
        return first_ranked_candidate(
            ranked_candidates,
            allow_zero_score=allow_zero_score,
        )
    for candidate in ranked_candidates_to_candidates(
        ranked_candidates,
        allow_zero_score=allow_zero_score,
    ):
        if (
            candidate.name == selected_candidate.name
            and candidate.type == selected_candidate.type
        ):
            return candidate
    return None


def supplement_candidates_from_options(
    candidates: list[CandidateSpec],
    options: list[ItineraryCompletionOption],
    *,
    city: str | None,
    target_day: int,
    target_block: TimeBlockType,
    poi_type: POIType | None = None,
) -> list[CandidateSpec]:
    by_key = {(candidate.name, candidate.type): candidate for candidate in candidates}
    for option in options:
        if option.suggested_day != target_day or option.suggested_block != target_block:
            continue
        if poi_type is not None and option.type != poi_type:
            continue
        key = (option.name, option.type)
        if key in by_key:
            continue
        candidate = build_candidate(
            name=option.name,
            poi_type=option.type,
            block_types=(target_block,),
            areas=(),
            themes=(),
            city=city,
        )
        if candidate.latitude is None or candidate.longitude is None:
            continue
        by_key[key] = candidate
    return list(by_key.values())


def resolve_meal_task_target(
    *,
    itinerary: ItineraryResponse,
    day: int | None,
    block_type: TimeBlockType | None,
) -> tuple[DayItinerary, DayTimeBlock] | None:
    candidate_blocks = (
        (block_type,)
        if block_type in {TimeBlockType.AFTERNOON, TimeBlockType.EVENING}
        else (TimeBlockType.AFTERNOON, TimeBlockType.EVENING)
    )
    for day_details in ordered_task_days(itinerary, day):
        for candidate_block_type in candidate_blocks:
            target_block = find_block(day_details, candidate_block_type)
            if target_block is not None and not block_has_restaurant(target_block):
                return day_details, target_block
    return None


def resolve_completion_candidate_task_target(
    *,
    itinerary: ItineraryResponse,
    task_id: str,
    day: int | None,
    block_type: TimeBlockType | None,
) -> tuple[DayItinerary, DayTimeBlock] | None:
    preferred_block = TimeBlockType.EVENING if task_id == "repair_evening_close" else block_type
    for day_details in ordered_task_days(itinerary, day):
        candidate_blocks = (
            (preferred_block,)
            if preferred_block is not None
            else tuple(signal.block_type for signal in build_day_fullness_signals(day_details) if signal.underfilled)
        )
        for candidate_block_type in candidate_blocks:
            target_block = find_block(day_details, candidate_block_type)
            if target_block is None:
                continue
            if task_id == "repair_evening_close" and candidate_block_type != TimeBlockType.EVENING:
                continue
            if build_block_fullness_signal(target_block).underfilled or task_id == "repair_evening_close":
                return day_details, target_block
    return None


def ordered_task_days(
    itinerary: ItineraryResponse,
    day: int | None,
) -> list[DayItinerary]:
    if day is not None:
        return [day_details for day_details in itinerary.days if day_details.day == day]
    return sorted(itinerary.days, key=lambda day_details: day_details.day)


def find_block(
    day: DayItinerary,
    block_type: TimeBlockType,
) -> DayTimeBlock | None:
    return next((block for block in day.blocks if block.block_type == block_type), None)


def restaurant_candidates_for_itinerary(
    itinerary: ItineraryResponse,
    scheduled_items: list[ScheduledPOI],
) -> list[CandidateSpec]:
    inferred_city = infer_itinerary_city(itinerary, scheduled_items)
    return [
        candidate
        for candidate in CITY_CANDIDATES.get(inferred_city or "", [])
        if candidate.type == POIType.RESTAURANT
        and candidate.latitude is not None
        and candidate.longitude is not None
    ]


def candidate_pool_for_task(
    *,
    itinerary: ItineraryResponse,
    scheduled_items: list[ScheduledPOI],
    task_id: str,
    target_block: DayTimeBlock,
) -> list[CandidateSpec]:
    inferred_city = infer_itinerary_city(itinerary, scheduled_items)
    candidates = [
        candidate
        for candidate in CITY_CANDIDATES.get(inferred_city or "", [])
        if candidate.latitude is not None
        and candidate.longitude is not None
        and target_block.block_type in candidate.block_types
    ]
    if task_id == "repair_evening_close":
        has_restaurant = block_has_restaurant(target_block)
        evening_candidates = [
            candidate
            for candidate in candidates
            if (
                candidate.type == POIType.RESTAURANT
                and not has_restaurant
            )
            or candidate.themes
            and bool(set(candidate.themes) & {"night", "waterfront", "street_food", "old_street"})
        ]
        return evening_candidates or candidates
    return candidates


def build_task_completion_option(
    *,
    candidate: CandidateSpec,
    day: DayItinerary,
    target_block: DayTimeBlock,
    candidate_pool: list[CandidateSpec],
    preference_policy: PlannerPreferencePolicy | None,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
) -> ItineraryCompletionOption:
    day_items = [item for block in day.blocks for item in block.items]
    scheduled_items = day_items
    day_signal = build_signal_profile(day_items)
    fullness_signal = build_block_fullness_signal(target_block)
    return ItineraryCompletionOption(
        name=candidate.name,
        type=candidate.type,
        suggested_day=day.day,
        suggested_block=target_block.block_type,
        reasoning_summary=build_reasoning_summary(
            day=day.day,
            block_type=target_block.block_type,
            candidate=candidate,
            day_signal=day_signal,
            fullness_signal=fullness_signal,
            sparse_day_rank=0,
            sparse_day_count=1,
            day_fullness_signals=build_day_fullness_signals(day),
            day_items=day_items,
            candidate_pool=candidate_pool,
            request_style_preferences=request_style_preferences,
            preference_policy=preference_policy,
        ),
        itinerary_relation_summary=build_itinerary_relation_summary(
            day=day.day,
            block_type=target_block.block_type,
            candidate=candidate,
            day_items=day_items,
        ),
        decision_evidence=build_completion_decision_evidence(
            block_type=target_block.block_type,
            candidate=candidate,
            day_items=day_items,
            candidate_pool=candidate_pool,
            day_details=day,
            target_block=target_block,
            existing_names={item.name for item in scheduled_items},
            used_names=set(),
            day_signal=day_signal,
            trip_signal=day_signal,
            day_centroid=build_centroid(day_items),
            trip_centroid=build_centroid(day_items),
            style_preferences=request_style_preferences,
            fullness_signal=fullness_signal,
            request_style_preferences=request_style_preferences,
            preference_policy=preference_policy,
        ),
    )


def ensure_task_style_preference(
    style_preferences: StylePreferenceSignal | set[str] | None,
    style_bucket: str,
) -> StylePreferenceSignal:
    style_signal = normalize_style_preference_signal(style_preferences)
    explicit = set(style_signal.explicit) if style_signal else set()
    inferred = set(style_signal.inferred) if style_signal else set()
    inferred.add(style_bucket)
    inferred -= explicit
    return StylePreferenceSignal(
        explicit=frozenset(explicit),
        inferred=frozenset(inferred),
    )


def source_label_for_completion_task(task_id: str) -> str:
    if task_id == "repair_evening_close":
        return "补全任务：夜间收口"
    return "补全任务：空档修复"


def complete_meal_rhythm(
    itinerary: ItineraryResponse,
    *,
    poi_discovery_provider: PoiDiscoveryProvider | None = None,
) -> ItineraryResponse:
    """Complete applicable lunch/dinner slots without moving existing stops."""

    updated = itinerary.model_copy(deep=True)
    provider = poi_discovery_provider or default_poi_discovery_provider()
    capability = provider.capability()
    candidates_evaluated = 0
    route_calls = 0
    successful_completions = 0

    if capability.poi_discovery_enabled:
        for day_number in sorted(day.day for day in updated.days):
            for role in (MealRole.LUNCH, MealRole.DINNER):
                current = assess_meal_rhythm(updated)
                slot = next(
                    slot
                    for day_summary in current.days
                    if day_summary.day == day_number
                    for slot in day_summary.slots
                    if slot.role == role
                )
                if slot.status != MealCoverageStatus.UNRESOLVED:
                    continue
                day = next(item for item in updated.days if item.day == day_number)
                result = insert_verified_meal(
                    itinerary=updated,
                    day=day,
                    role=role,
                    provider=provider,
                )
                updated = result.itinerary
                candidates_evaluated += result.candidates_evaluated
                route_calls += result.route_calls
                if result.inserted:
                    successful_completions += 1

    return updated.model_copy(
        update={
            "meal_rhythm": assess_meal_rhythm(
                updated,
                diagnostics=MealRhythmDiagnostics(
                    poi_candidates_evaluated=candidates_evaluated,
                    route_calls=route_calls,
                    successful_completions=successful_completions,
                ),
            )
        }
    )


@dataclass(frozen=True, slots=True)
class MealInsertionResult:
    itinerary: ItineraryResponse
    inserted: bool
    candidates_evaluated: int
    route_calls: int


@dataclass(frozen=True, slots=True)
class MealInsertionPlan:
    candidate: PoiDiscoveryCandidate
    start_time: time
    end_time: time
    previous_anchor: ScheduledPOI | HotelStay
    next_anchor: ScheduledPOI | HotelStay
    following_item: ScheduledPOI | None
    inbound: MealAdjacentRouteEvidence
    outbound: MealAdjacentRouteEvidence


def insert_verified_meal(
    *,
    itinerary: ItineraryResponse,
    day: DayItinerary,
    role: MealRole,
    provider: PoiDiscoveryProvider,
) -> MealInsertionResult:
    target_block_type = (
        TimeBlockType.AFTERNOON if role == MealRole.LUNCH else TimeBlockType.EVENING
    )
    target_block = next(
        (block for block in day.blocks if block.block_type == target_block_type),
        None,
    )
    if target_block is None:
        return MealInsertionResult(itinerary, False, 0, 0)
    existing_items = sorted(
        (item for block in day.blocks for item in block.items),
        key=lambda item: (item.start_time, item.end_time, item.name),
    )
    trip_items = [
        item
        for itinerary_day in itinerary.days
        for block in itinerary_day.blocks
        for item in block.items
    ]
    existing_provider_ids = {
        item.verified_place.provider_place_id
        for item in trip_items
        if item.verified_place is not None
    }
    existing_names = {item.name.strip() for item in trip_items}
    temporal_gaps = meal_temporal_gaps(day=day, role=role, items=existing_items)
    plans: list[MealInsertionPlan] = []
    candidates_evaluated = 0
    route_calls = 0
    seen_candidate_contexts: set[tuple[str, str, str, int, int]] = set()

    for previous_anchor, next_anchor, following_item, gap_start, gap_end in temporal_gaps:
        try:
            places = provider.search_around(
                keyword="午餐" if role == MealRole.LUNCH else "晚餐",
                city=previous_anchor.city or day.hotel.city or "",
                latitude=previous_anchor.latitude,
                longitude=previous_anchor.longitude,
                radius=COMPLETION_PREVIEW_AROUND_SEARCH_RADIUS_METERS,
                offset=min(COMPLETION_PREVIEW_SEARCH_OFFSET, 6),
            )
        except PoiDiscoveryUnavailable:
            continue
        for candidate in places[:6]:
            candidates_evaluated += 1
            provider_id = (candidate.provider_place_id or "").strip()
            candidate_name = (candidate.name or "").strip()
            if (
                not provider_id
                or not candidate_name
                or candidate.latitude is None
                or candidate.longitude is None
                or provider_id in existing_provider_ids
                or candidate_name in existing_names
                or not is_meal_capable_category(
                    candidate.type or "",
                    candidate.typecode,
                    name=candidate_name,
                )
            ):
                continue
            context_key = (
                provider_id,
                anchor_place_id(previous_anchor) or previous_anchor.name,
                anchor_place_id(next_anchor) or next_anchor.name,
                gap_start,
                gap_end,
            )
            if context_key in seen_candidate_contexts:
                continue
            seen_candidate_contexts.add(context_key)
            inbound = verified_meal_leg(
                from_anchor=previous_anchor,
                to_name=candidate_name,
                to_latitude=float(candidate.latitude),
                to_longitude=float(candidate.longitude),
            )
            route_calls += 1
            outbound = verified_meal_leg(
                from_anchor=MealCoordinateAnchor(
                    name=candidate_name,
                    city=previous_anchor.city or day.hotel.city,
                    latitude=float(candidate.latitude),
                    longitude=float(candidate.longitude),
                ),
                to_name=next_anchor.name,
                to_latitude=next_anchor.latitude,
                to_longitude=next_anchor.longitude,
            )
            route_calls += 1
            if inbound is None or outbound is None:
                continue
            start_minute = max(
                gap_start,
                minutes(meal_window(role).start),
                minutes(target_block.start_time),
                gap_start + round_up_route_minutes(inbound.duration_s),
            )
            end_minute = start_minute + MEAL_RHYTHM_POLICY.preferred_duration_minutes
            outbound_deadline = (
                minutes(following_item.start_time)
                if following_item is not None
                else minutes(
                    day.availability_summary.effective_end
                    or max(
                        (block.end_time for block in day.blocks),
                        default=time(21, 0),
                    )
                )
            )
            if (
                end_minute > gap_end
                or end_minute > minutes(target_block.end_time)
                or end_minute + round_up_route_minutes(outbound.duration_s) > outbound_deadline
            ):
                continue
            plans.append(
                MealInsertionPlan(
                    candidate=candidate,
                    start_time=time_from_minutes(start_minute),
                    end_time=time_from_minutes(end_minute),
                    previous_anchor=previous_anchor,
                    next_anchor=next_anchor,
                    following_item=following_item,
                    inbound=inbound,
                    outbound=outbound,
                )
            )

    if not plans:
        return MealInsertionResult(itinerary, False, candidates_evaluated, route_calls)

    preferred_start = minutes(meal_window(role).start) + 45
    selected = min(
        plans,
        key=lambda plan: (
            abs(minutes(plan.start_time) - preferred_start),
            plan.inbound.duration_s + plan.outbound.duration_s,
            plan.inbound.distance_m + plan.outbound.distance_m,
            plan.candidate.provider_place_id or "",
        ),
    )
    updated_itinerary = append_meal_item(
        itinerary=itinerary,
        day=day,
        role=role,
        plan=selected,
    )
    return MealInsertionResult(updated_itinerary, True, candidates_evaluated, route_calls)


@dataclass(frozen=True, slots=True)
class MealCoordinateAnchor:
    name: str
    city: str | None
    latitude: float
    longitude: float


def meal_temporal_gaps(
    *,
    day: DayItinerary,
    role: MealRole,
    items: list[ScheduledPOI],
) -> list[tuple[ScheduledPOI | HotelStay, ScheduledPOI | HotelStay, ScheduledPOI | None, int, int]]:
    active_start = day.availability_summary.effective_start or min(
        (block.start_time for block in day.blocks if block.start_time < block.end_time),
        default=time(9, 0),
    )
    active_end = day.availability_summary.effective_end or max(
        (block.end_time for block in day.blocks if block.start_time < block.end_time),
        default=time(21, 0),
    )
    window = meal_window(role)
    gaps = []
    previous: ScheduledPOI | HotelStay = day.hotel
    previous_end = minutes(active_start)
    for item in items:
        gap_start = max(previous_end, minutes(window.start))
        gap_end = min(minutes(item.start_time), minutes(window.end), minutes(active_end))
        if gap_end - gap_start >= MEAL_RHYTHM_POLICY.preferred_duration_minutes:
            gaps.append((previous, item, item, gap_start, gap_end))
        previous = item
        previous_end = minutes(item.end_time)
    gap_start = max(previous_end, minutes(window.start), minutes(active_start))
    gap_end = min(minutes(window.end), minutes(active_end))
    if gap_end - gap_start >= MEAL_RHYTHM_POLICY.preferred_duration_minutes:
        gaps.append((previous, day.hotel, None, gap_start, gap_end))
    return gaps


def verified_meal_leg(
    *,
    from_anchor: ScheduledPOI | HotelStay | MealCoordinateAnchor,
    to_name: str,
    to_latitude: float,
    to_longitude: float,
) -> MealAdjacentRouteEvidence | None:
    try:
        route = get_walking_route(
            origin_lat=from_anchor.latitude,
            origin_lng=from_anchor.longitude,
            dest_lat=to_latitude,
            dest_lng=to_longitude,
        )
    except RoutePlanningError:
        return None
    distance_m = int(route.get("distance_m") or 0)
    duration_s = int(route.get("duration_s") or 0)
    if distance_m <= 0 or duration_s <= 0:
        return None
    return MealAdjacentRouteEvidence(
        from_name=from_anchor.name,
        to_name=to_name,
        from_place_id=(
            from_anchor.canonical_place_id or from_anchor.stable_id
            if isinstance(from_anchor, ScheduledPOI)
            else None
        ),
        distance_m=distance_m,
        duration_s=duration_s,
    )


def append_meal_item(
    *,
    itinerary: ItineraryResponse,
    day: DayItinerary,
    role: MealRole,
    plan: MealInsertionPlan,
) -> ItineraryResponse:
    candidate = plan.candidate
    provider_id = candidate.provider_place_id or ""
    verified_place = VerifiedPlaceRef(
        stable_id=f"amap:{provider_id}",
        original_name=candidate.name or "",
        canonical_name=candidate.name or "",
        provider="amap",
        provider_place_id=provider_id,
        latitude=float(candidate.latitude),
        longitude=float(candidate.longitude),
        category=candidate.type,
    )
    inbound = plan.inbound.model_copy(update={"to_place_id": provider_id})
    outbound = plan.outbound.model_copy(
        update={
            "from_place_id": provider_id,
            "to_place_id": anchor_place_id(plan.next_anchor),
        }
    )
    item = ScheduledPOI(
        stable_id=verified_place.stable_id,
        name=verified_place.canonical_name,
        type=POIType.RESTAURANT,
        city=plan.previous_anchor.city or day.hotel.city,
        latitude=verified_place.latitude,
        longitude=verified_place.longitude,
        duration_minutes=MEAL_RHYTHM_POLICY.preferred_duration_minutes,
        day=day.day,
        start_time=plan.start_time,
        end_time=plan.end_time,
        is_fixed=False,
        placement_reason=(
            f"前后路线都已确认，并为后面的安排留出时间；"
            f"系统把这里顺路安排为{meal_role_label(role)}。"
        ),
        source_type=ScheduledPOISourceType.AUTO_SEEDED_MEAL,
        source_label="系统补充",
        source_reason=f"系统为这一天补上的{meal_role_label(role)}。",
        travel_from_name=plan.previous_anchor.name,
        travel_distance_m=plan.inbound.distance_m,
        travel_duration_s=plan.inbound.duration_s,
        travel_calculation_status="confirmed",
        candidate_id=verified_place.stable_id,
        canonical_place_id=provider_id,
        verified_place=verified_place,
        travel_from_place_id=anchor_place_id(plan.previous_anchor),
        travel_to_place_id=provider_id,
        travel_provider="amap",
        travel_data_status="confirmed",
        candidate_provenance={
            "purpose": "meal_rhythm",
            "meal_role": role.value,
            "provider_category": candidate.type,
            "provider_typecode": candidate.typecode,
        },
        meal_role=role,
        meal_route_evidence=MealRouteEvidence(
            inbound=inbound,
            outbound=outbound,
        ),
    )
    target_block_type = (
        TimeBlockType.AFTERNOON if role == MealRole.LUNCH else TimeBlockType.EVENING
    )
    updated_following = (
        plan.following_item.model_copy(
            update={
                "travel_from_name": item.name,
                "travel_distance_m": outbound.distance_m,
                "travel_duration_s": outbound.duration_s,
                "travel_calculation_status": "confirmed",
                "travel_from_place_id": provider_id,
                "travel_to_place_id": (
                    plan.following_item.canonical_place_id
                    or plan.following_item.stable_id
                ),
                "travel_provider": "amap",
                "travel_data_status": "confirmed",
            }
        )
        if plan.following_item is not None
        else None
    )
    updated_blocks: list[DayTimeBlock] = []
    for block in day.blocks:
        block_items = [
            updated_following if scheduled is plan.following_item and updated_following is not None else scheduled
            for scheduled in block.items
        ]
        if block.block_type == target_block_type:
            block_items = [*block_items, item]
        updated_blocks.append(
            block.model_copy(
                update={
                    "items": sorted(
                        block_items,
                        key=lambda scheduled: (
                            scheduled.start_time,
                            scheduled.end_time,
                            scheduled.name,
                        ),
                    )
                }
            )
        )
    updated_day = day.model_copy(update={"blocks": updated_blocks})
    return itinerary.model_copy(
        update={
            "days": [
                updated_day if candidate.day == day.day else candidate
                for candidate in itinerary.days
            ]
        }
    )


def anchor_place_id(anchor: ScheduledPOI | HotelStay | MealCoordinateAnchor) -> str | None:
    if isinstance(anchor, ScheduledPOI):
        return anchor.canonical_place_id or anchor.stable_id
    return None


def round_up_route_minutes(duration_s: int) -> int:
    return max(1, (duration_s + 59) // 60)


def time_from_minutes(value: int) -> time:
    bounded = max(0, min(value, 23 * 60 + 59))
    return time(bounded // 60, bounded % 60)


def repair_missing_meal_slots(
    itinerary: ItineraryResponse,
    used_names: set[str] | None = None,
    preference_policy: PlannerPreferencePolicy | None = None,
    request_style_preferences: StylePreferenceSignal | set[str] | None = None,
) -> ItineraryResponse:
    """
    Repair lunch/dinner gaps after generic sparse-block auto-fill.

    This is intentionally deterministic and local: it scans each day's afternoon
    and evening blocks, then inserts the best restaurant candidate only when the
    block has no meal anchor and has enough capacity.
    """
    updated_itinerary = itinerary.model_copy(deep=True)
    inserted_names = set(used_names or set())
    request_style_signal = normalize_style_preference_signal(request_style_preferences)

    scheduled_items = flatten_scheduled_items(updated_itinerary.days)
    existing_names = {item.name for item in scheduled_items}
    inferred_city = infer_itinerary_city(updated_itinerary, scheduled_items)
    restaurant_candidates = [
        candidate
        for candidate in CITY_CANDIDATES.get(inferred_city or "", [])
        if candidate.type == POIType.RESTAURANT
        and candidate.latitude is not None
        and candidate.longitude is not None
    ]
    if not restaurant_candidates:
        return updated_itinerary

    for day in updated_itinerary.days:
        for block_type in (TimeBlockType.AFTERNOON, TimeBlockType.EVENING):
            target_block = next(
                (block for block in day.blocks if block.block_type == block_type),
                None,
            )
            if target_block is None or block_has_restaurant(target_block):
                continue

            scheduled_items = flatten_scheduled_items(updated_itinerary.days)
            day_items = [item for block in day.blocks for item in block.items]
            day_signal = build_signal_profile(day_items)
            trip_signal = build_signal_profile(scheduled_items)
            day_centroid = build_centroid(day_items)
            trip_centroid = build_centroid(scheduled_items)
            candidate = choose_meal_repair_candidate(
                candidates=restaurant_candidates,
                day_details=day,
                target_block=target_block,
                block_type=block_type,
                existing_names=existing_names,
                used_names=inserted_names,
                day_signal=day_signal,
                trip_signal=trip_signal,
                day_centroid=day_centroid,
                trip_centroid=trip_centroid,
                style_preferences=request_style_signal,
                preference_policy=preference_policy,
            )
            if candidate is None:
                continue

            fullness_signal = build_block_fullness_signal(target_block)
            option = ItineraryCompletionOption(
                name=candidate.name,
                type=candidate.type,
                suggested_day=day.day,
                suggested_block=block_type,
                reasoning_summary=build_reasoning_summary(
                    day=day.day,
                    block_type=block_type,
                    candidate=candidate,
                    day_signal=day_signal,
                    fullness_signal=fullness_signal,
                    sparse_day_rank=0,
                    sparse_day_count=1,
                    day_fullness_signals=build_day_fullness_signals(day),
                    day_items=day_items,
                    candidate_pool=restaurant_candidates,
                    request_style_preferences=request_style_signal,
                    preference_policy=preference_policy,
                ),
                itinerary_relation_summary=build_itinerary_relation_summary(
                    day=day.day,
                    block_type=block_type,
                    candidate=candidate,
                    day_items=day_items,
                ),
                decision_evidence=build_completion_decision_evidence(
                    block_type=block_type,
                    candidate=candidate,
                    day_items=day_items,
                    candidate_pool=restaurant_candidates,
                    day_details=day,
                    target_block=target_block,
                    existing_names=existing_names,
                    used_names=inserted_names,
                    day_signal=day_signal,
                    trip_signal=trip_signal,
                    day_centroid=day_centroid,
                    trip_centroid=trip_centroid,
                    style_preferences=request_style_signal,
                    fullness_signal=fullness_signal,
                    request_style_preferences=request_style_signal,
                    preference_policy=preference_policy,
                ),
            )
            meal_item = build_meal_repair_item(
                itinerary=updated_itinerary,
                day=day,
                target_block=target_block,
                candidate=candidate,
                option=option,
                request_style_preferences=request_style_signal,
                preference_policy=preference_policy,
            )
            if meal_item is None:
                continue

            meal_item.source_label = "系统餐食修复"
            meal_item.source_reason = append_sentence_prefix(
                meal_item.source_reason,
                "系统修复了缺失的午餐或晚餐锚点，让这一天的节奏更接近真实出行。",
            )
            target_block.items.append(meal_item)
            target_block.items.sort(key=lambda item: (item.start_time, item.end_time, item.name))
            existing_names.add(candidate.name)
            inserted_names.add(candidate.name)

    return updated_itinerary


def choose_meal_repair_candidate(
    *,
    candidates: list[CandidateSpec],
    day_details: DayItinerary,
    target_block: DayTimeBlock,
    block_type: TimeBlockType,
    existing_names: set[str],
    used_names: set[str],
    day_signal: tuple[set[str], set[str]],
    trip_signal: tuple[set[str], set[str]],
    day_centroid: tuple[float, float] | None,
    trip_centroid: tuple[float, float] | None,
    style_preferences: StylePreferenceSignal | set[str] | None = None,
    preference_policy: PlannerPreferencePolicy | None = None,
) -> CandidateSpec | None:
    scored_candidates = rank_candidates_for_block(
        candidates=candidates,
        day_details=day_details,
        target_block=target_block,
        block_type=block_type,
        existing_names=existing_names,
        used_names=used_names,
        day_signal=day_signal,
        trip_signal=trip_signal,
        day_centroid=day_centroid,
        trip_centroid=trip_centroid,
        style_preferences=style_preferences,
        preference_policy=preference_policy,
    )
    if not scored_candidates:
        return None

    previous_anchor = meal_previous_anchor(day=day_details, target_block=target_block)
    next_anchor = meal_next_anchor(day=day_details, target_block=target_block)

    return sorted(
        scored_candidates,
        key=cmp_to_key(
            lambda left, right: compare_meal_repair_candidates(
                left=left,
                right=right,
                previous_anchor=previous_anchor,
                next_anchor=next_anchor,
                block_type=block_type,
                style_preferences=style_preferences,
                preference_policy=preference_policy,
            )
        ),
    )[0][11]


def compare_meal_repair_candidates(
    *,
    left: ScoredCandidate,
    right: ScoredCandidate,
    previous_anchor: ScheduledPOI | HotelStay,
    next_anchor: ScheduledPOI | HotelStay,
    block_type: TimeBlockType,
    style_preferences: StylePreferenceSignal | set[str] | None,
    preference_policy: PlannerPreferencePolicy | None,
) -> int:
    left_candidate = left[11]
    right_candidate = right[11]
    left_route = estimate_local_detour_metrics(
        previous_anchor=previous_anchor,
        next_anchor=next_anchor,
        candidate_lat=left_candidate.latitude,
        candidate_lng=left_candidate.longitude,
    )
    right_route = estimate_local_detour_metrics(
        previous_anchor=previous_anchor,
        next_anchor=next_anchor,
        candidate_lat=right_candidate.latitude,
        candidate_lng=right_candidate.longitude,
    )
    preference_ranking = compare_meal_repair_preference_alignment(
        left=left_candidate,
        right=right_candidate,
        block_type=block_type,
        style_preferences=style_preferences,
        preference_policy=preference_policy,
    )
    if preference_ranking != 0 and meal_repair_routes_are_close(left_route, right_route):
        return preference_ranking

    route_ranking = compare_route_ranking(
        left_ratio=left_route[0],
        left_delta=left_route[1],
        left_evidence_tier=left_route[2],
        left_source_tier=left_route[3],
        left_side_leg_tier=left_route[4],
        left_directionality_tier=left_route[5],
        right_ratio=right_route[0],
        right_delta=right_route[1],
        right_evidence_tier=right_route[2],
        right_source_tier=right_route[3],
        right_side_leg_tier=right_route[4],
        right_directionality_tier=right_route[5],
    )
    if route_ranking != 0:
        return route_ranking
    if preference_ranking != 0:
        return preference_ranking
    return compare_scored_candidates(left, right)


def compare_meal_repair_preference_alignment(
    *,
    left: CandidateSpec,
    right: CandidateSpec,
    block_type: TimeBlockType,
    style_preferences: StylePreferenceSignal | set[str] | None,
    preference_policy: PlannerPreferencePolicy | None,
) -> int:
    left_key = meal_repair_preference_alignment_key(
        candidate=left,
        block_type=block_type,
        style_preferences=style_preferences,
        preference_policy=preference_policy,
    )
    right_key = meal_repair_preference_alignment_key(
        candidate=right,
        block_type=block_type,
        style_preferences=style_preferences,
        preference_policy=preference_policy,
    )
    if left_key == right_key:
        return 0
    return -1 if left_key < right_key else 1


def meal_repair_preference_alignment_key(
    *,
    candidate: CandidateSpec,
    block_type: TimeBlockType,
    style_preferences: StylePreferenceSignal | set[str] | None,
    preference_policy: PlannerPreferencePolicy | None,
) -> tuple[int, int, int, int, int]:
    style_signal = normalize_style_preference_signal(style_preferences)
    candidate_themes = set(candidate.themes)
    visit_style = infer_poi_profile(candidate.name, candidate.type).visit_style

    explicit_style_rank = 2
    if style_signal:
        if style_signal.source_for(STYLE_BUCKET_FOOD_STOP) == "explicit":
            explicit_style_rank = min(
                explicit_style_rank,
                0
                if "street_food" in candidate_themes
                or visit_style == POIVisitStyle.FOOD_DISTRICT
                else 1,
            )
        if style_signal.source_for(STYLE_BUCKET_NIGHT_VIEW) == "explicit" and block_type == TimeBlockType.EVENING:
            explicit_style_rank = min(
                explicit_style_rank,
                0 if candidate_themes & {"night", "waterfront"} else 1,
            )
        if style_signal.source_for(STYLE_BUCKET_OLD_STREET) == "explicit":
            explicit_style_rank = min(
                explicit_style_rank,
                0
                if candidate_themes & {"old_street", "design"}
                or visit_style in {POIVisitStyle.OLD_STREET, POIVisitStyle.LEISURE_DISTRICT}
                else 1,
            )

    dining_rank = 1
    if preference_policy is not None and preference_policy.dining_priority == "high":
        dining_rank = 0 if candidate_themes & {"street_food", "night", "old_street"} else 1

    relaxed_rank = 1
    if preference_policy is not None and preference_policy.pace == "relaxed":
        relaxed_rank = 0 if candidate_themes & {"old_street", "design", "waterfront"} else 1

    night_rank = 1
    if block_type == TimeBlockType.EVENING:
        night_rank = 0 if candidate_themes & {"night", "waterfront"} else 1

    return (
        explicit_style_rank,
        dining_rank,
        relaxed_rank,
        night_rank,
        candidate_preference_alignment_key(
            candidate=candidate,
            block_type=block_type,
            style_preferences=style_preferences,
            preference_policy=preference_policy,
        )[2],
    )


def meal_repair_routes_are_close(
    left_route: tuple[float, float, int, int, int, int],
    right_route: tuple[float, float, int, int, int, int],
) -> bool:
    left_ratio, left_delta = left_route[0], left_route[1]
    right_ratio, right_delta = right_route[0], right_route[1]
    if not (isfinite(left_ratio) and isfinite(right_ratio) and isfinite(left_delta) and isfinite(right_delta)):
        return False
    return (
        abs(left_delta - right_delta) <= MEAL_REPAIR_PREFERENCE_ROUTE_CLOSE_DELTA_SECONDS
        or abs(left_ratio - right_ratio) <= MEAL_REPAIR_PREFERENCE_ROUTE_CLOSE_RATIO
    )


def build_meal_repair_item(
    *,
    itinerary: ItineraryResponse,
    day: DayItinerary,
    target_block: DayTimeBlock,
    candidate: CandidateSpec,
    option: ItineraryCompletionOption,
    request_style_preferences: StylePreferenceSignal | set[str] | None = None,
    preference_policy: PlannerPreferencePolicy | None = None,
) -> ScheduledPOI | None:
    inferred_city = infer_itinerary_city(itinerary, flatten_scheduled_items(itinerary.days))
    latitude, longitude = resolve_candidate_coordinates(
        name=option.name,
        city=inferred_city,
    )
    if latitude is None or longitude is None:
        return None

    profile = infer_poi_profile(option.name, option.type)
    insertion_plan = plan_meal_repair_insertion(
        day=day,
        target_block=target_block,
        duration_minutes=profile.typical_duration_minutes,
        profile_intensity=profile.intensity,
        candidate_name=option.name,
        candidate_lat=latitude,
        candidate_lng=longitude,
        request_style_preferences=request_style_preferences,
        preference_policy=preference_policy,
    )
    if insertion_plan is None:
        return None

    travel_distance_m, travel_duration_s = estimate_travel_metadata(
        origin_lat=insertion_plan["travel_anchor"].latitude,
        origin_lng=insertion_plan["travel_anchor"].longitude,
        dest_lat=latitude,
        dest_lng=longitude,
    )

    return ScheduledPOI(
        name=option.name,
        type=option.type,
        city=inferred_city,
        latitude=latitude,
        longitude=longitude,
        duration_minutes=profile.typical_duration_minutes,
        day=day.day,
        start_time=insertion_plan["start_time"],
        end_time=insertion_plan["end_time"],
        is_fixed=False,
        placement_reason=insertion_plan["placement_reason"],
        source_type=ScheduledPOISourceType.AUTO_FILLED,
        source_label="系统餐食修复",
        source_reason=build_autofill_source_reason(option),
        travel_from_name=insertion_plan["travel_anchor"].name,
        travel_distance_m=travel_distance_m,
        travel_duration_s=travel_duration_s,
    )


def plan_meal_repair_insertion(
    *,
    day: DayItinerary,
    target_block: DayTimeBlock,
    duration_minutes: int,
    profile_intensity: str,
    candidate_name: str,
    candidate_lat: float,
    candidate_lng: float,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
    preference_policy: PlannerPreferencePolicy | None,
) -> dict[str, time | ScheduledPOI | HotelStay | str] | None:
    boundary_buffer = effective_buffer_minutes(
        insertion_kind="boundary",
        block_type=target_block.block_type,
        poi_type=POIType.RESTAURANT,
        profile_intensity=profile_intensity,
    )
    ordered_items = sorted(target_block.items, key=lambda item: (item.start_time, item.end_time, item.name))
    previous_anchor = meal_previous_anchor(day=day, target_block=target_block)

    if not ordered_items:
        if minutes_between_times(target_block.start_time, target_block.end_time) < duration_minutes:
            return None
        end_time = add_minutes_to_time(target_block.start_time, duration_minutes)
        next_anchor = meal_next_anchor(day=day, target_block=target_block)
        return {
            "start_time": target_block.start_time,
            "end_time": end_time,
            "travel_anchor": previous_anchor,
            "placement_reason": build_meal_repair_placement_reason(
                block_type=target_block.block_type,
                candidate_name=candidate_name,
                previous_anchor=previous_anchor,
                next_anchor=next_anchor,
                candidate_lat=candidate_lat,
                candidate_lng=candidate_lng,
                request_style_preferences=request_style_preferences,
                preference_policy=preference_policy,
            ),
        }

    first_item = ordered_items[0]
    before_gap = minutes_between_times(target_block.start_time, first_item.start_time)
    if before_gap >= duration_minutes + boundary_buffer:
        end_time = add_minutes_to_time(first_item.start_time, -boundary_buffer)
        start_time = add_minutes_to_time(end_time, -duration_minutes)
        return {
            "start_time": start_time,
            "end_time": end_time,
            "travel_anchor": previous_anchor,
            "placement_reason": build_meal_repair_placement_reason(
                block_type=target_block.block_type,
                candidate_name=candidate_name,
                previous_anchor=previous_anchor,
                next_anchor=first_item,
                candidate_lat=candidate_lat,
                candidate_lng=candidate_lng,
                request_style_preferences=request_style_preferences,
                preference_policy=preference_policy,
            ),
        }

    last_item = ordered_items[-1]
    after_gap = minutes_between_times(last_item.end_time, target_block.end_time)
    if after_gap >= duration_minutes + boundary_buffer:
        start_time = add_minutes_to_time(last_item.end_time, boundary_buffer)
        next_anchor = meal_next_anchor(day=day, target_block=target_block)
        return {
            "start_time": start_time,
            "end_time": add_minutes_to_time(start_time, duration_minutes),
            "travel_anchor": last_item,
            "placement_reason": build_meal_repair_placement_reason(
                block_type=target_block.block_type,
                candidate_name=candidate_name,
                previous_anchor=last_item,
                next_anchor=next_anchor,
                candidate_lat=candidate_lat,
                candidate_lng=candidate_lng,
                request_style_preferences=request_style_preferences,
                preference_policy=preference_policy,
            ),
        }

    return None


def meal_previous_anchor(
    *,
    day: DayItinerary,
    target_block: DayTimeBlock,
) -> ScheduledPOI | HotelStay:
    previous_items = [
        item
        for block in day.blocks
        if block.start_time < target_block.start_time
        for item in block.items
    ]
    if previous_items:
        return max(previous_items, key=lambda item: (item.end_time, item.start_time, item.name))
    return day.hotel


def meal_next_anchor(
    *,
    day: DayItinerary,
    target_block: DayTimeBlock,
) -> ScheduledPOI | HotelStay:
    same_block_items = [
        item
        for item in target_block.items
        if item.type != POIType.RESTAURANT
    ]
    if same_block_items:
        return min(same_block_items, key=lambda item: (item.start_time, item.end_time, item.name))
    return find_next_autofill_anchor(day=day, target_block=target_block)


def build_meal_repair_placement_reason(
    *,
    block_type: TimeBlockType,
    candidate_name: str,
    previous_anchor: ScheduledPOI | HotelStay,
    next_anchor: ScheduledPOI | HotelStay,
    candidate_lat: float,
    candidate_lng: float,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
    preference_policy: PlannerPreferencePolicy | None,
) -> str:
    if block_type == TimeBlockType.AFTERNOON:
        meal_label = "午餐"
    else:
        meal_label = "晚餐"
    route_phrase = build_meal_repair_route_phrase(
        previous_anchor=previous_anchor,
        next_anchor=next_anchor,
        candidate_lat=candidate_lat,
        candidate_lng=candidate_lng,
    )
    preference_phrase = build_request_preference_phrase(
        candidate=CandidateSpec(
            name=candidate_name,
            type=POIType.RESTAURANT,
            block_types=(block_type,),
            areas=(),
            themes=(),
            duration_minutes=60,
            profile_intensity="medium",
            latitude=candidate_lat,
            longitude=candidate_lng,
        ),
        block_type=block_type,
        candidate_themes=set(),
        visit_style=infer_poi_profile(candidate_name, POIType.RESTAURANT).visit_style,
        request_style_preferences=request_style_preferences,
        preference_policy=preference_policy,
    )
    preference_sentence = f" 同时也匹配：{preference_phrase}。" if preference_phrase else ""
    return (
        f"餐食空档修复：把 {candidate_name} 作为{meal_label}锚点插入 "
        f"{previous_anchor.name} 和 {next_anchor.name} 之间{route_phrase}，"
        f"让吃饭服务于路线节奏，而不是临时塞入的填充项。{preference_sentence}"
    )


def build_meal_repair_route_phrase(
    *,
    previous_anchor: ScheduledPOI | HotelStay,
    next_anchor: ScheduledPOI | HotelStay,
    candidate_lat: float,
    candidate_lng: float,
) -> str:
    inbound_minutes = estimate_anchor_to_coordinate_minutes(
        anchor=previous_anchor,
        dest_lat=candidate_lat,
        dest_lng=candidate_lng,
    )
    outbound_minutes = estimate_coordinate_to_anchor_minutes(
        origin_lat=candidate_lat,
        origin_lng=candidate_lng,
        anchor=next_anchor,
    )
    if inbound_minutes is None and outbound_minutes is None:
        return ""
    if inbound_minutes is not None and outbound_minutes is not None:
        return f"，距上一站约 {inbound_minutes} 分钟，去下一站约 {outbound_minutes} 分钟"
    if inbound_minutes is not None:
        return f"，距上一站约 {inbound_minutes} 分钟"
    return f"，去下一站约 {outbound_minutes} 分钟"


def estimate_anchor_to_coordinate_minutes(
    *,
    anchor: ScheduledPOI | HotelStay,
    dest_lat: float,
    dest_lng: float,
) -> int | None:
    _distance_m, duration_s = estimate_travel_metadata(
        origin_lat=anchor.latitude,
        origin_lng=anchor.longitude,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
    )
    if duration_s is None:
        return None
    return max(1, round(duration_s / 60))


def estimate_coordinate_to_anchor_minutes(
    *,
    origin_lat: float,
    origin_lng: float,
    anchor: ScheduledPOI | HotelStay,
) -> int | None:
    _distance_m, duration_s = estimate_travel_metadata(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=anchor.latitude,
        dest_lng=anchor.longitude,
    )
    if duration_s is None:
        return None
    return max(1, round(duration_s / 60))


def block_has_restaurant(block: DayTimeBlock) -> bool:
    return any(item.type == POIType.RESTAURANT for item in block.items)


def append_sentence_prefix(existing_reason: str | None, prefix: str) -> str:
    if existing_reason and existing_reason.startswith(prefix):
        return existing_reason
    if existing_reason:
        return f"{prefix} {existing_reason}"
    return prefix


def prioritized_autofill_options(
    recommendation: ItineraryCompletionRecommendation,
) -> list[ItineraryCompletionOption]:
    options_by_day: dict[int, list[ItineraryCompletionOption]] = {}
    ordered_days: list[int] = []

    for option in recommendation.options:
        if option.suggested_day not in options_by_day:
            options_by_day[option.suggested_day] = []
        options_by_day[option.suggested_day].append(option)

    for sparse_day in recommendation.sparse_days:
        if sparse_day.day in options_by_day and sparse_day.day not in ordered_days:
            ordered_days.append(sparse_day.day)

    for option in recommendation.options:
        if option.suggested_day not in ordered_days:
            ordered_days.append(option.suggested_day)

    prioritized: list[ItineraryCompletionOption] = []
    if not ordered_days:
        return prioritized

    thinnest_day = ordered_days[0]
    early_slots = min(
        THINNEST_DAY_EARLY_AUTOFILL_SLOTS,
        len(options_by_day.get(thinnest_day, [])),
    )
    for _ in range(early_slots):
        prioritized.append(options_by_day[thinnest_day].pop(0))

    for day in ordered_days[1:]:
        day_options = options_by_day.get(day, [])
        if day_options:
            prioritized.append(day_options.pop(0))

    for day in ordered_days:
        prioritized.extend(options_by_day.get(day, []))

    return prioritized


def summarize_sparse_days(
    days: list[DayItinerary],
    preference_policy: PlannerPreferencePolicy | None = None,
) -> list[SparseDaySummary]:
    summaries_with_priority: list[tuple[tuple[int, int, int, int, int], SparseDaySummary]] = []
    relaxed = preference_policy is not None and preference_policy.pace == "relaxed"
    packed = preference_policy is not None and preference_policy.pace == "packed"
    for day in days:
        fullness_signals = build_day_fullness_signals(day)
        meaningful_blocks = {
            signal.block_type for signal in fullness_signals if signal.meaningful
        }
        occupied_block_count = sum(1 for signal in fullness_signals if signal.occupied_minutes > 0)
        occupied_total_minutes = sum(signal.occupied_minutes for signal in fullness_signals)
        complete_shape_minutes_threshold = sum(
            meaningful_block_minutes_threshold(block.block_type)
            for block in day.blocks
        )
        has_meaningful_daytime_shape = {
            TimeBlockType.MORNING,
            TimeBlockType.AFTERNOON,
        }.issubset(meaningful_blocks)
        has_complete_spread_shape = (
            len(day.blocks) >= 3
            and occupied_block_count == len(day.blocks)
            and occupied_total_minutes >= complete_shape_minutes_threshold
        )
        item_count = sum(len(block.items) for block in day.blocks)
        missing_blocks = [block.block_type for block in day.blocks if not block.items]
        if has_complete_spread_shape:
            is_sparse = False
        elif packed:
            is_sparse = len(meaningful_blocks) < 3
        elif relaxed:
            is_sparse = not has_meaningful_daytime_shape and len(meaningful_blocks) < 2
        else:
            is_sparse = not has_meaningful_daytime_shape and len(meaningful_blocks) < 3

        if is_sparse:
            summaries_with_priority.append(
                (
                    sparse_day_priority_key(
                        day=day,
                        meaningful_blocks=meaningful_blocks,
                        occupied_block_count=occupied_block_count,
                        occupied_total_minutes=occupied_total_minutes,
                        item_count=item_count,
                    ),
                    SparseDaySummary(
                        day=day.day,
                        item_count=item_count,
                        missing_blocks=missing_blocks,
                    ),
                )
            )
    summaries_with_priority.sort(key=lambda item: item[0])
    return [summary for _priority, summary in summaries_with_priority]


def sparse_day_priority_key(
    *,
    day: DayItinerary,
    meaningful_blocks: set[TimeBlockType],
    occupied_block_count: int,
    occupied_total_minutes: int,
    item_count: int,
) -> tuple[int, int, int, int, int]:
    return (
        len(meaningful_blocks),
        occupied_block_count,
        occupied_total_minutes,
        item_count,
        day.day,
    )


def infer_light_blocks(day: DayItinerary) -> list[TimeBlockType]:
    if day.blocks:
        return [day.blocks[-1].block_type]
    return [TimeBlockType.AFTERNOON]


def infer_fillable_blocks(
    *,
    day_details: DayItinerary,
    city_candidates: list[CandidateSpec],
) -> list[TimeBlockType]:
    blocks_with_capacity: list[tuple[tuple[int, int, int, int], TimeBlockType]] = []
    fallback_capacity_blocks: list[tuple[tuple[int, int, int, int], TimeBlockType]] = []
    all_candidates = city_candidates
    fullness_by_block = {
        signal.block_type: signal
        for signal in build_day_fullness_signals(day_details)
    }

    for block in day_details.blocks:
        fits_any_candidate = any(
            candidate_fits_block(
                day=day_details,
                target_block=block,
                candidate=candidate,
            )
            for candidate in all_candidates
        )
        if not fits_any_candidate:
            continue

        thinness_key = block_thinness_priority_key(
            block=block,
            fullness_signal=fullness_by_block.get(block.block_type),
        )
        fallback_capacity_blocks.append((thinness_key, block.block_type))
        fullness_signal = fullness_by_block.get(block.block_type)
        if fullness_signal is None or fullness_signal.underfilled:
            blocks_with_capacity.append((thinness_key, block.block_type))

    if blocks_with_capacity:
        blocks_with_capacity.sort(key=lambda item: item[0])
        return [block_type for _key, block_type in blocks_with_capacity]

    if fallback_capacity_blocks:
        fallback_capacity_blocks.sort(key=lambda item: item[0])
        return [block_type for _key, block_type in fallback_capacity_blocks]

    if not day_details.blocks:
        fallback_blocks = infer_light_blocks(day_details)
        return [block_type for block_type in fallback_blocks]

    return []


def block_thinness_priority_key(
    *,
    block: DayTimeBlock,
    fullness_signal: BlockFullnessSignal | None,
) -> tuple[int, int, int, int]:
    occupied_minutes = fullness_signal.occupied_minutes if fullness_signal is not None else 0
    return (
        0 if occupied_minutes == 0 else 1,
        occupied_minutes,
        len(block.items),
        block_order_index(block.block_type),
    )


def block_order_index(block_type: TimeBlockType) -> int:
    if block_type == TimeBlockType.MORNING:
        return 0
    if block_type == TimeBlockType.AFTERNOON:
        return 1
    return 2


def choose_candidate(
    candidates: list[CandidateSpec],
    day_details: DayItinerary,
    target_block: DayTimeBlock,
    block_type: TimeBlockType,
    existing_names: set[str],
    used_names: set[str],
    day_signal: tuple[set[str], set[str]],
    trip_signal: tuple[set[str], set[str]],
    day_centroid: tuple[float, float] | None,
    trip_centroid: tuple[float, float] | None,
    style_preferences: StylePreferenceSignal | set[str] | None = None,
    preference_policy: PlannerPreferencePolicy | None = None,
) -> CandidateSpec | None:
    scored_candidates = rank_candidates_for_block(
        candidates=candidates,
        day_details=day_details,
        target_block=target_block,
        block_type=block_type,
        existing_names=existing_names,
        used_names=used_names,
        day_signal=day_signal,
        trip_signal=trip_signal,
        day_centroid=day_centroid,
        trip_centroid=trip_centroid,
        style_preferences=style_preferences,
        preference_policy=preference_policy,
    )

    if not scored_candidates:
        return None

    scored_candidates.sort(key=cmp_to_key(compare_scored_candidates))
    (
        best_score,
        _best_local_detour_ratio,
        _best_local_detour_delta,
        _best_route_data_quality_tier,
        _best_route_source_symmetry_tier,
        _best_route_side_leg_symmetry_tier,
        _best_route_directionality_tier,
        _best_preference_alignment_key,
        _best_slack_margin,
        _best_kind_rank,
        _best_distance,
        best_candidate,
    ) = scored_candidates[0]
    if best_score == 0 and day_signal == (set(), set()) and trip_signal == (set(), set()):
        return best_candidate
    if best_score <= 0:
        return None
    return best_candidate


def rank_candidates_for_block(
    *,
    candidates: list[CandidateSpec],
    day_details: DayItinerary,
    target_block: DayTimeBlock,
    block_type: TimeBlockType,
    existing_names: set[str],
    used_names: set[str],
    day_signal: tuple[set[str], set[str]],
    trip_signal: tuple[set[str], set[str]],
    day_centroid: tuple[float, float] | None,
    trip_centroid: tuple[float, float] | None,
    style_preferences: StylePreferenceSignal | set[str] | None = None,
    preference_policy: PlannerPreferencePolicy | None = None,
) -> list[ScoredCandidate]:
    scored_candidates: list[ScoredCandidate] = []

    for candidate in candidates:
        if candidate.name in existing_names or candidate.name in used_names:
            continue
        if not candidate_fits_block(
            day=day_details,
            target_block=target_block,
            candidate=candidate,
        ):
            continue
        fit_quality = candidate_insertion_fit_quality(
            day=day_details,
            target_block=target_block,
            candidate=candidate,
        )
        if fit_quality is None:
            continue
        (
            local_detour_ratio,
            local_detour_delta,
            route_data_quality_tier,
            route_source_symmetry_tier,
            route_side_leg_symmetry_tier,
            route_directionality_tier,
            slack_margin_minutes,
            insertion_kind_rank,
        ) = fit_quality

        score = score_completion_candidate(
            candidate=candidate,
            day_details=day_details,
            block_type=block_type,
            day_signal=day_signal,
            trip_signal=trip_signal,
            day_centroid=day_centroid,
            trip_centroid=trip_centroid,
        )
        preference_alignment_key = candidate_preference_alignment_key(
            candidate=candidate,
            block_type=block_type,
            style_preferences=style_preferences,
            preference_policy=preference_policy,
        )
        day_distance = distance_to_centroid(candidate, day_centroid)

        scored_candidates.append(
            (
                score,
                local_detour_ratio,
                local_detour_delta,
                route_data_quality_tier,
                route_source_symmetry_tier,
                route_side_leg_symmetry_tier,
                route_directionality_tier,
                preference_alignment_key,
                slack_margin_minutes,
                insertion_kind_rank,
                day_distance,
                candidate,
            )
        )

    scored_candidates.sort(key=cmp_to_key(compare_scored_candidates))
    return scored_candidates


def score_completion_candidate(
    *,
    candidate: CandidateSpec,
    day_details: DayItinerary,
    block_type: TimeBlockType,
    day_signal: tuple[set[str], set[str]],
    trip_signal: tuple[set[str], set[str]],
    day_centroid: tuple[float, float] | None,
    trip_centroid: tuple[float, float] | None,
) -> int:
    score = 0
    day_areas, day_themes = day_signal
    trip_areas, trip_themes = trip_signal

    score += 4 * overlap_count(day_areas, set(candidate.areas))
    score += 3 * overlap_count(day_themes, set(candidate.themes))
    score += 2 * overlap_count(trip_areas, set(candidate.areas))
    score += 2 * overlap_count(trip_themes, set(candidate.themes))

    if not day_areas and not day_themes:
        score += 1
    score += meal_slot_candidate_score(
        day_details=day_details,
        block_type=block_type,
        candidate=candidate,
    )
    if block_type == TimeBlockType.EVENING and candidate.type == POIType.RESTAURANT:
        score += 2
    if block_type == TimeBlockType.MORNING and candidate.type == POIType.SCENIC:
        score += 1

    day_distance = distance_to_centroid(candidate, day_centroid)
    trip_distance = distance_to_centroid(candidate, trip_centroid)
    score += proximity_score(day_distance, close_km=1.0, mid_km=2.5, wide_km=5.0, close_score=5, mid_score=3, wide_score=1)
    score += proximity_score(trip_distance, close_km=1.5, mid_km=4.0, wide_km=7.0, close_score=2, mid_score=1, wide_score=0)
    return score


def meal_slot_candidate_score(
    *,
    day_details: DayItinerary,
    block_type: TimeBlockType,
    candidate: CandidateSpec,
) -> int:
    if block_type == TimeBlockType.MORNING:
        return -4 if candidate.type == POIType.RESTAURANT else 1

    if block_type not in {TimeBlockType.AFTERNOON, TimeBlockType.EVENING}:
        return 0

    block_has_restaurant = any(
        item.type == POIType.RESTAURANT
        for block in day_details.blocks
        if block.block_type == block_type
        for item in block.items
    )
    if block_has_restaurant:
        return 0

    if candidate.type == POIType.RESTAURANT:
        return 5 if block_type == TimeBlockType.AFTERNOON else 6
    if block_type == TimeBlockType.AFTERNOON:
        return -1
    return 0


def build_signal_profile(items: list[ScheduledPOI]) -> tuple[set[str], set[str]]:
    areas: set[str] = set()
    themes: set[str] = set()
    for item in items:
        normalized_name = item.name.lower()
        for area, keywords in AREA_KEYWORDS.items():
            if any(keyword.lower() in normalized_name for keyword in keywords):
                areas.add(area)
        for theme, keywords in THEME_KEYWORDS.items():
            if any(keyword.lower() in normalized_name for keyword in keywords):
                themes.add(theme)
        if item.type == POIType.RESTAURANT:
            themes.add("street_food")
    return areas, themes


def build_reasoning_summary(
    day: int,
    block_type: TimeBlockType,
    candidate: CandidateSpec,
    day_signal: tuple[set[str], set[str]],
    fullness_signal: BlockFullnessSignal | None,
    sparse_day_rank: int,
    sparse_day_count: int,
    day_fullness_signals: list[BlockFullnessSignal],
    day_items: list[ScheduledPOI] | None = None,
    candidate_pool: list[CandidateSpec] | None = None,
    request_style_preferences: StylePreferenceSignal | set[str] | None = None,
    preference_policy: PlannerPreferencePolicy | None = None,
) -> str:
    day_intro = format_day_priority_phrase(
        day=day,
        sparse_day_rank=sparse_day_rank,
        sparse_day_count=sparse_day_count,
    )
    block_intro = format_block_fullness_phrase(
        block_type=block_type,
        fullness_signal=fullness_signal,
    )
    restraint_phrase = format_day_restraint_phrase(
        block_type=block_type,
        day_fullness_signals=day_fullness_signals,
    )
    day_areas, day_themes = day_signal
    intent_phrase = build_planning_intent_phrase(
        candidate=candidate,
        day_signal=day_signal,
        block_type=block_type,
        request_style_preferences=request_style_preferences,
        preference_policy=preference_policy,
    )
    decision_context = build_specific_decision_context(
        block_type=block_type,
        candidate=candidate,
        day_items=day_items or [],
        candidate_pool=candidate_pool or [],
        intent_phrase=intent_phrase,
        fullness_signal=fullness_signal,
    )
    if day_areas:
        intent_clause = f"，并且{intent_phrase}" if intent_phrase else ""
        return (
            f"{decision_context} "
            f"{day_intro}，{block_intro}{restraint_phrase}，所以 {candidate.name} "
            f"更适合修复这个空档{intent_clause}，并且仍在 {format_signal_values(day_areas)} "
            "附近保持路线连贯。"
        )
    if day_themes:
        intent_clause = f"，并且{intent_phrase}" if intent_phrase else ""
        return (
            f"{decision_context} "
            f"{day_intro}，{block_intro}{restraint_phrase}，所以 {candidate.name} "
            f"更适合修复这个空档{intent_clause}，也更贴近当前围绕 "
            f"{format_signal_values(day_themes)} 的旅行气质。"
        )
    if intent_phrase:
        return (
            f"{decision_context} "
            f"{day_intro}，{block_intro}{restraint_phrase}，所以 {candidate.name} "
            f"更适合修复这个空档，并且{intent_phrase}。"
        )
    poi_label = "餐食停靠点" if candidate.type == POIType.RESTAURANT else "游览点"
    return (
        f"{decision_context} "
        f"{day_intro}，{block_intro}{restraint_phrase}，在这里补一个{poi_label}"
        "会让这一天更自然地继续推进。"
    )


def build_planning_intent_phrase(
    *,
    candidate: CandidateSpec,
    day_signal: tuple[set[str], set[str]],
    block_type: TimeBlockType,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
    preference_policy: PlannerPreferencePolicy | None,
) -> str | None:
    _day_areas, day_themes = day_signal
    candidate_themes = set(candidate.themes)
    candidate_profile = infer_poi_profile(candidate.name, candidate.type)
    visit_style = candidate_profile.visit_style

    request_preference_phrase = build_request_preference_phrase(
        candidate=candidate,
        block_type=block_type,
        candidate_themes=candidate_themes,
        visit_style=visit_style,
        request_style_preferences=request_style_preferences,
        preference_policy=preference_policy,
    )

    if "museum" in day_themes and (
        "museum" in candidate_themes or visit_style == POIVisitStyle.MUSEUM
    ):
        return with_request_preference_phrase(
            "符合这一天已经在形成的博物馆/文化路线",
            request_preference_phrase,
        )

    if (day_themes & {"old_street", "design"}) and (
        candidate_themes & {"old_street", "design"}
        or visit_style in {POIVisitStyle.OLD_STREET, POIVisitStyle.LEISURE_DISTRICT}
    ):
        return with_request_preference_phrase(
            "更接近你偏好的老街漫游感",
            request_preference_phrase,
        )

    if (
        candidate.type == POIType.RESTAURANT
        or "street_food" in candidate_themes
        or visit_style in {POIVisitStyle.FOOD_STOP, POIVisitStyle.FOOD_DISTRICT}
    ) and (day_themes & {"street_food", "night"} or block_type == TimeBlockType.EVENING):
        return with_request_preference_phrase(
            "延续当前较轻松的餐食停靠节奏",
            request_preference_phrase,
        )

    if (
        block_type == TimeBlockType.EVENING
        and (day_themes & {"night", "waterfront"} or candidate_themes & {"night", "waterfront"})
        and (
            candidate_themes & {"night", "waterfront"}
            or visit_style == POIVisitStyle.NIGHT_VIEW
        )
    ):
        return with_request_preference_phrase(
            "延续当前夜间散步或临水夜景的路线气质",
            request_preference_phrase,
        )

    return None


def build_specific_decision_context(
    *,
    block_type: TimeBlockType,
    candidate: CandidateSpec,
    day_items: list[ScheduledPOI],
    candidate_pool: list[CandidateSpec],
    intent_phrase: str | None,
    fullness_signal: BlockFullnessSignal | None,
) -> str:
    gap_phrase = build_gap_existence_phrase(block_type, fullness_signal)
    anchor_phrase = build_nearby_anchor_phrase(candidate=candidate, day_items=day_items)
    preference_phrase = (
        f"它匹配：{intent_phrase}。"
        if intent_phrase
        else build_structural_fit_phrase(block_type=block_type, candidate=candidate)
    )
    rejected_phrase = build_implicit_rejection_phrase(
        block_type=block_type,
        candidate=candidate,
        candidate_pool=candidate_pool,
    )
    return " ".join(
        phrase
        for phrase in (gap_phrase, anchor_phrase, preference_phrase, rejected_phrase)
        if phrase
    )


def build_completion_decision_evidence(
    *,
    block_type: TimeBlockType,
    candidate: CandidateSpec,
    day_items: list[ScheduledPOI],
    candidate_pool: list[CandidateSpec],
    day_details: DayItinerary,
    target_block: DayTimeBlock,
    existing_names: set[str],
    used_names: set[str],
    day_signal: tuple[set[str], set[str]],
    trip_signal: tuple[set[str], set[str]],
    day_centroid: tuple[float, float] | None,
    trip_centroid: tuple[float, float] | None,
    style_preferences: StylePreferenceSignal | set[str] | None,
    fullness_signal: BlockFullnessSignal | None,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
    preference_policy: PlannerPreferencePolicy | None,
) -> CompletionDecisionEvidence:
    intent_phrase = build_planning_intent_phrase(
        candidate=candidate,
        day_signal=day_signal,
        block_type=block_type,
        request_style_preferences=request_style_preferences,
        preference_policy=preference_policy,
    )
    nearby_anchor_phrase = build_nearby_anchor_phrase(
        candidate=candidate,
        day_items=day_items,
    )
    structural_fit_phrase = (
        f"它匹配：{intent_phrase}。"
        if intent_phrase
        else build_structural_fit_phrase(block_type=block_type, candidate=candidate)
    )
    why_this_poi_fits = " ".join(
        phrase
        for phrase in (nearby_anchor_phrase, structural_fit_phrase)
        if phrase
    )

    return CompletionDecisionEvidence(
        why_gap_exists=build_gap_existence_phrase(
            block_type=block_type,
            fullness_signal=fullness_signal,
        ),
        why_this_poi_fits=why_this_poi_fits,
        alternatives_rejected=build_implicit_rejection_phrase(
            block_type=block_type,
            candidate=candidate,
            candidate_pool=candidate_pool,
        ),
        top_candidates=build_top_candidate_traces(
            candidate=candidate,
            candidate_pool=candidate_pool,
            day_details=day_details,
            target_block=target_block,
            block_type=block_type,
            existing_names=existing_names,
            used_names=used_names,
            day_signal=day_signal,
            trip_signal=trip_signal,
            day_centroid=day_centroid,
            trip_centroid=trip_centroid,
            style_preferences=style_preferences,
            preference_policy=preference_policy,
        ),
        rejected_candidates=build_rejected_candidate_traces(
            candidate=candidate,
            candidate_pool=candidate_pool,
            day_details=day_details,
            target_block=target_block,
            block_type=block_type,
            existing_names=existing_names,
            used_names=used_names,
            day_signal=day_signal,
            trip_signal=trip_signal,
            day_centroid=day_centroid,
            trip_centroid=trip_centroid,
            style_preferences=style_preferences,
            preference_policy=preference_policy,
        ),
    )


def build_gap_existence_phrase(
    block_type: TimeBlockType,
    fullness_signal: BlockFullnessSignal | None,
) -> str:
    block_label = format_block_label(block_type)
    if fullness_signal is None or fullness_signal.occupied_minutes == 0:
        return f"这个空档存在，因为{block_label}时段仍然为空。"
    if fullness_signal.underfilled:
        return (
            f"这个空档存在，因为{block_label}时段目前只有 "
            f"{fullness_signal.occupied_minutes} 分钟已安排内容。"
        )
    return f"这个空档存在，因为{block_label}时段仍有可利用余量。"


def build_top_candidate_traces(
    *,
    candidate: CandidateSpec,
    candidate_pool: list[CandidateSpec],
    day_details: DayItinerary,
    target_block: DayTimeBlock,
    block_type: TimeBlockType,
    existing_names: set[str],
    used_names: set[str],
    day_signal: tuple[set[str], set[str]],
    trip_signal: tuple[set[str], set[str]],
    day_centroid: tuple[float, float] | None,
    trip_centroid: tuple[float, float] | None,
    style_preferences: StylePreferenceSignal | set[str] | None,
    preference_policy: PlannerPreferencePolicy | None,
) -> list[CompletionCandidateTrace]:
    ranked = rank_candidates_for_block(
        candidates=candidate_pool,
        day_details=day_details,
        target_block=target_block,
        block_type=block_type,
        existing_names=existing_names,
        used_names=used_names,
        day_signal=day_signal,
        trip_signal=trip_signal,
        day_centroid=day_centroid,
        trip_centroid=trip_centroid,
        style_preferences=style_preferences,
        preference_policy=preference_policy,
    )

    traces: list[CompletionCandidateTrace] = []
    for index, scored in enumerate(ranked[:4], start=1):
        ranked_candidate = scored[11]
        is_selected = ranked_candidate.name == candidate.name
        traces.append(
            CompletionCandidateTrace(
                name=ranked_candidate.name,
                type=ranked_candidate.type,
                rank=index,
                score=scored[0],
                status="selected" if is_selected else "ranked_alternative",
                reason=build_candidate_rank_reason(
                    scored=scored,
                    block_type=block_type,
                    selected=is_selected,
                ),
            )
        )
    return traces


def build_rejected_candidate_traces(
    *,
    candidate: CandidateSpec,
    candidate_pool: list[CandidateSpec],
    day_details: DayItinerary,
    target_block: DayTimeBlock,
    block_type: TimeBlockType,
    existing_names: set[str],
    used_names: set[str],
    day_signal: tuple[set[str], set[str]],
    trip_signal: tuple[set[str], set[str]],
    day_centroid: tuple[float, float] | None,
    trip_centroid: tuple[float, float] | None,
    style_preferences: StylePreferenceSignal | set[str] | None,
    preference_policy: PlannerPreferencePolicy | None,
) -> list[CompletionCandidateTrace]:
    rejected: list[CompletionCandidateTrace] = []
    seen: set[str] = {candidate.name}

    ranked = rank_candidates_for_block(
        candidates=candidate_pool,
        day_details=day_details,
        target_block=target_block,
        block_type=block_type,
        existing_names=existing_names,
        used_names=used_names,
        day_signal=day_signal,
        trip_signal=trip_signal,
        day_centroid=day_centroid,
        trip_centroid=trip_centroid,
        style_preferences=style_preferences,
        preference_policy=preference_policy,
    )
    for index, scored in enumerate(ranked, start=1):
        ranked_candidate = scored[11]
        if ranked_candidate.name in seen:
            continue
        seen.add(ranked_candidate.name)
        rejected.append(
            CompletionCandidateTrace(
                name=ranked_candidate.name,
                type=ranked_candidate.type,
                rank=index,
                score=scored[0],
                status="downranked",
                reason=build_candidate_rank_reason(
                    scored=scored,
                    block_type=block_type,
                    selected=False,
                ),
            )
        )
        if len(rejected) >= 2:
            break

    for rejected_candidate in candidate_pool:
        if rejected_candidate.name in seen:
            continue
        reason = candidate_rejection_reason(
            candidate=rejected_candidate,
            day_details=day_details,
            target_block=target_block,
            block_type=block_type,
            existing_names=existing_names,
            used_names=used_names,
        )
        if reason is None:
            continue
        seen.add(rejected_candidate.name)
        rejected.append(
            CompletionCandidateTrace(
                name=rejected_candidate.name,
                type=rejected_candidate.type,
                rank=None,
                score=None,
                status="rejected",
                reason=reason,
            )
        )
        if len(rejected) >= 4:
            break
    return rejected


def candidate_rejection_reason(
    *,
    candidate: CandidateSpec,
    day_details: DayItinerary,
    target_block: DayTimeBlock,
    block_type: TimeBlockType,
    existing_names: set[str],
    used_names: set[str],
) -> str | None:
    if candidate.name in existing_names:
        return "它已经出现在行程里，所以不会重复用于这个空档。"
    if candidate.name in used_names:
        return "它已经被用于本次推荐的另一个空档。"
    if block_type not in candidate.block_types:
        return f"它更适合其他时段，因此没有用于{format_block_label(block_type)}空档。"
    if candidate.type == POIType.RESTAURANT and any(
        item.type == POIType.RESTAURANT for item in target_block.items
    ):
        return "这个时段已经有餐食锚点，因此没有重复补餐。"
    if not candidate_fits_block(
        day=day_details,
        target_block=target_block,
        candidate=candidate,
    ):
        return "它的游玩时长和缓冲会挤爆这个时段，因此被排除。"
    return None


def build_candidate_rank_reason(
    *,
    scored: ScoredCandidate,
    block_type: TimeBlockType,
    selected: bool,
) -> str:
    (
        score,
        local_detour_ratio,
        local_detour_delta,
        route_data_quality_tier,
        _route_source_symmetry_tier,
        _route_side_leg_symmetry_tier,
        _route_directionality_tier,
        _preference_alignment_key,
        slack_margin_minutes,
        insertion_kind_rank,
        day_distance,
        candidate,
    ) = scored
    status_phrase = "已选中" if selected else "候选备选"
    route_phrase = (
        "路线数据较充分"
        if route_data_quality_tier == STRONG_ROUTE_DATA_QUALITY_TIER
        else "使用了兜底路线估算"
        if route_data_quality_tier == FALLBACK_ROUTE_DATA_QUALITY_TIER
        else "路线数据有限"
    )
    distance_phrase = (
        "贴近当天路线"
        if day_distance < 1.5
        else "距离当天路线适中"
        if day_distance < 4
        else "离当天路线偏远"
    )
    return (
        f"{status_phrase}用于{format_block_label(block_type)}，综合分 {score}；"
        f"{route_phrase}，局部绕行约 {format_ratio_for_trace(local_detour_ratio)}，"
        f"绕行增量 {format_minutes_for_trace(local_detour_delta / 60)}，"
        f"剩余缓冲 {slack_margin_minutes} 分钟，{format_insertion_kind_rank(insertion_kind_rank)}，{distance_phrase}。"
    )


def format_ratio_for_trace(value: float) -> str:
    if not isfinite(value):
        return "未知"
    return f"{round(value, 2)}x"


def format_minutes_for_trace(value: float) -> str:
    if not isfinite(value):
        return "未知"
    return f"{round(value)} 分钟"


def format_insertion_kind_rank(value: int) -> str:
    if value == insertion_kind_rank("empty"):
        return "可直接填入空档"
    if value == insertion_kind_rank("boundary"):
        return "适合放在时段边界"
    return "适合插在两站之间"


def build_nearby_anchor_phrase(
    *,
    candidate: CandidateSpec,
    day_items: list[ScheduledPOI],
) -> str | None:
    if candidate.latitude is None or candidate.longitude is None or not day_items:
        return None

    nearest_items = nearest_day_items(day_items=day_items, candidate=candidate)
    if not nearest_items:
        return None

    anchor = next((item for item in day_items if item.name == nearest_items[0]), None)
    if anchor is None:
        return None
    travel_minutes = estimate_candidate_minutes_from_item(
        candidate=candidate,
        anchor=anchor,
    )
    if travel_minutes is None:
        return f"这一天的路线已经接近 {anchor.name}。"
    return f"这一天的路线已经接近 {anchor.name}，约 {travel_minutes} 分钟可达。"


def estimate_candidate_minutes_from_item(
    *,
    candidate: CandidateSpec,
    anchor: ScheduledPOI,
) -> int | None:
    if candidate.latitude is None or candidate.longitude is None:
        return None
    try:
        walking_route = get_walking_route(
            origin_lat=anchor.latitude,
            origin_lng=anchor.longitude,
            dest_lat=candidate.latitude,
            dest_lng=candidate.longitude,
        )
        return max(1, round(int(walking_route["duration_s"]) / 60))
    except RoutePlanningError:
        distance_km = haversine_km(
            anchor.latitude,
            anchor.longitude,
            candidate.latitude,
            candidate.longitude,
        )
        if distance_km <= 0:
            return 1
        return max(1, round(distance_km / 4.5 * 60))


def build_structural_fit_phrase(
    *,
    block_type: TimeBlockType,
    candidate: CandidateSpec,
) -> str:
    if candidate.type == POIType.RESTAURANT and block_type == TimeBlockType.AFTERNOON:
        return "它适合放在这个空档里作为午餐锚点，再自然接上下半天路线。"
    if candidate.type == POIType.RESTAURANT and block_type == TimeBlockType.EVENING:
        return "它适合放在这个空档里作为晚餐锚点，再衔接可选夜间活动。"
    if candidate.type == POIType.SCENIC and block_type == TimeBlockType.MORNING:
        return "它适合放在上午时段，作为午餐前的白天游览。"
    if candidate.type == POIType.SCENIC and block_type == TimeBlockType.AFTERNOON:
        return "它适合作为下午的主游览点，不需要大幅挪动其他安排。"
    return "它能填补这个空档，同时不会强行挤压当天其他安排。"


def build_implicit_rejection_phrase(
    *,
    block_type: TimeBlockType,
    candidate: CandidateSpec,
    candidate_pool: list[CandidateSpec],
) -> str:
    competing_types = {
        other.type
        for other in candidate_pool
        if other.name != candidate.name and block_type in other.block_types
    }
    if candidate.type == POIType.RESTAURANT:
        if POIType.SCENIC in competing_types:
            return "这里更适合作为餐食锚点，因此暂时降低了景点填充项的优先级。"
        return "其他餐食候选因为顺路连续性更弱，被排在后面。"
    if POIType.RESTAURANT in competing_types and block_type == TimeBlockType.MORNING:
        return "上午空档优先保留给游览点，早餐或午餐不应替代当天第一个景点。"
    if POIType.RESTAURANT in competing_types:
        return "餐食候选被留给午餐或晚餐时段，不与这个景点空档竞争。"
    return "与偏好和路线关系较弱的通用填充项被排除在这个空档之外。"


def with_request_preference_phrase(
    base_phrase: str,
    request_preference_phrase: str | None,
) -> str:
    if not request_preference_phrase:
        return base_phrase
    return f"{base_phrase}, and also fits {request_preference_phrase}"


def build_request_preference_phrase(
    *,
    candidate: CandidateSpec,
    block_type: TimeBlockType,
    candidate_themes: set[str],
    visit_style: POIVisitStyle,
    request_style_preferences: StylePreferenceSignal | set[str] | None,
    preference_policy: PlannerPreferencePolicy | None,
) -> str | None:
    request_style_signal = normalize_style_preference_signal(request_style_preferences)
    if request_style_signal:
        if style_signal_matches(request_style_signal, STYLE_BUCKET_FOOD_STOP) and (
            candidate.type == POIType.RESTAURANT
            or "street_food" in candidate_themes
            or visit_style in {POIVisitStyle.FOOD_STOP, POIVisitStyle.FOOD_DISTRICT}
        ):
            return style_signal_phrase(
                request_style_signal,
                STYLE_BUCKET_FOOD_STOP,
                explicit_phrase="你明确偏好的餐食停靠风格",
                inferred_phrase="当前计划里已经显现出的餐食停靠节奏",
            )

        if style_signal_matches(request_style_signal, STYLE_BUCKET_MUSEUM) and (
            "museum" in candidate_themes or visit_style == POIVisitStyle.MUSEUM
        ):
            return style_signal_phrase(
                request_style_signal,
                STYLE_BUCKET_MUSEUM,
                explicit_phrase="你明确偏好的博物馆/文化风格",
                inferred_phrase="当前计划里已经显现出的博物馆/文化方向",
            )

        if style_signal_matches(request_style_signal, STYLE_BUCKET_OLD_STREET) and (
            candidate_themes & {"old_street", "design"}
            or visit_style in {POIVisitStyle.OLD_STREET, POIVisitStyle.LEISURE_DISTRICT}
        ):
            return style_signal_phrase(
                request_style_signal,
                STYLE_BUCKET_OLD_STREET,
                explicit_phrase="你明确偏好的漫游感",
                inferred_phrase="当前计划里已经显现出的漫游感",
            )

        if style_signal_matches(request_style_signal, STYLE_BUCKET_NIGHT_VIEW) and (
            block_type == TimeBlockType.EVENING
            and (
                candidate_themes & {"night", "waterfront"}
                or visit_style == POIVisitStyle.NIGHT_VIEW
            )
        ):
            return style_signal_phrase(
                request_style_signal,
                STYLE_BUCKET_NIGHT_VIEW,
                explicit_phrase="你明确偏好的夜景风格",
                inferred_phrase="当前计划里已经显现出的夜景方向",
            )

        if style_signal_matches(request_style_signal, STYLE_BUCKET_LANDMARK) and (
            visit_style in {POIVisitStyle.LANDMARK, POIVisitStyle.TEMPLE_PARK}
        ):
            return style_signal_phrase(
                request_style_signal,
                STYLE_BUCKET_LANDMARK,
                explicit_phrase="你明确偏好的地标型游览",
                inferred_phrase="当前计划里已经显现出的地标型方向",
            )

    if preference_policy is None:
        return None

    if preference_policy.dining_priority == "high" and (
        candidate.type == POIType.RESTAURANT
        or "street_food" in candidate_themes
        or visit_style in {POIVisitStyle.FOOD_STOP, POIVisitStyle.FOOD_DISTRICT}
    ):
        return "你偏好的餐食停靠风格"

    if preference_policy.scenic_priority == "high":
        if "museum" in candidate_themes or visit_style == POIVisitStyle.MUSEUM:
            return "你偏好的博物馆/文化风格"
        if candidate_themes & {"old_street", "design"} or visit_style in {
            POIVisitStyle.OLD_STREET,
            POIVisitStyle.LEISURE_DISTRICT,
        }:
            return "你偏好的漫游感"
        if block_type == TimeBlockType.EVENING and (
            candidate_themes & {"night", "waterfront"}
            or visit_style == POIVisitStyle.NIGHT_VIEW
        ):
            return "你偏好的夜景风格"

    if preference_policy.pace == "relaxed":
        if candidate_themes & {"old_street", "design"} or visit_style in {
            POIVisitStyle.OLD_STREET,
            POIVisitStyle.LEISURE_DISTRICT,
        }:
            return "你偏好的更慢漫游节奏"
        if block_type == TimeBlockType.EVENING and (
            candidate_themes & {"night", "waterfront"}
            or visit_style == POIVisitStyle.NIGHT_VIEW
        ):
            return "你偏好的更轻松夜间节奏"

    return None


def build_itinerary_relation_summary(
    day: int,
    block_type: TimeBlockType,
    candidate: CandidateSpec,
    day_items: list[ScheduledPOI],
) -> str:
    related_items = nearest_day_items(day_items=day_items, candidate=candidate)
    if related_items:
        return (
            f"它更适合作为第 {day} 天{format_block_label(block_type)}补点，"
            f"围绕 {format_names(related_items)} 衔接，比随机加入 {candidate.name} "
            "这类全城候选更能保持路线连贯。"
        )
    return (
        f"第 {day} 天当前路线信号还比较弱，因此这是一个偏通用的"
        f"{format_block_label(block_type)}推荐。"
    )


def build_summary(
    *,
    sparse_days: list[SparseDaySummary],
    options: list[ItineraryCompletionOption],
    total_day_count: int,
) -> str:
    lead_day = sparse_days[0]
    if len(sparse_days) > 1:
        trailing_days = "、".join(f"第 {day.day} 天" for day in sparse_days[1:])
        lead_clause = (
            f"第 {lead_day.day} 天是当前最薄的一天，{trailing_days}"
            "也仍然偏轻。"
        )
    else:
        lead_clause = f"第 {lead_day.day} 天仍是当前骨架里最弱的一天。"

    restraint_clause = ""
    if total_day_count > len(sparse_days):
        restraint_clause = (
            " 其他天已经相对平衡，所以这次优先修复更弱的空档。"
        )

    if any("通用" in option.itinerary_relation_summary for option in options):
        return (
            f"{lead_clause}{restraint_clause} 这些建议基于目前有限的路线信号，"
            "更像诚实的补全候选，而不是强行判断的必去点。"
        )
    return (
        f"{lead_clause}{restraint_clause} 这些建议用于加固当前骨架里最薄的部分，"
        "同时尽量贴近已有路线流向。"
    )


def format_day_priority_phrase(
    *,
    day: int,
    sparse_day_rank: int,
    sparse_day_count: int,
) -> str:
    if sparse_day_count <= 1:
        return f"第 {day} 天仍然偏轻"
    if sparse_day_rank == 0:
        return f"第 {day} 天仍是最薄的一天"
    return f"第 {day} 天仍比其他天更轻"


def format_block_fullness_phrase(
    *,
    block_type: TimeBlockType,
    fullness_signal: BlockFullnessSignal | None,
) -> str:
    block_label = format_block_label(block_type)
    if fullness_signal is None or fullness_signal.occupied_minutes == 0:
        return f"{block_label}时段仍然为空"
    if fullness_signal.underfilled:
        return f"{block_label}时段仍然偏空"
    return f"{block_label}时段仍有空间"


def format_day_restraint_phrase(
    *,
    block_type: TimeBlockType,
    day_fullness_signals: list[BlockFullnessSignal],
) -> str:
    other_occupied_blocks = sum(
        1
        for signal in day_fullness_signals
        if signal.block_type != block_type and signal.occupied_minutes > 0
    )
    if other_occupied_blocks >= 2:
        return "，同时当天其他时段已经相对平衡"
    return ""


def overlap_count(left: set[str], right: set[str]) -> int:
    return len(left & right)


def format_block_label(block_type: TimeBlockType) -> str:
    labels = {
        TimeBlockType.MORNING: "上午",
        TimeBlockType.AFTERNOON: "下午",
        TimeBlockType.EVENING: "夜间",
    }
    return labels.get(block_type, block_type.value)


def format_names(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    return f"{names[0]} 和 {names[1]}"


def format_signal_values(values: set[str]) -> str:
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0].replace("_", " ")
    return f"{sorted_values[0].replace('_', ' ')} 和 {sorted_values[1].replace('_', ' ')}"


def infer_itinerary_city(
    itinerary: ItineraryResponse,
    scheduled_items: list[ScheduledPOI],
) -> str | None:
    if itinerary.hotel is not None and itinerary.hotel.city:
        return normalize_city_name(itinerary.hotel.city)

    for item in scheduled_items:
        if item.city:
            return normalize_city_name(item.city)

    return None


def build_day_fullness_signals(day: DayItinerary) -> list[BlockFullnessSignal]:
    return [
        build_block_fullness_signal(block)
        for block in day.blocks
    ]


def build_block_fullness_signal(block: DayTimeBlock) -> BlockFullnessSignal:
    occupied_minutes = block_occupied_minutes(block)
    meaningful = (
        occupied_minutes >= meaningful_block_minutes_threshold(block.block_type)
        or len(block.items) >= 2
    )
    return BlockFullnessSignal(
        block_type=block.block_type,
        occupied_minutes=occupied_minutes,
        meaningful=meaningful,
        underfilled=(occupied_minutes == 0 or not meaningful),
    )


def meaningful_block_minutes_threshold(block_type: TimeBlockType) -> int:
    if block_type == TimeBlockType.MORNING:
        return 60
    if block_type == TimeBlockType.AFTERNOON:
        return 75
    return 75


def build_autofilled_item(
    *,
    itinerary: ItineraryResponse,
    day: DayItinerary,
    option: ItineraryCompletionOption,
) -> ScheduledPOI | None:
    inferred_city = infer_itinerary_city(itinerary, flatten_scheduled_items(itinerary.days))
    latitude, longitude = resolve_candidate_coordinates(
        name=option.name,
        city=inferred_city,
    )
    if latitude is None or longitude is None:
        return None

    profile = infer_poi_profile(option.name, option.type)
    target_block = next(
        (block for block in day.blocks if block.block_type == option.suggested_block),
        None,
    )
    if target_block is None:
        return None

    insertion_plan = plan_block_insertion(
        day=day,
        target_block=target_block,
        poi_type=option.type,
        profile_intensity=profile.intensity,
        duration_minutes=profile.typical_duration_minutes,
        candidate_lat=latitude,
        candidate_lng=longitude,
    )
    if insertion_plan is None:
        return None

    travel_distance_m, travel_duration_s = estimate_travel_metadata(
        origin_lat=insertion_plan["travel_anchor"].latitude,
        origin_lng=insertion_plan["travel_anchor"].longitude,
        dest_lat=latitude,
        dest_lng=longitude,
    )

    return ScheduledPOI(
        name=option.name,
        type=option.type,
        city=inferred_city,
        latitude=latitude,
        longitude=longitude,
        duration_minutes=profile.typical_duration_minutes,
        day=day.day,
        start_time=insertion_plan["start_time"],
        end_time=insertion_plan["end_time"],
        is_fixed=False,
        placement_reason=insertion_plan["placement_reason"],
        source_type=ScheduledPOISourceType.AUTO_FILLED,
        source_label="系统空档补全",
        source_reason=build_autofill_source_reason(option),
        travel_from_name=insertion_plan["travel_anchor"].name,
        travel_distance_m=travel_distance_m,
        travel_duration_s=travel_duration_s,
    )


def build_autofill_source_reason(option: ItineraryCompletionOption) -> str:
    if option.decision_evidence is None:
        return "系统插入这个补全候选，让稀疏时段变成可执行路线。"
    return " ".join(
        [
            option.decision_evidence.why_gap_exists,
            option.decision_evidence.why_this_poi_fits,
            option.decision_evidence.alternatives_rejected,
        ]
    )


def flatten_scheduled_items(days: list[DayItinerary]) -> list[ScheduledPOI]:
    return [item for day in days for block in day.blocks for item in block.items]


def find_autofill_anchor(
    *,
    day: DayItinerary,
    target_block: DayTimeBlock,
) -> ScheduledPOI | HotelStay:
    previous_items = [
        item
        for block in day.blocks
        if block.start_time < target_block.start_time
        for item in block.items
    ]
    if previous_items:
        return max(previous_items, key=lambda item: (item.end_time, item.start_time, item.name))
    return day.hotel


def find_next_autofill_anchor(
    *,
    day: DayItinerary,
    target_block: DayTimeBlock,
) -> ScheduledPOI | HotelStay:
    following_items = [
        item
        for block in day.blocks
        if block.start_time > target_block.start_time
        for item in block.items
    ]
    if following_items:
        return min(following_items, key=lambda item: (item.start_time, item.end_time, item.name))
    return day.hotel


def plan_block_insertion(
    *,
    day: DayItinerary,
    target_block: DayTimeBlock,
    poi_type: POIType,
    profile_intensity: str,
    duration_minutes: int,
    candidate_lat: float,
    candidate_lng: float,
) -> dict[str, time | ScheduledPOI | HotelStay | str] | None:
    empty_extra_minutes = dynamic_block_extra_buffer_minutes(
        target_block=target_block,
        poi_type=poi_type,
        profile_intensity=profile_intensity,
        insertion_kind="empty",
        duration_minutes=duration_minutes,
    )
    boundary_extra_minutes = dynamic_block_extra_buffer_minutes(
        target_block=target_block,
        poi_type=poi_type,
        profile_intensity=profile_intensity,
        insertion_kind="boundary",
        duration_minutes=duration_minutes,
    )
    middle_extra_minutes = dynamic_block_extra_buffer_minutes(
        target_block=target_block,
        poi_type=poi_type,
        profile_intensity=profile_intensity,
        insertion_kind="middle",
        duration_minutes=duration_minutes,
    )
    if not target_block.items:
        if not gap_supports_duration(
            gap_minutes=minutes_between_times(target_block.start_time, target_block.end_time),
            duration_minutes=duration_minutes,
            insertion_kind="empty",
            block_type=target_block.block_type,
            poi_type=poi_type,
            profile_intensity=profile_intensity,
            pacing_extra_minutes=empty_extra_minutes,
        ):
            return None
        scheduled_end = add_minutes_to_time(target_block.start_time, duration_minutes)
        if scheduled_end > target_block.end_time:
            return None
        travel_anchor = find_autofill_anchor(day=day, target_block=target_block)
        return {
            "start_time": target_block.start_time,
            "end_time": scheduled_end,
            "travel_anchor": travel_anchor,
            "placement_reason": (
                f"系统自动修复稀疏的{format_block_label(target_block.block_type)}时段，"
                "使用了更贴合当前路线的补全候选。"
            ),
        }

    ordered_items = sorted(target_block.items, key=lambda item: (item.start_time, item.end_time, item.name))
    first_item = ordered_items[0]
    last_item = ordered_items[-1]
    before_gap = minutes_between_times(target_block.start_time, first_item.start_time)
    after_gap = minutes_between_times(last_item.end_time, target_block.end_time)

    feasible_plans: list[
        tuple[float, float, int, int, int, int, time, dict[str, time | ScheduledPOI | HotelStay | str]]
    ] = []

    if gap_supports_duration(
        gap_minutes=before_gap,
        duration_minutes=duration_minutes,
        insertion_kind="boundary",
        block_type=target_block.block_type,
        poi_type=poi_type,
        profile_intensity=profile_intensity,
        pacing_extra_minutes=boundary_extra_minutes,
    ):
        previous_anchor = find_autofill_anchor(day=day, target_block=target_block)
        before_start = add_minutes_to_time(
            first_item.start_time,
            -effective_buffer_minutes(
                insertion_kind="boundary",
                block_type=target_block.block_type,
                poi_type=poi_type,
                profile_intensity=profile_intensity,
                pacing_extra_minutes=boundary_extra_minutes,
            ) - duration_minutes,
        )
        (
            before_ratio,
            before_delta,
            before_quality_tier,
            before_source_tier,
            before_side_leg_tier,
            before_directionality_tier,
        ) = estimate_local_detour_metrics(
            previous_anchor=previous_anchor,
            next_anchor=first_item,
            candidate_lat=candidate_lat,
            candidate_lng=candidate_lng,
        )
        feasible_plans.append(
            (
                before_ratio,
                before_delta,
                before_quality_tier,
                before_source_tier,
                before_side_leg_tier,
                before_directionality_tier,
                2,
                before_start,
                {
                    "start_time": before_start,
                    "end_time": first_item.start_time,
                    "travel_anchor": previous_anchor,
                    "placement_reason": (
                        f"系统自动修复稀疏的{format_block_label(target_block.block_type)}时段，"
                        f"把候选放在 {first_item.name} 之前以保持局部路线连贯。"
                    ),
                },
            )
        )

    for previous_item, next_item in zip(ordered_items, ordered_items[1:]):
        middle_gap = minutes_between_times(previous_item.end_time, next_item.start_time)
        if not gap_supports_duration(
            gap_minutes=middle_gap,
            duration_minutes=duration_minutes,
            insertion_kind="middle",
            block_type=target_block.block_type,
            poi_type=poi_type,
            profile_intensity=profile_intensity,
            pacing_extra_minutes=middle_extra_minutes,
        ):
            continue

        lead_buffer, _trail_buffer = middle_buffer_split(
            block_type=target_block.block_type,
            poi_type=poi_type,
            profile_intensity=profile_intensity,
            pacing_extra_minutes=middle_extra_minutes,
        )
        (
            middle_ratio,
            middle_delta,
            middle_quality_tier,
            middle_source_tier,
            middle_side_leg_tier,
            middle_directionality_tier,
        ) = estimate_local_detour_metrics(
            previous_anchor=previous_item,
            next_anchor=next_item,
            candidate_lat=candidate_lat,
            candidate_lng=candidate_lng,
        )
        feasible_plans.append(
            (
                middle_ratio,
                middle_delta,
                middle_quality_tier,
                middle_source_tier,
                middle_side_leg_tier,
                middle_directionality_tier,
                0,
                add_minutes_to_time(previous_item.end_time, lead_buffer),
                {
                    "start_time": add_minutes_to_time(previous_item.end_time, lead_buffer),
                    "end_time": add_minutes_to_time(
                        add_minutes_to_time(previous_item.end_time, lead_buffer),
                        duration_minutes,
                    ),
                    "travel_anchor": previous_item,
                    "placement_reason": (
                        f"系统自动修复稀疏的{format_block_label(target_block.block_type)}时段，"
                        f"把候选放在 {previous_item.name} 和 {next_item.name} 之间以保持局部路线连贯。"
                    ),
                },
            )
        )

    if gap_supports_duration(
        gap_minutes=after_gap,
        duration_minutes=duration_minutes,
        insertion_kind="boundary",
        block_type=target_block.block_type,
        poi_type=poi_type,
        profile_intensity=profile_intensity,
        pacing_extra_minutes=boundary_extra_minutes,
    ):
        next_anchor = find_next_autofill_anchor(day=day, target_block=target_block)
        after_start = add_minutes_to_time(
            last_item.end_time,
            effective_buffer_minutes(
                insertion_kind="boundary",
                block_type=target_block.block_type,
                poi_type=poi_type,
                profile_intensity=profile_intensity,
                pacing_extra_minutes=boundary_extra_minutes,
            ),
        )
        after_end = add_minutes_to_time(after_start, duration_minutes)
        (
            after_ratio,
            after_delta,
            after_quality_tier,
            after_source_tier,
            after_side_leg_tier,
            after_directionality_tier,
        ) = estimate_local_detour_metrics(
            previous_anchor=last_item,
            next_anchor=next_anchor,
            candidate_lat=candidate_lat,
            candidate_lng=candidate_lng,
        )
        feasible_plans.append(
            (
                after_ratio,
                after_delta,
                after_quality_tier,
                after_source_tier,
                after_side_leg_tier,
                after_directionality_tier,
                1,
                after_start,
                {
                    "start_time": after_start,
                    "end_time": after_end,
                    "travel_anchor": last_item,
                    "placement_reason": (
                        f"系统自动修复稀疏的{format_block_label(target_block.block_type)}时段，"
                        f"把候选放在 {last_item.name} 之后以保持局部路线连贯。"
                    ),
                },
            )
        )

    if not feasible_plans:
        return None

    feasible_plans.sort(key=cmp_to_key(compare_feasible_plans))
    return feasible_plans[0][8]


def compare_route_ranking(
    *,
    left_ratio: float,
    left_delta: float,
    left_evidence_tier: int,
    left_source_tier: int,
    left_side_leg_tier: int,
    left_directionality_tier: int,
    right_ratio: float,
    right_delta: float,
    right_evidence_tier: int,
    right_source_tier: int,
    right_side_leg_tier: int,
    right_directionality_tier: int,
) -> int:
    if abs(left_ratio - right_ratio) > NORMALIZED_DETOUR_RATIO_TIE_EPSILON:
        return -1 if left_ratio < right_ratio else 1
    if abs(left_delta - right_delta) > ABSOLUTE_DETOUR_DELTA_TIE_EPSILON:
        return -1 if left_delta < right_delta else 1
    if left_evidence_tier != right_evidence_tier:
        return -1 if left_evidence_tier < right_evidence_tier else 1
    if left_source_tier != right_source_tier:
        return -1 if left_source_tier < right_source_tier else 1
    if left_side_leg_tier != right_side_leg_tier:
        return -1 if left_side_leg_tier < right_side_leg_tier else 1
    if left_directionality_tier != right_directionality_tier:
        return -1 if left_directionality_tier < right_directionality_tier else 1
    if left_delta != right_delta:
        return -1 if left_delta < right_delta else 1
    return 0


def compare_scored_candidates(
    left: tuple[int, float, float, int, int, int, int, tuple[int, int, int, int], int, int, float, CandidateSpec],
    right: tuple[int, float, float, int, int, int, int, tuple[int, int, int, int], int, int, float, CandidateSpec],
) -> int:
    score_gap = abs(left[0] - right[0])
    if left[0] != right[0] and score_gap > PREFERENCE_ALIGNMENT_SCORE_CLOSE_GAP:
        return -1 if left[0] > right[0] else 1

    route_ranking = compare_route_ranking(
        left_ratio=left[1],
        left_delta=left[2],
        left_evidence_tier=left[3],
        left_source_tier=left[4],
        left_side_leg_tier=left[5],
        left_directionality_tier=left[6],
        right_ratio=right[1],
        right_delta=right[2],
        right_evidence_tier=right[3],
        right_source_tier=right[4],
        right_side_leg_tier=right[5],
        right_directionality_tier=right[6],
    )
    if left[0] == right[0] and route_ranking != 0:
        return route_ranking

    if (
        score_gap <= PREFERENCE_ALIGNMENT_SCORE_CLOSE_GAP
        and route_ranking == 0
        and left[7] != right[7]
    ):
        return -1 if left[7] < right[7] else 1

    if left[0] != right[0]:
        return -1 if left[0] > right[0] else 1
    if route_ranking != 0:
        return route_ranking
    if left[8] != right[8]:
        return -1 if left[8] > right[8] else 1
    if left[9] != right[9]:
        return -1 if left[9] < right[9] else 1
    if left[10] != right[10]:
        return -1 if left[10] < right[10] else 1
    if left[11].type.value != right[11].type.value:
        return -1 if left[11].type.value < right[11].type.value else 1
    if left[11].name != right[11].name:
        return -1 if left[11].name < right[11].name else 1
    return 0


def candidate_preference_alignment_key(
    *,
    candidate: CandidateSpec,
    block_type: TimeBlockType,
    style_preferences: StylePreferenceSignal | set[str] | None,
    preference_policy: PlannerPreferencePolicy | None,
) -> tuple[int, int, int, int]:
    style_preference_signal = normalize_style_preference_signal(style_preferences)
    if preference_policy is None and style_preference_signal is None:
        return (1, 1, 1, 1)

    candidate_themes = set(candidate.themes)
    visit_style = infer_poi_profile(candidate.name, candidate.type).visit_style

    dining_rank = 1
    if preference_policy is not None and preference_policy.dining_priority == "high":
        dining_rank = 0 if (
            candidate.type == POIType.RESTAURANT
            or "street_food" in candidate_themes
            or visit_style in {POIVisitStyle.FOOD_STOP, POIVisitStyle.FOOD_DISTRICT}
        ) else 1

    scenic_rank = 1
    if preference_policy is not None and preference_policy.scenic_priority == "high":
        scenic_rank = 0 if (
            candidate.type == POIType.SCENIC
            and (
                candidate_themes & {"museum", "old_street", "design", "waterfront", "night", "garden"}
                or visit_style in {
                    POIVisitStyle.MUSEUM,
                    POIVisitStyle.LANDMARK,
                    POIVisitStyle.TEMPLE_PARK,
                    POIVisitStyle.OLD_STREET,
                    POIVisitStyle.LEISURE_DISTRICT,
                    POIVisitStyle.NIGHT_VIEW,
                }
            )
        ) else 1

    pace_rank = 1
    if preference_policy is not None and preference_policy.pace == "relaxed":
        if (
            candidate_themes & {"old_street", "design", "street_food", "night", "waterfront"}
            or visit_style in {
                POIVisitStyle.OLD_STREET,
                POIVisitStyle.LEISURE_DISTRICT,
                POIVisitStyle.FOOD_STOP,
                POIVisitStyle.FOOD_DISTRICT,
                POIVisitStyle.NIGHT_VIEW,
            }
        ):
            pace_rank = 0
        elif candidate.profile_intensity == "heavy":
            pace_rank = 2

    style_rank = 1
    if style_preference_signal:
        candidate_style_bucket = infer_style_bucket(
            name=candidate.name,
            poi_type=candidate.type,
        )
        if candidate_style_bucket is not None:
            source = style_preference_signal.source_for(candidate_style_bucket)
            if source == "explicit":
                style_rank = 0
            elif source == "inferred":
                style_rank = 1
            else:
                style_rank = 2

    return (dining_rank, scenic_rank, style_rank, pace_rank)


def normalize_style_preference_signal(
    value: StylePreferenceSignal | set[str] | None,
) -> StylePreferenceSignal | None:
    if value is None:
        return None
    if isinstance(value, StylePreferenceSignal):
        return value if value else None
    explicit_styles = frozenset(value)
    if not explicit_styles:
        return None
    return StylePreferenceSignal(explicit=explicit_styles)


def style_signal_matches(
    signal: StylePreferenceSignal,
    style_bucket: str,
) -> bool:
    return signal.source_for(style_bucket) is not None


def style_signal_phrase(
    signal: StylePreferenceSignal,
    style_bucket: str,
    *,
    explicit_phrase: str,
    inferred_phrase: str,
) -> str | None:
    source = signal.source_for(style_bucket)
    if source == "explicit":
        return explicit_phrase
    if source == "inferred":
        return inferred_phrase
    return None


def infer_dominant_style_preferences(items: list[ScheduledPOI]) -> set[str]:
    style_counts: dict[str, int] = {}
    for item in items:
        style_bucket = infer_style_bucket(name=item.name, poi_type=item.type)
        if style_bucket is None:
            continue
        style_counts[style_bucket] = style_counts.get(style_bucket, 0) + 1

    if not style_counts:
        return set()

    max_count = max(style_counts.values())
    total_count = sum(style_counts.values())
    if max_count == 1 and total_count > 2:
        return set()

    return {
        style_bucket
        for style_bucket, count in style_counts.items()
        if count == max_count
    }


def infer_style_bucket(
    *,
    name: str,
    poi_type: POIType,
) -> str | None:
    visit_style = infer_poi_profile(name, poi_type).visit_style

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


def compare_feasible_plans(
    left: tuple[float, float, int, int, int, int, int, time, dict[str, time | ScheduledPOI | HotelStay | str]],
    right: tuple[float, float, int, int, int, int, int, time, dict[str, time | ScheduledPOI | HotelStay | str]],
) -> int:
    route_ranking = compare_route_ranking(
        left_ratio=left[0],
        left_delta=left[1],
        left_evidence_tier=left[2],
        left_source_tier=left[3],
        left_side_leg_tier=left[4],
        left_directionality_tier=left[5],
        right_ratio=right[0],
        right_delta=right[1],
        right_evidence_tier=right[2],
        right_source_tier=right[3],
        right_side_leg_tier=right[4],
        right_directionality_tier=right[5],
    )
    if route_ranking != 0:
        return route_ranking
    if left[6] != right[6]:
        return -1 if left[6] < right[6] else 1
    if left[7] != right[7]:
        return -1 if left[7] < right[7] else 1
    return 0


def compare_candidate_fit_quality(
    left: tuple[float, float, int, int, int, int, int, int],
    right: tuple[float, float, int, int, int, int, int, int],
) -> int:
    route_ranking = compare_route_ranking(
        left_ratio=left[0],
        left_delta=left[1],
        left_evidence_tier=left[2],
        left_source_tier=left[3],
        left_side_leg_tier=left[4],
        left_directionality_tier=left[5],
        right_ratio=right[0],
        right_delta=right[1],
        right_evidence_tier=right[2],
        right_source_tier=right[3],
        right_side_leg_tier=right[4],
        right_directionality_tier=right[5],
    )
    if route_ranking != 0:
        return route_ranking
    if left[6] != right[6]:
        return -1 if left[6] > right[6] else 1
    if left[7] != right[7]:
        return -1 if left[7] > right[7] else 1
    return 0


def estimate_side_route_cost(
    *,
    previous_anchor: ScheduledPOI | HotelStay,
    next_anchor: ScheduledPOI | HotelStay,
    candidate_lat: float | None,
    candidate_lng: float | None,
) -> float:
    if candidate_lat is None or candidate_lng is None:
        return float("inf")

    inbound_distance_m, inbound_duration_s = estimate_travel_metadata(
        origin_lat=previous_anchor.latitude,
        origin_lng=previous_anchor.longitude,
        dest_lat=candidate_lat,
        dest_lng=candidate_lng,
    )
    outbound_distance_m, outbound_duration_s = estimate_travel_metadata(
        origin_lat=candidate_lat,
        origin_lng=candidate_lng,
        dest_lat=next_anchor.latitude,
        dest_lng=next_anchor.longitude,
    )

    if inbound_duration_s is not None and outbound_duration_s is not None:
        return float(inbound_duration_s + outbound_duration_s)

    inbound_distance = float(inbound_distance_m or 0)
    outbound_distance = float(outbound_distance_m or 0)
    return inbound_distance + outbound_distance


def estimate_travel_metadata_with_quality(
    *,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> tuple[int, int, int]:
    try:
        route = get_walking_route(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
        )
        return (
            int(route["distance_m"]),
            int(route["duration_s"]),
            STRONG_ROUTE_DATA_QUALITY_TIER,
        )
    except RoutePlanningError:
        distance_km = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
        distance_m = int(distance_km * 1000)
        walking_duration_s = int((distance_km / 4.5) * 3600) if distance_km > 0 else 0
        return (
            distance_m,
            walking_duration_s,
            FALLBACK_ROUTE_DATA_QUALITY_TIER,
        )


def estimate_side_route_metrics(
    *,
    previous_anchor: ScheduledPOI | HotelStay,
    next_anchor: ScheduledPOI | HotelStay,
    candidate_lat: float | None,
    candidate_lng: float | None,
) -> tuple[float, int, int]:
    if candidate_lat is None or candidate_lng is None:
        return float("inf"), MISSING_ROUTE_DATA_QUALITY_TIER, MISSING_ROUTE_DATA_QUALITY_TIER

    _inbound_distance_m, inbound_duration_s, inbound_quality_tier = estimate_travel_metadata_with_quality(
        origin_lat=previous_anchor.latitude,
        origin_lng=previous_anchor.longitude,
        dest_lat=candidate_lat,
        dest_lng=candidate_lng,
    )
    _outbound_distance_m, outbound_duration_s, outbound_quality_tier = estimate_travel_metadata_with_quality(
        origin_lat=candidate_lat,
        origin_lng=candidate_lng,
        dest_lat=next_anchor.latitude,
        dest_lng=next_anchor.longitude,
    )
    return (
        float(inbound_duration_s + outbound_duration_s),
        inbound_quality_tier,
        outbound_quality_tier,
    )


def estimate_direct_route_cost(
    *,
    origin_anchor: ScheduledPOI | HotelStay,
    dest_anchor: ScheduledPOI | HotelStay,
) -> float:
    direct_distance_m, direct_duration_s = estimate_travel_metadata(
        origin_lat=origin_anchor.latitude,
        origin_lng=origin_anchor.longitude,
        dest_lat=dest_anchor.latitude,
        dest_lng=dest_anchor.longitude,
    )

    if direct_duration_s is not None:
        return float(direct_duration_s)

    return float(direct_distance_m or 0)


def estimate_direct_route_metrics(
    *,
    origin_anchor: ScheduledPOI | HotelStay,
    dest_anchor: ScheduledPOI | HotelStay,
) -> tuple[float, int]:
    _direct_distance_m, direct_duration_s, direct_quality_tier = estimate_travel_metadata_with_quality(
        origin_lat=origin_anchor.latitude,
        origin_lng=origin_anchor.longitude,
        dest_lat=dest_anchor.latitude,
        dest_lng=dest_anchor.longitude,
    )
    return float(direct_duration_s), direct_quality_tier


def route_evidence_completeness_tier(*quality_tiers: int) -> int:
    if any(tier == MISSING_ROUTE_DATA_QUALITY_TIER for tier in quality_tiers):
        return MISSING_ROUTE_EVIDENCE_TIER
    if all(tier == STRONG_ROUTE_DATA_QUALITY_TIER for tier in quality_tiers):
        return ALL_STRONG_ROUTE_EVIDENCE_TIER
    if all(tier == FALLBACK_ROUTE_DATA_QUALITY_TIER for tier in quality_tiers):
        return ALL_FALLBACK_ROUTE_EVIDENCE_TIER
    return MIXED_ROUTE_EVIDENCE_TIER


def route_evidence_source_symmetry_tier(
    *,
    inbound_quality_tier: int,
    outbound_quality_tier: int,
    baseline_quality_tier: int,
) -> int:
    completeness_tier = route_evidence_completeness_tier(
        inbound_quality_tier,
        outbound_quality_tier,
        baseline_quality_tier,
    )
    if completeness_tier == MISSING_ROUTE_EVIDENCE_TIER:
        return MISSING_ROUTE_SOURCE_TIER
    if completeness_tier != MIXED_ROUTE_EVIDENCE_TIER:
        return NEUTRAL_ROUTE_SOURCE_TIER
    if baseline_quality_tier == STRONG_ROUTE_DATA_QUALITY_TIER:
        return BASELINE_STRONG_MIXED_ROUTE_SOURCE_TIER
    return BASELINE_FALLBACK_MIXED_ROUTE_SOURCE_TIER


def route_side_leg_symmetry_tier(
    *,
    inbound_quality_tier: int,
    outbound_quality_tier: int,
    baseline_quality_tier: int,
) -> int:
    completeness_tier = route_evidence_completeness_tier(
        inbound_quality_tier,
        outbound_quality_tier,
        baseline_quality_tier,
    )
    if completeness_tier == MISSING_ROUTE_EVIDENCE_TIER:
        return MISSING_SIDE_LEG_SYMMETRY_TIER
    if baseline_quality_tier != STRONG_ROUTE_DATA_QUALITY_TIER:
        return OTHER_SIDE_LEG_SYMMETRY_TIER
    if (
        inbound_quality_tier == STRONG_ROUTE_DATA_QUALITY_TIER
        and outbound_quality_tier == STRONG_ROUTE_DATA_QUALITY_TIER
    ):
        return BOTH_SIDE_LEGS_STRONG_TIER
    if (
        inbound_quality_tier == STRONG_ROUTE_DATA_QUALITY_TIER
        or outbound_quality_tier == STRONG_ROUTE_DATA_QUALITY_TIER
    ):
        return ONE_SIDE_STRONG_ONE_FALLBACK_TIER
    return OTHER_SIDE_LEG_SYMMETRY_TIER


def route_side_leg_directionality_tier(
    *,
    inbound_quality_tier: int,
    outbound_quality_tier: int,
    baseline_quality_tier: int,
) -> int:
    if any(
        tier == MISSING_ROUTE_DATA_QUALITY_TIER
        for tier in (inbound_quality_tier, outbound_quality_tier, baseline_quality_tier)
    ):
        return MISSING_DIRECTIONALITY_TIER
    if baseline_quality_tier != STRONG_ROUTE_DATA_QUALITY_TIER:
        return NEUTRAL_DIRECTIONALITY_TIER
    if (
        inbound_quality_tier == STRONG_ROUTE_DATA_QUALITY_TIER
        and outbound_quality_tier == FALLBACK_ROUTE_DATA_QUALITY_TIER
    ):
        return INBOUND_STRONG_DIRECTIONALITY_TIER
    if (
        inbound_quality_tier == FALLBACK_ROUTE_DATA_QUALITY_TIER
        and outbound_quality_tier == STRONG_ROUTE_DATA_QUALITY_TIER
    ):
        return OUTBOUND_STRONG_DIRECTIONALITY_TIER
    return NEUTRAL_DIRECTIONALITY_TIER


def estimate_local_detour_delta(
    *,
    previous_anchor: ScheduledPOI | HotelStay,
    next_anchor: ScheduledPOI | HotelStay,
    candidate_lat: float | None,
    candidate_lng: float | None,
) -> float:
    side_route_cost = estimate_side_route_cost(
        previous_anchor=previous_anchor,
        next_anchor=next_anchor,
        candidate_lat=candidate_lat,
        candidate_lng=candidate_lng,
    )
    if side_route_cost == float("inf"):
        return side_route_cost

    baseline_cost = estimate_direct_route_cost(
        origin_anchor=previous_anchor,
        dest_anchor=next_anchor,
    )
    return max(0.0, side_route_cost - baseline_cost)


def estimate_local_detour_metrics(
    *,
    previous_anchor: ScheduledPOI | HotelStay,
    next_anchor: ScheduledPOI | HotelStay,
    candidate_lat: float | None,
    candidate_lng: float | None,
) -> tuple[float, float, int, int, int, int]:
    side_route_cost, inbound_quality_tier, outbound_quality_tier = estimate_side_route_metrics(
        previous_anchor=previous_anchor,
        next_anchor=next_anchor,
        candidate_lat=candidate_lat,
        candidate_lng=candidate_lng,
    )
    if side_route_cost == float("inf"):
        return (
            float("inf"),
            float("inf"),
            MISSING_ROUTE_EVIDENCE_TIER,
            MISSING_ROUTE_SOURCE_TIER,
            MISSING_SIDE_LEG_SYMMETRY_TIER,
            MISSING_DIRECTIONALITY_TIER,
        )

    baseline_cost, baseline_quality_tier = estimate_direct_route_metrics(
        origin_anchor=previous_anchor,
        dest_anchor=next_anchor,
    )
    detour_delta = max(0.0, side_route_cost - baseline_cost)
    normalized_baseline_cost = max(MIN_NORMALIZED_DETOUR_BASELINE_COST, baseline_cost)
    return (
        detour_delta / normalized_baseline_cost,
        detour_delta,
        route_evidence_completeness_tier(
            inbound_quality_tier,
            outbound_quality_tier,
            baseline_quality_tier,
        ),
        route_evidence_source_symmetry_tier(
            inbound_quality_tier=inbound_quality_tier,
            outbound_quality_tier=outbound_quality_tier,
            baseline_quality_tier=baseline_quality_tier,
        ),
        route_side_leg_symmetry_tier(
            inbound_quality_tier=inbound_quality_tier,
            outbound_quality_tier=outbound_quality_tier,
            baseline_quality_tier=baseline_quality_tier,
        ),
        route_side_leg_directionality_tier(
            inbound_quality_tier=inbound_quality_tier,
            outbound_quality_tier=outbound_quality_tier,
            baseline_quality_tier=baseline_quality_tier,
        ),
    )


def minimum_candidate_duration_for_block(
    *,
    candidates: list[CandidateSpec],
    block_type: TimeBlockType,
) -> int | None:
    durations = [
        candidate.duration_minutes
        for candidate in candidates
        if block_type in candidate.block_types
    ]
    if not durations:
        return None
    return min(durations)


def block_insertion_capacity_minutes(
    *,
    day: DayItinerary,
    target_block: DayTimeBlock,
    poi_type: POIType,
    profile_intensity: str = "medium",
    duration_minutes: int = 0,
) -> int:
    empty_extra_minutes = dynamic_block_extra_buffer_minutes(
        target_block=target_block,
        poi_type=poi_type,
        profile_intensity=profile_intensity,
        insertion_kind="empty",
        duration_minutes=duration_minutes,
    )
    boundary_extra_minutes = dynamic_block_extra_buffer_minutes(
        target_block=target_block,
        poi_type=poi_type,
        profile_intensity=profile_intensity,
        insertion_kind="boundary",
        duration_minutes=duration_minutes,
    )
    middle_extra_minutes = dynamic_block_extra_buffer_minutes(
        target_block=target_block,
        poi_type=poi_type,
        profile_intensity=profile_intensity,
        insertion_kind="middle",
        duration_minutes=duration_minutes,
    )
    if not target_block.items:
        return max_insertable_duration_for_gap(
            gap_minutes=minutes_between_times(target_block.start_time, target_block.end_time),
            insertion_kind="empty",
            block_type=target_block.block_type,
            poi_type=poi_type,
            profile_intensity=profile_intensity,
            pacing_extra_minutes=empty_extra_minutes,
        )

    ordered_items = sorted(target_block.items, key=lambda item: (item.start_time, item.end_time, item.name))
    before_capacity = max_insertable_duration_for_gap(
        gap_minutes=minutes_between_times(target_block.start_time, ordered_items[0].start_time),
        insertion_kind="boundary",
        block_type=target_block.block_type,
        poi_type=poi_type,
        profile_intensity=profile_intensity,
        pacing_extra_minutes=boundary_extra_minutes,
    )
    after_capacity = max_insertable_duration_for_gap(
        gap_minutes=minutes_between_times(ordered_items[-1].end_time, target_block.end_time),
        insertion_kind="boundary",
        block_type=target_block.block_type,
        poi_type=poi_type,
        profile_intensity=profile_intensity,
        pacing_extra_minutes=boundary_extra_minutes,
    )
    middle_capacities = [
        max_insertable_duration_for_gap(
            gap_minutes=minutes_between_times(previous_item.end_time, next_item.start_time),
            insertion_kind="middle",
            block_type=target_block.block_type,
            poi_type=poi_type,
            profile_intensity=profile_intensity,
            pacing_extra_minutes=middle_extra_minutes,
        )
        for previous_item, next_item in zip(ordered_items, ordered_items[1:])
    ]
    return max([before_capacity, after_capacity, *middle_capacities], default=0)


def estimate_travel_metadata(
    *,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> tuple[int | None, int | None]:
    distance_m, duration_s, _quality_tier = estimate_travel_metadata_with_quality(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
    )
    return distance_m, duration_s


def add_minutes_to_time(value: time, minutes: int) -> time:
    base = datetime.combine(datetime(2000, 1, 1).date(), value)
    return (base + timedelta(minutes=minutes)).time()


def middle_buffer_split(
    *,
    block_type: TimeBlockType | None,
    poi_type: POIType | None,
    profile_intensity: str | None,
    pacing_extra_minutes: int = 0,
) -> tuple[int, int]:
    total_buffer = effective_buffer_minutes(
        insertion_kind="middle",
        block_type=block_type,
        poi_type=poi_type,
        profile_intensity=profile_intensity,
        pacing_extra_minutes=pacing_extra_minutes,
    )
    lead_buffer = total_buffer // 2
    trail_buffer = total_buffer - lead_buffer
    return lead_buffer, trail_buffer


def insertion_buffer_minutes(insertion_kind: str) -> int:
    if insertion_kind == "middle":
        return MIDDLE_INSERTION_BUFFER_MINUTES
    return BOUNDARY_INSERTION_BUFFER_MINUTES


def context_extra_buffer_minutes(block_type: TimeBlockType | None) -> int:
    if block_type == TimeBlockType.EVENING:
        return EVENING_BLOCK_EXTRA_BUFFER_MINUTES
    return 0


def poi_type_buffer_adjustment_minutes(poi_type: POIType | None) -> int:
    if poi_type == POIType.RESTAURANT:
        return -RESTAURANT_BUFFER_DISCOUNT_MINUTES
    return 0


def profile_buffer_adjustment_minutes(
    *,
    poi_type: POIType | None,
    profile_intensity: str | None,
) -> int:
    if poi_type != POIType.SCENIC:
        return 0
    if profile_intensity == "light":
        return -LIGHT_SCENIC_PROFILE_BUFFER_DISCOUNT_MINUTES
    if profile_intensity == "heavy":
        return HEAVY_SCENIC_PROFILE_BUFFER_EXTRA_MINUTES
    return 0


def infer_scheduled_item_intensity(item: ScheduledPOI) -> str:
    return infer_poi_profile(item.name, item.type).intensity


def block_pacing_buffer_adjustment_minutes(
    *,
    target_block: DayTimeBlock,
    poi_type: POIType | None,
    profile_intensity: str | None,
) -> int:
    if poi_type != POIType.SCENIC or not target_block.items:
        return 0

    scenic_item_intensities = [
        infer_scheduled_item_intensity(item)
        for item in target_block.items
        if item.type == POIType.SCENIC
    ]
    if "heavy" not in scenic_item_intensities:
        return 0
    if profile_intensity == "heavy":
        return EXISTING_HEAVY_BLOCK_HEAVY_CANDIDATE_EXTRA_BUFFER_MINUTES
    if profile_intensity == "medium":
        return EXISTING_HEAVY_BLOCK_MEDIUM_CANDIDATE_EXTRA_BUFFER_MINUTES
    return 0


def block_load_buffer_adjustment_minutes(
    *,
    target_block: DayTimeBlock,
    poi_type: POIType | None,
) -> int:
    if poi_type != POIType.SCENIC:
        return 0

    scenic_item_count = sum(1 for item in target_block.items if item.type == POIType.SCENIC)
    if scenic_item_count >= 2:
        return HIGH_SCENIC_BLOCK_LOAD_EXTRA_BUFFER_MINUTES
    return 0


def block_occupied_minutes(target_block: DayTimeBlock) -> int:
    return sum(
        minutes_between_times(item.start_time, item.end_time)
        for item in target_block.items
    )


def block_saturation_buffer_adjustment_minutes(
    *,
    target_block: DayTimeBlock,
    poi_type: POIType | None,
    insertion_kind: str = "boundary",
    duration_minutes: int | None = None,
) -> int:
    if poi_type != POIType.SCENIC:
        return 0

    total_block_minutes = minutes_between_times(target_block.start_time, target_block.end_time)
    if total_block_minutes <= 0:
        return 0

    occupied_ratio = block_occupied_minutes(target_block) / total_block_minutes
    moderate_threshold, high_threshold = block_saturation_thresholds(target_block.block_type)
    saturation_extra_minutes = 0
    if occupied_ratio >= high_threshold:
        saturation_extra_minutes = HIGH_SCENIC_BLOCK_SATURATION_EXTRA_BUFFER_MINUTES
    elif occupied_ratio >= moderate_threshold:
        saturation_extra_minutes = MODERATE_SCENIC_BLOCK_SATURATION_EXTRA_BUFFER_MINUTES

    if saturation_extra_minutes <= 0:
        return 0
    if insertion_kind == "middle":
        saturation_extra_minutes += MIDDLE_INSERTION_SATURATION_EXTRA_BUFFER_MINUTES
    if (
        poi_type == POIType.SCENIC
        and duration_minutes is not None
        and duration_minutes >= LONG_SCENIC_DURATION_MINUTES
    ):
        saturation_extra_minutes += LONG_SCENIC_SATURATION_EXTRA_BUFFER_MINUTES
    return saturation_extra_minutes


def dynamic_block_extra_buffer_minutes(
    *,
    target_block: DayTimeBlock,
    poi_type: POIType,
    profile_intensity: str,
    insertion_kind: str,
    duration_minutes: int,
) -> int:
    return (
        block_pacing_buffer_adjustment_minutes(
            target_block=target_block,
            poi_type=poi_type,
            profile_intensity=profile_intensity,
        )
        + block_load_buffer_adjustment_minutes(
            target_block=target_block,
            poi_type=poi_type,
        )
        + block_saturation_buffer_adjustment_minutes(
            target_block=target_block,
            poi_type=poi_type,
            insertion_kind=insertion_kind,
            duration_minutes=duration_minutes,
        )
    )


def block_saturation_thresholds(
    block_type: TimeBlockType,
) -> tuple[float, float]:
    if block_type == TimeBlockType.EVENING:
        return (
            EVENING_MODERATE_BLOCK_SATURATION_THRESHOLD,
            EVENING_HIGH_BLOCK_SATURATION_THRESHOLD,
        )
    return (
        DEFAULT_MODERATE_BLOCK_SATURATION_THRESHOLD,
        DEFAULT_HIGH_BLOCK_SATURATION_THRESHOLD,
    )


def effective_buffer_minutes(
    *,
    insertion_kind: str,
    block_type: TimeBlockType | None,
    poi_type: POIType | None,
    profile_intensity: str | None = None,
    pacing_extra_minutes: int = 0,
) -> int:
    return max(
        0,
        insertion_buffer_minutes(insertion_kind)
        + context_extra_buffer_minutes(block_type)
        + poi_type_buffer_adjustment_minutes(poi_type)
        + profile_buffer_adjustment_minutes(
            poi_type=poi_type,
            profile_intensity=profile_intensity,
        )
        + pacing_extra_minutes,
    )


def max_insertable_duration_for_gap(
    *,
    gap_minutes: int,
    insertion_kind: str,
    block_type: TimeBlockType | None = None,
    poi_type: POIType | None = None,
    profile_intensity: str | None = None,
    pacing_extra_minutes: int = 0,
) -> int:
    return max(
        0,
        gap_minutes
        - effective_buffer_minutes(
            insertion_kind=insertion_kind,
            block_type=block_type,
            poi_type=poi_type,
            profile_intensity=profile_intensity,
            pacing_extra_minutes=pacing_extra_minutes,
        ),
    )


def gap_supports_duration(
    *,
    gap_minutes: int,
    duration_minutes: int,
    insertion_kind: str,
    block_type: TimeBlockType | None = None,
    poi_type: POIType | None = None,
    profile_intensity: str | None = None,
    pacing_extra_minutes: int = 0,
) -> bool:
    return gap_minutes >= (
        duration_minutes
        + effective_buffer_minutes(
            insertion_kind=insertion_kind,
            block_type=block_type,
            poi_type=poi_type,
            profile_intensity=profile_intensity,
            pacing_extra_minutes=pacing_extra_minutes,
        )
    )


def candidate_fits_block(
    *,
    day: DayItinerary,
    target_block: DayTimeBlock,
    candidate: CandidateSpec,
) -> bool:
    if target_block.block_type not in candidate.block_types:
        return False
    if candidate.type == POIType.RESTAURANT and any(
        item.type == POIType.RESTAURANT for item in target_block.items
    ):
        return False
    return candidate.duration_minutes <= block_insertion_capacity_minutes(
        day=day,
        target_block=target_block,
        poi_type=candidate.type,
        profile_intensity=candidate.profile_intensity,
        duration_minutes=candidate.duration_minutes,
    )


def candidate_insertion_fit_quality(
    *,
    day: DayItinerary,
    target_block: DayTimeBlock,
    candidate: CandidateSpec,
) -> tuple[float, float, int, int, int, int, int, int] | None:
    if target_block.block_type not in candidate.block_types:
        return None
    if candidate.type == POIType.RESTAURANT and any(
        item.type == POIType.RESTAURANT for item in target_block.items
    ):
        return None

    empty_extra_minutes = dynamic_block_extra_buffer_minutes(
        target_block=target_block,
        poi_type=candidate.type,
        profile_intensity=candidate.profile_intensity,
        insertion_kind="empty",
        duration_minutes=candidate.duration_minutes,
    )
    boundary_extra_minutes = dynamic_block_extra_buffer_minutes(
        target_block=target_block,
        poi_type=candidate.type,
        profile_intensity=candidate.profile_intensity,
        insertion_kind="boundary",
        duration_minutes=candidate.duration_minutes,
    )
    middle_extra_minutes = dynamic_block_extra_buffer_minutes(
        target_block=target_block,
        poi_type=candidate.type,
        profile_intensity=candidate.profile_intensity,
        insertion_kind="middle",
        duration_minutes=candidate.duration_minutes,
    )

    feasible_insertions: list[tuple[float, float, int, int, int, int, int, int]] = []

    if not target_block.items:
        empty_capacity = max_insertable_duration_for_gap(
            gap_minutes=minutes_between_times(target_block.start_time, target_block.end_time),
            insertion_kind="empty",
            block_type=target_block.block_type,
            poi_type=candidate.type,
            profile_intensity=candidate.profile_intensity,
            pacing_extra_minutes=empty_extra_minutes,
        )
        if candidate.duration_minutes <= empty_capacity:
            previous_anchor = find_autofill_anchor(day=day, target_block=target_block)
            next_anchor = find_next_autofill_anchor(day=day, target_block=target_block)
            (
                local_detour_ratio,
                local_detour_delta,
                route_data_quality_tier,
                route_source_symmetry_tier,
                route_side_leg_symmetry_tier,
                route_directionality_tier,
            ) = estimate_local_detour_metrics(
                previous_anchor=previous_anchor,
                next_anchor=next_anchor,
                candidate_lat=candidate.latitude,
                candidate_lng=candidate.longitude,
            )
            feasible_insertions.append(
                (
                    local_detour_ratio,
                    local_detour_delta,
                    route_data_quality_tier,
                    route_source_symmetry_tier,
                    route_side_leg_symmetry_tier,
                    route_directionality_tier,
                    empty_capacity - candidate.duration_minutes,
                    insertion_kind_rank("empty"),
                )
            )
    else:
        ordered_items = sorted(target_block.items, key=lambda item: (item.start_time, item.end_time, item.name))

        before_capacity = max_insertable_duration_for_gap(
            gap_minutes=minutes_between_times(target_block.start_time, ordered_items[0].start_time),
            insertion_kind="boundary",
            block_type=target_block.block_type,
            poi_type=candidate.type,
            profile_intensity=candidate.profile_intensity,
            pacing_extra_minutes=boundary_extra_minutes,
        )
        if candidate.duration_minutes <= before_capacity:
            previous_anchor = find_autofill_anchor(day=day, target_block=target_block)
            (
                local_detour_ratio,
                local_detour_delta,
                route_data_quality_tier,
                route_source_symmetry_tier,
                route_side_leg_symmetry_tier,
                route_directionality_tier,
            ) = estimate_local_detour_metrics(
                previous_anchor=previous_anchor,
                next_anchor=ordered_items[0],
                candidate_lat=candidate.latitude,
                candidate_lng=candidate.longitude,
            )
            feasible_insertions.append(
                (
                    local_detour_ratio,
                    local_detour_delta,
                    route_data_quality_tier,
                    route_source_symmetry_tier,
                    route_side_leg_symmetry_tier,
                    route_directionality_tier,
                    before_capacity - candidate.duration_minutes,
                    insertion_kind_rank("boundary"),
                )
            )

        after_capacity = max_insertable_duration_for_gap(
            gap_minutes=minutes_between_times(ordered_items[-1].end_time, target_block.end_time),
            insertion_kind="boundary",
            block_type=target_block.block_type,
            poi_type=candidate.type,
            profile_intensity=candidate.profile_intensity,
            pacing_extra_minutes=boundary_extra_minutes,
        )
        if candidate.duration_minutes <= after_capacity:
            next_anchor = find_next_autofill_anchor(day=day, target_block=target_block)
            (
                local_detour_ratio,
                local_detour_delta,
                route_data_quality_tier,
                route_source_symmetry_tier,
                route_side_leg_symmetry_tier,
                route_directionality_tier,
            ) = estimate_local_detour_metrics(
                previous_anchor=ordered_items[-1],
                next_anchor=next_anchor,
                candidate_lat=candidate.latitude,
                candidate_lng=candidate.longitude,
            )
            feasible_insertions.append(
                (
                    local_detour_ratio,
                    local_detour_delta,
                    route_data_quality_tier,
                    route_source_symmetry_tier,
                    route_side_leg_symmetry_tier,
                    route_directionality_tier,
                    after_capacity - candidate.duration_minutes,
                    insertion_kind_rank("boundary"),
                )
            )

        for previous_item, next_item in zip(ordered_items, ordered_items[1:]):
            middle_capacity = max_insertable_duration_for_gap(
                gap_minutes=minutes_between_times(previous_item.end_time, next_item.start_time),
                insertion_kind="middle",
                block_type=target_block.block_type,
                poi_type=candidate.type,
                profile_intensity=candidate.profile_intensity,
                pacing_extra_minutes=middle_extra_minutes,
            )
            if candidate.duration_minutes <= middle_capacity:
                (
                    local_detour_ratio,
                    local_detour_delta,
                    route_data_quality_tier,
                    route_source_symmetry_tier,
                    route_side_leg_symmetry_tier,
                    route_directionality_tier,
                ) = estimate_local_detour_metrics(
                    previous_anchor=previous_item,
                    next_anchor=next_item,
                    candidate_lat=candidate.latitude,
                    candidate_lng=candidate.longitude,
                )
                feasible_insertions.append(
                    (
                        local_detour_ratio,
                        local_detour_delta,
                        route_data_quality_tier,
                        route_source_symmetry_tier,
                        route_side_leg_symmetry_tier,
                        route_directionality_tier,
                        middle_capacity - candidate.duration_minutes,
                        insertion_kind_rank("middle"),
                    )
                )

    if not feasible_insertions:
        return None

    feasible_insertions.sort(
        key=cmp_to_key(compare_candidate_fit_quality)
    )
    return feasible_insertions[0]


def insertion_kind_rank(insertion_kind: str) -> int:
    if insertion_kind == "empty":
        return 2
    if insertion_kind == "boundary":
        return 1
    return 0


def minutes_between_times(start_time: time, end_time: time) -> int:
    start_dt = datetime.combine(datetime(2000, 1, 1).date(), start_time)
    end_dt = datetime.combine(datetime(2000, 1, 1).date(), end_time)
    delta = end_dt - start_dt
    return max(0, int(delta.total_seconds() // 60))


def build_centroid(items: list[ScheduledPOI]) -> tuple[float, float] | None:
    valid_items = [item for item in items if item.latitude is not None and item.longitude is not None]
    if not valid_items:
        return None

    return (
        sum(item.latitude for item in valid_items) / len(valid_items),
        sum(item.longitude for item in valid_items) / len(valid_items),
    )


def distance_to_centroid(
    candidate: CandidateSpec,
    centroid: tuple[float, float] | None,
) -> float:
    if centroid is None or candidate.latitude is None or candidate.longitude is None:
        return float("inf")

    return haversine_km(
        candidate.latitude,
        candidate.longitude,
        centroid[0],
        centroid[1],
    )


def proximity_score(
    distance_km: float,
    *,
    close_km: float,
    mid_km: float,
    wide_km: float,
    close_score: int,
    mid_score: int,
    wide_score: int,
) -> int:
    if distance_km == float("inf"):
        return 0
    if distance_km <= close_km:
        return close_score
    if distance_km <= mid_km:
        return mid_score
    if distance_km <= wide_km:
        return wide_score
    return 0


def nearest_day_items(
    day_items: list[ScheduledPOI],
    candidate: CandidateSpec,
) -> list[str]:
    if len(day_items) <= 2:
        return [item.name for item in day_items[:2]]

    if candidate.latitude is None or candidate.longitude is None:
        return [item.name for item in day_items[:2]]

    ranked_items = sorted(
        day_items,
        key=lambda item: haversine_km(
            item.latitude,
            item.longitude,
            candidate.latitude,
            candidate.longitude,
        ),
    )
    return [item.name for item in ranked_items[:2]]


def haversine_km(
    left_lat: float,
    left_lng: float,
    right_lat: float,
    right_lng: float,
) -> float:
    left_lat_rad = radians(left_lat)
    left_lng_rad = radians(left_lng)
    right_lat_rad = radians(right_lat)
    right_lng_rad = radians(right_lng)

    delta_lat = right_lat_rad - left_lat_rad
    delta_lng = right_lng_rad - left_lng_rad
    a = (
        sin(delta_lat / 2) ** 2
        + cos(left_lat_rad) * cos(right_lat_rad) * sin(delta_lng / 2) ** 2
    )
    return 6371.0 * 2 * atan2(sqrt(a), sqrt(1 - a))
