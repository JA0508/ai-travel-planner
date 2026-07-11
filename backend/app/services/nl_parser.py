from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.schemas.availability import AvailabilityWindow
from app.schemas.intent import ParsedFixedEvent, ParsedTripIntentResponse
from app.schemas.planning_state import PlanningInputState
from app.services.llm_intent_parser import IntentParsingError, parse_trip_text_with_llm
from app.services.preference_policy import (
    StylePreferenceAttribution,
    build_style_preference_debug_snapshot,
    build_style_preference_signal_from_sources,
    build_style_preference_attribution_from_names,
    normalize_style_preference_sources,
    ordered_style_preferences,
    summarize_style_preference_attribution,
    style_preference_sources_from_signal,
)


logger = logging.getLogger(__name__)
KEY_ALIASES = {
    "city": ("城市", "city"),
    "hotel": ("酒店", "hotel", "住宿", "民宿"),
    "arrival_anchor": ("到达", "arrival", "arrival_anchor", "出发地", "入境点", "抵达"),
    "departure_anchor": ("离开", "departure", "departure_anchor", "返程", "出境点"),
    "availability_windows": ("可用时间", "availability", "availability_windows", "时间范围", "可出行时间"),
    "scenic_spots": ("景点", "scenic", "scenic_spots", "想去", "景点列表"),
    "restaurants": ("餐厅", "restaurant", "restaurants", "吃饭", "美食"),
    "preferences": ("偏好", "preference", "preferences"),
    "fixed": ("固定", "fixed", "固定安排", "fixed_events"),
}

CHINESE_NUMBER_MAP = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

GENERIC_INTEREST_KEYWORDS = (
    "citywalk",
    "city walk",
    "夜景",
    "江景",
    "历史",
    "文化",
    "历史文化",
    "人文",
    "古迹",
    "老街",
    "古镇",
    "博物馆",
    "展览",
    "咖啡",
    "下午茶",
    "本帮菜",
    "小吃",
    "美食",
    "轻松",
    "慢慢逛",
    "闲逛",
)

COMMON_CITY_NAMES = (
    "北京",
    "上海",
    "广州",
    "深圳",
    "杭州",
    "苏州",
    "南京",
    "成都",
    "重庆",
    "西安",
    "武汉",
    "长沙",
    "厦门",
    "青岛",
    "天津",
    "大理",
    "丽江",
    "昆明",
    "三亚",
    "香港",
    "澳门",
    "台北",
)

SOFT_TIME_PREFERENCE_KEYWORDS = (
    "轻松",
    "别太赶",
    "不要太赶",
    "别排太满",
    "不要排太满",
    "留点休息",
    "留一段时间休息",
    "休息",
    "最多安排",
    "早起",
    "不想起太早",
    "夜景",
    "吃饭",
)
ANCHOR_SUFFIX_KEYWORDS = (
    "国际机场",
    "机场",
    "火车站",
    "高铁站",
    "动车站",
    "汽车站",
    "客运站",
    "航站楼",
    "码头",
    "口岸",
    "虹桥",
    "浦东",
    "车站",
    "站",
)
RESTAURANT_NAME_HINTS = (
    "餐厅",
    "饭店",
    "菜馆",
    "饭庄",
    "酒家",
    "咖啡",
    "coffee",
    "cafe",
    "茶馆",
    "小吃街",
    "火锅",
    "面馆",
    "烧烤",
    "酒馆",
    "食堂",
)
FIXED_EVENT_NAME_KEYWORDS = (
    "预约",
    "安排",
    "见朋友",
    "见面",
    "会朋友",
    "演出",
    "音乐剧",
    "话剧",
    "表演",
    "会议",
    "活动",
    "固定行程",
    "有约",
)


@dataclass(frozen=True, slots=True)
class ParsedStyleAttributionInspectionRow:
    label: str
    style_preferences: tuple[str, ...]
    style_preference_sources: dict[str, str]
    debug_snapshot: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedStyleAttributionInspectionReport:
    total_samples: int
    samples_with_styles: int
    aggregate_source_counts: dict[str, int]
    aggregate_evidence_counts: dict[str, int]
    rows: tuple[ParsedStyleAttributionInspectionRow, ...]


def parse_trip_text(text: str) -> ParsedTripIntentResponse:
    """
    Parse free-form trip text into structured intent.

    Main path:
    - LLM-backed intent extraction

    Fallback path:
    - lightweight rule-based parser for local/dev resilience when the LLM
      parser is unavailable or misconfigured
    """
    try:
        return supplement_inline_boundary_windows(
            normalize_parsed_trip_intent(parse_trip_text_with_llm(text)),
            text,
        )
    except IntentParsingError as exc:
        logger.info("LLM intent parser unavailable; using deterministic fallback parser: %s", exc)
        return normalize_parsed_trip_intent(parse_trip_text_fallback(text))


def parse_trip_text_fallback(text: str) -> ParsedTripIntentResponse:
    normalized_text = text.strip()
    lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    weekday_day_map = build_weekday_day_map(normalized_text)

    city = extract_city(normalized_text, lines)
    trip_days = extract_trip_days(normalized_text, lines)
    hotel = extract_single_value(lines, KEY_ALIASES["hotel"])
    arrival_anchor = extract_single_value(lines, KEY_ALIASES["arrival_anchor"])
    departure_anchor = extract_single_value(lines, KEY_ALIASES["departure_anchor"])
    availability_windows = extract_availability_windows(lines)
    scenic_spots = extract_list_value(lines, KEY_ALIASES["scenic_spots"])
    restaurants = extract_list_value(lines, KEY_ALIASES["restaurants"])
    preferences = extract_list_value(lines, KEY_ALIASES["preferences"])

    if arrival_anchor is None:
        arrival_anchor = extract_inline_arrival_anchor(normalized_text)
    if departure_anchor is None:
        departure_anchor = extract_inline_departure_anchor(normalized_text)

    scenic_spots.extend(extract_inline_scenic_spots(normalized_text, city=city))
    restaurants.extend(extract_inline_restaurants(normalized_text))
    preferences.extend(extract_inline_preferences(normalized_text))
    availability_windows.extend(
        extract_inline_availability_windows(
            normalized_text,
            trip_days=trip_days,
            weekday_day_map=weekday_day_map,
        )
    )
    fixed_events = extract_fixed_events(lines)
    fixed_events.extend(
        extract_inline_fixed_events(
            normalized_text,
            trip_days=trip_days,
            weekday_day_map=weekday_day_map,
        )
    )
    style_attribution = build_style_preference_attribution_from_names(
        preferences=unique_preserve_order(preferences),
        scenic_spot_names=unique_preserve_order(scenic_spots),
        restaurant_names=unique_preserve_order(restaurants),
    )
    style_signal = style_attribution.signal

    parsed = ParsedTripIntentResponse(
        city=city,
        trip_days=trip_days,
        hotel=hotel,
        arrival_anchor=arrival_anchor,
        departure_anchor=departure_anchor,
        availability_windows=availability_windows,
        scenic_spots=unique_preserve_order(scenic_spots),
        restaurants=unique_preserve_order(restaurants),
        fixed_events=fixed_events,
        preferences=unique_preserve_order(preferences),
        style_preferences=ordered_style_preferences(style_signal.combined()),
        style_preference_sources=style_preference_sources_from_signal(style_signal),
    )
    parsed._style_preference_evidence = dict(style_attribution.evidence)
    return parsed


def normalize_parsed_trip_intent(parsed: ParsedTripIntentResponse) -> ParsedTripIntentResponse:
    fixed_events = [
        ParsedFixedEvent(
            name=event.name.strip(),
            fixed_day=event.fixed_day,
            fixed_time_start=normalize_time_text(event.fixed_time_start),
            fixed_time_end=normalize_time_text(event.fixed_time_end),
            category=normalize_category(event.category),
        )
        for event in parsed.fixed_events
        if event.name.strip() and not is_non_actionable_generic_fixed_event(event)
    ]

    fixed_event_names = {event.name.casefold() for event in fixed_events}
    raw_scenic_spots = remove_fixed_event_duplicates(parsed.scenic_spots, fixed_event_names)
    scenic_spots, scenic_seed_preferences = split_scenic_spots_and_preferences(raw_scenic_spots)
    restaurants = remove_fixed_event_duplicates(parsed.restaurants, fixed_event_names)
    preferences = normalize_preferences([*parsed.preferences, *scenic_seed_preferences])
    style_attribution = build_style_preference_attribution_from_names(
        preferences=preferences,
        scenic_spot_names=scenic_spots,
        restaurant_names=restaurants,
        parsed_style_preferences=normalize_style_preferences(parsed.style_preferences),
        parsed_style_preference_sources=normalize_style_preference_sources(
            parsed.style_preference_sources
        ),
    )
    style_signal = style_attribution.signal
    style_preference_sources = style_preference_sources_from_signal(style_signal)

    normalized = ParsedTripIntentResponse(
        city=parsed.city.strip() if parsed.city else None,
        trip_days=parsed.trip_days,
        hotel=parsed.hotel.strip() if parsed.hotel else None,
        arrival_anchor=parsed.arrival_anchor.strip() if parsed.arrival_anchor else None,
        departure_anchor=parsed.departure_anchor.strip() if parsed.departure_anchor else None,
        availability_windows=normalize_availability_windows(parsed.availability_windows),
        scenic_spots=scenic_spots,
        restaurants=restaurants,
        fixed_events=fixed_events,
        preferences=preferences,
        style_preferences=ordered_style_preferences(style_signal.combined()),
        style_preference_sources=style_preference_sources,
        disambiguation_summary=parsed.disambiguation_summary,
    )
    normalized._style_preference_evidence = dict(style_attribution.evidence)
    return normalized


def supplement_inline_boundary_windows(
    parsed: ParsedTripIntentResponse,
    raw_text: str,
) -> ParsedTripIntentResponse:
    """
    Backfill deterministic arrival/departure boundary windows from raw text.

    LLM extraction is allowed to understand preferences, but hard day boundaries
    such as "第一天中午到" or "第三天晚上坐火车离开" must be explicit before the
    deterministic scheduler runs. This supplement only adds missing availability
    windows; it does not invent POIs or reorder anything.
    """
    normalized_text = raw_text.strip()
    if not normalized_text:
        return parsed

    lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    trip_days = parsed.trip_days or extract_trip_days(normalized_text, lines)
    supplemental_windows = extract_inline_availability_windows(
        normalized_text,
        trip_days=trip_days,
        weekday_day_map=build_weekday_day_map(normalized_text),
    )
    if not supplemental_windows:
        return parsed

    existing_keys = {
        (window.day, window.label, window.available_start, window.available_end)
        for window in parsed.availability_windows
    }
    additions = [
        window
        for window in supplemental_windows
        if (window.day, window.label, window.available_start, window.available_end)
        not in existing_keys
    ]
    if not additions:
        return parsed

    return normalize_parsed_trip_intent(
        parsed.model_copy(
            update={
                "availability_windows": [
                    *parsed.availability_windows,
                    *additions,
                ]
            }
        )
    )


def normalize_time_text(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip()


def normalize_category(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"scenic", "restaurant", "transport", "activity", "other"}:
        return normalized
    return "other"


def remove_fixed_event_duplicates(values: list[str], fixed_event_names: set[str]) -> list[str]:
    filtered: list[str] = []
    for value in unique_preserve_order([item.strip() for item in values if item.strip()]):
        if value.casefold() in fixed_event_names:
            continue
        filtered.append(value)
    return filtered


def normalize_preferences(values: list[str]) -> list[str]:
    cleaned = [value.strip() for value in values if value.strip()]
    return unique_preserve_order(cleaned)


def split_scenic_spots_and_preferences(values: list[str]) -> tuple[list[str], list[str]]:
    scenic_spots: list[str] = []
    preferences: list[str] = []
    for value in values:
        preference = preference_from_non_place_scenic_seed(value)
        if preference is not None:
            preferences.append(preference)
            continue
        scenic_spots.append(value)
    return scenic_spots, preferences


def normalize_style_preferences(values: list[str]) -> list[str]:
    allowed = {"museum", "old_street", "landmark", "food_stop", "night_view"}
    cleaned = [value.strip() for value in values if value.strip() in allowed]
    return unique_preserve_order(cleaned)


def build_parsed_style_attribution_debug_snapshot(
    parsed: ParsedTripIntentResponse | PlanningInputState,
) -> tuple[str, ...]:
    return build_style_preference_debug_snapshot(
        build_parsed_style_attribution(parsed)
    )


def inspect_parsed_style_attribution_samples(
    samples: Iterable[tuple[str, str]],
    *,
    parser: Callable[[str], ParsedTripIntentResponse] = parse_trip_text,
) -> ParsedStyleAttributionInspectionReport:
    return inspect_parsed_style_attribution_parsed_samples(
        ((label, parser(text)) for label, text in samples)
    )


def build_parsed_style_attribution(
    parsed: ParsedTripIntentResponse | PlanningInputState,
) -> StylePreferenceAttribution:
    return StylePreferenceAttribution(
        signal=build_style_preference_signal_from_sources(
            parsed.style_preference_sources
        ),
        evidence=getattr(parsed, "_style_preference_evidence", {}),
    )


def inspect_parsed_style_attribution_parsed_samples(
    samples: Iterable[tuple[str, ParsedTripIntentResponse]],
) -> ParsedStyleAttributionInspectionReport:
    rows: list[ParsedStyleAttributionInspectionRow] = []
    aggregate_source_counts = {
        "explicit": 0,
        "inferred": 0,
    }
    aggregate_evidence_counts = {
        "request_wording": 0,
        "parser_explicit": 0,
        "parser_inferred": 0,
        "poi_mix": 0,
    }

    for label, parsed in samples:
        debug_snapshot = build_parsed_style_attribution_debug_snapshot(parsed)
        attribution = build_parsed_style_attribution(parsed)
        summary = summarize_style_preference_attribution(attribution)

        aggregate_source_counts["explicit"] += summary.explicit_count
        aggregate_source_counts["inferred"] += summary.inferred_count
        for evidence_key, count in summary.evidence_counts.items():
            aggregate_evidence_counts[evidence_key] += count

        rows.append(
            ParsedStyleAttributionInspectionRow(
                label=label,
                style_preferences=tuple(parsed.style_preferences),
                style_preference_sources=dict(parsed.style_preference_sources),
                debug_snapshot=debug_snapshot,
            )
        )

    return ParsedStyleAttributionInspectionReport(
        total_samples=len(rows),
        samples_with_styles=sum(1 for row in rows if row.style_preferences),
        aggregate_source_counts=aggregate_source_counts,
        aggregate_evidence_counts=aggregate_evidence_counts,
        rows=tuple(rows),
    )


def normalize_availability_windows(
    windows: list[AvailabilityWindow],
) -> list[AvailabilityWindow]:
    normalized: list[AvailabilityWindow] = []
    seen: set[tuple[int | None, str | None, str | None, str | None]] = set()

    for window in windows:
        label = window.label.strip() if window.label else None
        start = normalize_time_text(window.available_start)
        end = normalize_time_text(window.available_end)
        normalized_window = AvailabilityWindow(
            day=window.day,
            label=label,
            available_start=start,
            available_end=end,
        )
        key = (
            normalized_window.day,
            normalized_window.label,
            normalized_window.available_start,
            normalized_window.available_end,
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(normalized_window)

    return normalized


def extract_city(text: str, lines: list[str]) -> str | None:
    explicit_city = extract_single_value(lines, KEY_ALIASES["city"])
    if explicit_city:
        return explicit_city

    known_city = extract_known_city(text)
    if known_city:
        return known_city

    patterns = [
        r"(?:去|到|在)(?P<city>[\u4e00-\u9fffA-Za-z]{2,20})(?:玩|旅行|旅游|出差|待)",
        r"(?P<city>[\u4e00-\u9fffA-Za-z]{2,20})(?:\s*)(?:玩|旅行|旅游)(?P<days>\d+)?",
        r"(?P<city>[\u4e00-\u9fff]{2,8})(?:\d+|[零一二两三四五六七八九十]+)?(?:天|日)",
        r"(?:上午|中午|下午|晚上|傍晚|夜里|夜晚)?到(?P<city>[\u4e00-\u9fff]{2,8})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            city = match.group("city").strip()
            if looks_like_anchor(city) or is_invalid_city_candidate(city):
                continue
            return city
    return None


def extract_known_city(text: str) -> str | None:
    for city in sorted(COMMON_CITY_NAMES, key=len, reverse=True):
        pattern = (
            rf"(?:^|[\s，,。；;]|去|到|在|飞|抵达)"
            rf"(?P<city>{re.escape(city)})(?:市)?"
            rf"(?=$|[\s，,。；;]|\d|[零一二两三四五六七八九十]+(?:天|日)|周末|玩|旅行|旅游|出差|待)"
        )
        if re.search(pattern, text):
            return city
    return None


def extract_trip_days(text: str, lines: list[str]) -> int | None:
    for line in lines:
        match = re.search(r"(?:天数|trip_days|几天)[:：]?\s*(\d+)", line, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))

    for pattern in (r"(\d+)\s*(?:天|日)", r"([零一二两三四五六七八九十]+)\s*(?:天|日)"):
        for match in re.finditer(pattern, text):
            prefix = text[max(0, match.start() - 2):match.start()]
            if prefix.endswith("第") or prefix.endswith("最后"):
                continue
            matched = chinese_number_to_int(match.group(1))
            if matched is not None:
                return matched
    return None


def extract_single_value(lines: list[str], aliases: tuple[str, ...]) -> str | None:
    for line in lines:
        value = extract_value_by_alias(line, aliases)
        if value:
            return value
    return None


def extract_list_value(lines: list[str], aliases: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for line in lines:
        extracted = extract_value_by_alias(line, aliases)
        if extracted:
            values.extend(split_items(extracted))
    return values


def extract_availability_windows(lines: list[str]) -> list[AvailabilityWindow]:
    windows: list[AvailabilityWindow] = []
    for line in lines:
        extracted = extract_value_by_alias(line, KEY_ALIASES["availability_windows"])
        if not extracted:
            continue

        for part in split_items(extracted):
            windows.append(parse_availability_window(part))

    return [window for window in windows if window.label or window.day or window.available_start or window.available_end]


def parse_availability_window(value: str) -> AvailabilityWindow:
    match = re.search(
        r"(?:(?:day|Day)\s*(?P<day>\d+)\s*)?(?P<label>[^0-9]*)?\s*(?P<start>\d{1,2}:\d{2})?\s*(?:-|到|–|—)?\s*(?P<end>\d{1,2}:\d{2})?",
        value,
    )
    if not match:
        return AvailabilityWindow(label=value.strip() or None)

    label = (match.group("label") or value).strip() or None
    return AvailabilityWindow(
        day=int(match.group("day")) if match.group("day") else None,
        label=label,
        available_start=match.group("start"),
        available_end=match.group("end"),
    )


def extract_value_by_alias(line: str, aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        pattern = rf"^{re.escape(alias)}\s*[:：]\s*(.+)$"
        match = re.match(pattern, line, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def split_items(value: str) -> list[str]:
    parts = re.split(r"[，,、/；;]", value)
    return [part.strip() for part in parts if part.strip()]


def split_text_clauses(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[\n\r，,。！？；;]\s*", text) if part.strip()]


def split_free_text_items(value: str) -> list[str]:
    parts = re.split(r"[，,、/；;]|(?:\s*(?:和|及|以及|还有)\s*)", value)
    return [clean_item_text(part) for part in parts if clean_item_text(part)]


def clean_item_text(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"^(?:城市|偏好|景点|餐厅|酒店|到达|离开|可用时间|固定(?:安排)?)\s*[:：]\s*", "", cleaned)
    cleaned = re.sub(
        r"^(?:周末|这周末|下周末|上午|中午|下午|傍晚|晚上|夜里|夜晚)?(?:我(?:们)?|咱们)?(?:已经)?(?:主要|比较|偏)?(?:还|也|再)?(?:想加上|想去|想逛|想看看|想看|想吃|喜欢|偏好|最好|希望|安排|加上|再加上|加个|再去|去|逛|看看|看|吃点|吃)\s*",
        "",
        cleaned,
    )
    cleaned = re.sub(r"^(?:著名的|有名的|当地的|本地的)\s*", "", cleaned)
    cleaned = re.sub(r"^[:：]\s*", "", cleaned)
    cleaned = re.sub(r"(?:吧|呀|呢|一下|一些|一点)$", "", cleaned)
    return cleaned.strip()


def chinese_number_to_int(value: str) -> int | None:
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.isdigit():
        return int(normalized)
    if normalized == "十":
        return 10
    if "十" in normalized:
        left, _, right = normalized.partition("十")
        tens = CHINESE_NUMBER_MAP.get(left, 1) if left else 1
        ones = CHINESE_NUMBER_MAP.get(right, 0) if right else 0
        return tens * 10 + ones
    if len(normalized) == 1:
        return CHINESE_NUMBER_MAP.get(normalized)
    return None


def looks_like_anchor(value: str) -> bool:
    normalized = value.strip()
    return any(keyword in normalized for keyword in ANCHOR_SUFFIX_KEYWORDS)


def is_invalid_city_candidate(value: str) -> bool:
    normalized = value.strip()
    return normalized.startswith(
        ("第一", "第二", "第三", "最后", "希望", "每天", "某天", "周", "想")
    ) or normalized in {"得晚"}


def is_generic_interest_token(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in GENERIC_INTEREST_KEYWORDS:
        return True
    # Keep named places such as "国家海洋博物馆"; only short/generic wording should
    # become preference text instead of a concrete seed POI.
    return len(normalized) <= 4 and any(keyword in normalized for keyword in GENERIC_INTEREST_KEYWORDS)


def preference_from_non_place_scenic_seed(value: str) -> str | None:
    """
    Convert phrases like "主要想看历史文化" into preferences, not POI seeds.

    The LLM/fallback parser may interpret broad interests as scenic_spots because
    the user used a verb such as "想看". Named places still pass through: e.g.
    "陕西历史博物馆" is long and specific, while "历史文化" is a generic intent.
    """
    raw = value.strip()
    cleaned = clean_item_text(raw)
    if not cleaned:
        return None
    if looks_like_anchor(cleaned) or looks_like_restaurant_name(cleaned):
        return None
    if is_generic_interest_token(cleaned):
        return cleaned
    if (
        any(token in raw for token in ("想看", "想看看", "想了解", "主要", "喜欢", "偏好", "希望"))
        and any(keyword in cleaned for keyword in GENERIC_INTEREST_KEYWORDS)
        and len(cleaned) <= 6
    ):
        return cleaned
    return None


def looks_like_trip_scope_item(value: str, city: str | None = None) -> bool:
    normalized = value.strip()
    if not normalized:
        return True
    if city and city in normalized and any(token in normalized for token in ("周末", "旅行", "旅游", "出游", "玩")):
        return True
    day_count_pattern = r"(?:\d+|[零一二两三四五六七八九十]+)\s*(?:天|日)"
    if city and normalized.startswith(city) and re.search(day_count_pattern, normalized):
        return True
    return bool(re.search(r"(?:周末|旅行|旅游|出游|玩).{0,12}" + day_count_pattern, normalized))


def is_soft_time_preference_clause(value: str) -> bool:
    normalized = value.strip().casefold()
    return any(keyword in normalized for keyword in SOFT_TIME_PREFERENCE_KEYWORDS)


def looks_like_restaurant_name(value: str) -> bool:
    normalized = value.strip().casefold()
    return any(keyword in normalized for keyword in RESTAURANT_NAME_HINTS)


def has_scenic_seed_action(clause: str) -> bool:
    return any(
        token in clause
        for token in ("想去", "想逛", "想看看", "想看", "打卡", "加上", "再加上", "再去")
    )


def has_restaurant_seed_action(clause: str) -> bool:
    return any(token in clause for token in ("想吃", "吃", "餐厅", "饭店", "菜馆", "咖啡"))


def is_seed_continuation_clause(clause: str) -> bool:
    normalized = clause.strip()
    if not normalized:
        return False
    return not any(
        token in normalized
        for token in (
            "准备",
            "到站",
            "到达",
            "抵达",
            "第一天",
            "第二天",
            "第三天",
            "最后一天",
            "不想",
            "不要",
            "别",
            "帮我",
            "补",
            "回去",
            "返程",
            "坐高铁",
            "坐火车",
            "坐飞机",
        )
    )


def extract_inline_scenic_spots(text: str, city: str | None = None) -> list[str]:
    scenic_spots: list[str] = []
    continuing_scenic_seed = False

    for clause in split_text_clauses(text):
        if has_restaurant_seed_action(clause):
            continuing_scenic_seed = False
            continue
        if has_scenic_seed_action(clause):
            continuing_scenic_seed = True
        elif not continuing_scenic_seed or not is_seed_continuation_clause(clause):
            continuing_scenic_seed = False
            continue

        for item in split_free_text_items(clause):
            if looks_like_trip_scope_item(item, city=city):
                continue
            if looks_like_anchor(item) or looks_like_restaurant_name(item):
                continue
            if preference_from_non_place_scenic_seed(item) is not None:
                continue
            if is_generic_interest_token(item):
                continue
            scenic_spots.append(item)

    return scenic_spots


def extract_inline_restaurants(text: str) -> list[str]:
    restaurants: list[str] = []
    continuing_restaurant_seed = False

    for clause in split_text_clauses(text):
        if has_scenic_seed_action(clause):
            continuing_restaurant_seed = False
            continue
        if has_restaurant_seed_action(clause):
            continuing_restaurant_seed = True
        elif not continuing_restaurant_seed or not is_seed_continuation_clause(clause):
            continuing_restaurant_seed = False
            continue

        for item in split_free_text_items(clause):
            if looks_like_restaurant_name(item):
                restaurants.append(item)

    return restaurants


def extract_inline_preferences(text: str) -> list[str]:
    preferences: list[str] = []

    for clause in split_text_clauses(text):
        if extract_value_by_alias(clause, KEY_ALIASES["preferences"]) is not None:
            continue

        if is_hard_timing_constraint_clause(clause):
            continue

        if any(token in clause for token in ("想吃", "吃点")):
            preferences.extend(
                item for item in split_free_text_items(clause)
                if not looks_like_restaurant_name(item)
            )
            continue

        if any(token in clause for token in ("喜欢", "偏好", "最好", "希望")):
            preferences.extend(split_free_text_items(clause))
            continue

        if "想逛" in clause:
            items = split_free_text_items(clause)
            if items and all(is_generic_interest_token(item) for item in items):
                preferences.extend(items)
                continue

        if any(token in clause for token in ("想看", "想看看", "想了解")):
            items = split_free_text_items(clause)
            preference_items = [
                preference
                for item in items
                if (preference := preference_from_non_place_scenic_seed(item)) is not None
            ]
            if preference_items and len(preference_items) == len(items):
                preferences.extend(preference_items)
                continue

        if any(token in clause for token in ("不要太赶", "别太赶", "不要排太满", "别排太满", "休息", "留给", "早起", "起太早", "最多安排")):
            preferences.append(clean_soft_preference_clause(clause))
            continue

        if "吃" in clause:
            items = split_free_text_items(clause)
            if items and not any(looks_like_restaurant_name(item) for item in items):
                preferences.extend(items)
                continue

        if is_soft_time_preference_clause(clause):
            preferences.append(clean_soft_preference_clause(clause))

    return preferences


def extract_inline_arrival_anchor(text: str) -> str | None:
    anchor_body_pattern = rf"[\u4e00-\u9fffA-Za-z0-9]{{0,20}}(?:{'|'.join(re.escape(keyword) for keyword in ANCHOR_SUFFIX_KEYWORDS)})"
    patterns = [
        rf"(?:到站为|到站是|到达站为|抵达站为)\s*(?P<anchor>{anchor_body_pattern})",
        rf"(?:到达|抵达|落地|飞到|到)(?P<anchor>{anchor_body_pattern})",
    ]
    for clause in split_text_clauses(text):
        if not any(token in clause for token in ("到", "到达", "抵达", "落地", "飞到")):
            continue
        if any(token in clause for token in ("离开", "返程", "回程", "走", "回去")) or looks_like_departure_clause(clause):
            continue
        for pattern in patterns:
            match = re.search(pattern, clause)
            if match:
                return match.group("anchor").strip()
    return None


def extract_inline_departure_anchor(text: str) -> str | None:
    anchor_suffix_pattern = "|".join(re.escape(keyword) for keyword in ANCHOR_SUFFIX_KEYWORDS)
    anchor_body_pattern = rf"[\u4e00-\u9fffA-Za-z0-9]{{0,20}}(?:{anchor_suffix_pattern})"
    patterns = [
        rf"(?:去|前往|赶去|离开|返程|回程|回去|走)\s*(?P<anchor>{anchor_body_pattern})",
        rf"(?:要到|到)\s*(?P<anchor>{anchor_body_pattern})",
    ]
    for clause in split_text_clauses(text):
        if not any(token in clause for token in ("离开", "返程", "回程", "回去", "前", "走", "赶", "要到")):
            continue
        for pattern in patterns:
            match = re.search(pattern, clause)
            if match:
                return match.group("anchor").strip()
    return None


def extract_inline_availability_windows(
    text: str,
    *,
    trip_days: int | None,
    weekday_day_map: dict[str, int],
) -> list[AvailabilityWindow]:
    windows: list[AvailabilityWindow] = []

    for clause in split_text_clauses(text):
        day, label = extract_day_reference(
            clause,
            trip_days=trip_days,
            weekday_day_map=weekday_day_map,
        )

        if looks_like_arrival_clause(clause) and not looks_like_departure_clause(clause):
            start_time = extract_boundary_time(clause, kind="start")
            if start_time is not None and (day is not None or label is not None):
                windows.append(
                    AvailabilityWindow(
                        day=day,
                        label=label,
                        available_start=start_time,
                    )
                )

        if looks_like_departure_clause(clause):
            end_time = extract_boundary_time(clause, kind="end")
            if end_time is not None and (day is not None or label is not None):
                windows.append(
                    AvailabilityWindow(
                        day=day,
                        label=label,
                        available_end=end_time,
                    )
                )

        if is_unavailable_period_clause(clause):
            period_window = infer_period_unavailable_window(clause)
            if period_window is not None and (day is not None or label is not None):
                available_start, available_end = period_window
                windows.append(
                    AvailabilityWindow(
                        day=day,
                        label=label,
                        available_start=available_start,
                        available_end=available_end,
                    )
                )

    return windows


def extract_day_reference(
    clause: str,
    *,
    trip_days: int | None,
    weekday_day_map: dict[str, int],
) -> tuple[int | None, str | None]:
    explicit_match = re.search(r"第([零一二两三四五六七八九十\d]+)天", clause)
    if explicit_match:
        day_value = chinese_number_to_int(explicit_match.group(1))
        if day_value is not None:
            return day_value, f"第{day_value}天"

    if any(token in clause for token in ("第一天", "首日")):
        return 1, "第一天"

    if any(token in clause for token in ("最后一天", "末日")):
        return trip_days, "最后一天"

    weekday_match = re.search(r"(周[一二三四五六日天末]|星期[一二三四五六日天])", clause)
    if weekday_match:
        period = extract_period_token(clause)
        label = weekday_match.group(1)
        if period:
            label = f"{label}{period}"
        return weekday_day_map.get(weekday_match.group(1)), label

    if "某天" in clause:
        period = extract_period_token(clause)
        label = "某天"
        if period:
            label = f"{label}{period}"
        return None, label

    return None, None


def looks_like_arrival_clause(clause: str) -> bool:
    return (
        any(token in clause for token in ("到达", "抵达", "落地", "飞到", "到得"))
        or re.search(r"(?:清晨|早上|上午|中午|下午|傍晚|晚上|夜里|夜晚)到(?:$|[，,。；;])", clause)
        is not None
        or (
            "到" in clause
            and not re.search(r"点\s*(?:-|到|至|–|—)\s*\d", clause)
            and (looks_like_anchor(clause) or re.search(r"到[\u4e00-\u9fff]{2,8}", clause) is not None)
        )
    ) and not any(token in clause for token in ("离开", "返程", "回程", "回去", "前要去"))


def looks_like_departure_clause(clause: str) -> bool:
    return (
        any(token in clause for token in ("离开", "返程", "回程", "回去", "走", "赶去", "就走"))
        or ("前" in clause and ("要到" in clause or looks_like_anchor(clause)))
    )


def is_unavailable_period_clause(clause: str) -> bool:
    return any(
        token in clause
        for token in ("别的安排", "其他安排", "有安排", "没空", "不方便")
    ) and extract_period_token(clause) is not None


def is_hard_timing_constraint_clause(clause: str) -> bool:
    return (
        looks_like_arrival_clause(clause)
        or looks_like_departure_clause(clause)
        or is_unavailable_period_clause(clause)
        or looks_like_fixed_event_clause(clause)
    )


def extract_period_token(clause: str) -> str | None:
    for token in ("清晨", "早上", "上午", "中午", "下午", "傍晚", "晚上", "夜里", "夜晚"):
        if token in clause:
            return token
    if re.search(r"(?:周[一二三四五六日天末]|星期[一二三四五六日天])晚", clause):
        return "晚上"
    return None


def extract_boundary_time(clause: str, *, kind: str) -> str | None:
    explicit_time = extract_explicit_time(clause)
    if explicit_time is not None:
        return explicit_time

    if kind == "start" and any(token in clause for token in ("到得晚", "到得比较晚", "第一天晚到")):
        return "18:00"

    period = extract_period_token(clause)
    if period is None:
        return None

    if kind == "start":
        return {
            "清晨": "07:00",
            "早上": "09:00",
            "上午": "09:00",
            "中午": "12:00",
            "下午": "13:00",
            "傍晚": "17:00",
            "晚上": "18:00",
            "夜里": "20:00",
            "夜晚": "20:00",
        }.get(period)

    return {
        "清晨": "09:00",
        "早上": "12:00",
        "上午": "12:00",
        "中午": "13:00",
        "下午": "17:00",
        "傍晚": "18:00",
        "晚上": "20:00",
        "夜里": "21:00",
        "夜晚": "21:00",
    }.get(period)


def extract_explicit_time(clause: str) -> str | None:
    colon_match = re.search(r"(\d{1,2})[:：](\d{2})", clause)
    if colon_match:
        return f"{int(colon_match.group(1)):02d}:{int(colon_match.group(2)):02d}"

    point_match = re.search(r"([零一二两三四五六七八九十\d]{1,3})点(半)?", clause)
    if point_match:
        hour = chinese_number_to_int(point_match.group(1))
        if hour is None:
            return None
        period = extract_period_token(clause)
        if period in {"下午", "傍晚", "晚上", "夜里", "夜晚"} and 0 <= hour < 12:
            hour += 12
        if point_match.group(2):
            return f"{hour:02d}:30"
        return f"{hour:02d}:00"

    return None


def extract_time_range(clause: str) -> tuple[str | None, str | None]:
    colon_match = re.search(r"(\d{1,2}[:：]\d{2})\s*(?:-|到|至|–|—)\s*(\d{1,2}[:：]\d{2})", clause)
    if colon_match:
        return (
            normalize_clock_text(colon_match.group(1)),
            normalize_clock_text(colon_match.group(2)),
        )

    point_match = re.search(
        r"([零一二两三四五六七八九十\d]{1,3})\s*点(半)?\s*(?:-|到|至|–|—)\s*([零一二两三四五六七八九十\d]{1,3})\s*点(半)?",
        clause,
    )
    if point_match:
        start_time = normalize_hour_token(
            point_match.group(1),
            half=bool(point_match.group(2)),
            clause=clause,
        )
        end_time = normalize_hour_token(
            point_match.group(3),
            half=bool(point_match.group(4)),
            clause=clause,
        )
        return start_time, end_time

    single_time = extract_explicit_time(clause)
    if single_time is None:
        return None, None

    period = extract_period_token(clause)
    if period is not None:
        _period_start, period_end = period_to_window(period)
        return single_time, max_clock_text(single_time, period_end)
    return single_time, add_minutes_to_clock_text(single_time, 120)


def normalize_clock_text(value: str) -> str:
    hour_text, minute_text = re.split(r"[:：]", value.strip(), maxsplit=1)
    return f"{int(hour_text):02d}:{int(minute_text):02d}"


def normalize_hour_token(value: str, *, half: bool, clause: str) -> str | None:
    hour = chinese_number_to_int(value)
    if hour is None:
        return None
    period = extract_period_token(clause)
    if period in {"下午", "傍晚", "晚上", "夜里", "夜晚"} and 0 <= hour < 12:
        hour += 12
    return f"{hour:02d}:{'30' if half else '00'}"


def period_to_window(period: str) -> tuple[str, str]:
    return {
        "清晨": ("07:00", "09:00"),
        "早上": ("09:00", "12:00"),
        "上午": ("09:00", "12:00"),
        "中午": ("12:00", "13:00"),
        "下午": ("13:00", "17:00"),
        "傍晚": ("17:00", "18:00"),
        "晚上": ("18:00", "21:00"),
        "夜里": ("20:00", "21:00"),
        "夜晚": ("20:00", "21:00"),
    }[period]


def infer_period_unavailable_window(clause: str) -> tuple[str | None, str | None] | None:
    period = extract_period_token(clause)
    if period is None:
        return None

    if period in {"晚上", "夜里", "夜晚", "傍晚"}:
        return "09:00", "17:30"
    if period == "下午":
        return "09:00", "13:00"
    if period in {"早上", "上午"}:
        return "12:00", "21:00"
    if period == "中午":
        return "09:00", "12:00"
    return None


def max_clock_text(left: str | None, right: str | None) -> str | None:
    if left is None:
        return right
    if right is None:
        return left
    return left if left >= right else right


def add_minutes_to_clock_text(value: str, minutes: int) -> str:
    hour_text, minute_text = value.split(":", 1)
    total_minutes = int(hour_text) * 60 + int(minute_text) + minutes
    total_minutes = min(total_minutes, 23 * 60 + 59)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def build_weekday_day_map(text: str) -> dict[str, int]:
    seen: list[str] = []
    for clause in split_text_clauses(text):
        for match in re.findall(r"(周[一二三四五六日天末]|星期[一二三四五六日天])", clause):
            if match not in seen:
                seen.append(match)
    return {weekday: index + 1 for index, weekday in enumerate(seen)}


def looks_like_fixed_event_clause(clause: str) -> bool:
    if "安排" in clause and not any(
        token in clause
        for token in ("固定安排", "固定行程", "有安排", "别的安排", "其他安排", "没空", "不方便")
    ):
        return any(keyword in clause for keyword in FIXED_EVENT_NAME_KEYWORDS if keyword != "安排")
    return any(keyword in clause for keyword in FIXED_EVENT_NAME_KEYWORDS)


def is_non_actionable_generic_fixed_event(event: ParsedFixedEvent) -> bool:
    """
    Drop LLM/fallback artifacts such as "有安排" when they have no day.

    "晚上安排吃饭和夜游" is a soft planning preference; it should become
    completion intent, not an undated fixed event that the deterministic
    scheduler cannot place safely.
    """
    normalized_name = event.name.strip()
    if normalized_name not in {"有安排", "安排"}:
        return False
    return event.fixed_day is None


def extract_inline_fixed_events(
    text: str,
    *,
    trip_days: int | None,
    weekday_day_map: dict[str, int],
) -> list[ParsedFixedEvent]:
    fixed_events: list[ParsedFixedEvent] = []

    for clause in split_text_clauses(text):
        if not looks_like_fixed_event_clause(clause):
            continue
        if looks_like_arrival_clause(clause) or looks_like_departure_clause(clause):
            continue

        fixed_day, _label = extract_day_reference(
            clause,
            trip_days=trip_days,
            weekday_day_map=weekday_day_map,
        )
        start_time, end_time = extract_time_range(clause)

        if start_time is None and end_time is None:
            period = extract_period_token(clause)
            if period is not None:
                start_time, end_time = period_to_window(period)

        event_name = extract_fixed_event_name(clause)
        fixed_events.append(
            ParsedFixedEvent(
                name=event_name,
                fixed_day=fixed_day,
                fixed_time_start=start_time,
                fixed_time_end=end_time,
                category=infer_fixed_event_category(clause),
            )
        )

    return fixed_events


def extract_fixed_event_name(clause: str) -> str:
    if "见朋友" in clause:
        return "见朋友"
    if "见面" in clause:
        return "见面"
    if "预约" in clause:
        return "预约"
    if "演出" in clause:
        return "看演出"
    if "音乐剧" in clause:
        return "看音乐剧"
    if "话剧" in clause:
        return "看话剧"
    if "会议" in clause:
        return "会议"
    if "固定行程" in clause:
        return "固定行程"
    if "安排" in clause:
        return "有安排"
    return clean_preference_clause(clause)


def infer_fixed_event_category(clause: str) -> str:
    if looks_like_anchor(clause):
        return "transport"
    if any(token in clause for token in ("演出", "音乐剧", "话剧", "活动", "表演")):
        return "activity"
    if any(token in clause for token in ("见朋友", "见面", "预约", "会议", "安排")):
        return "other"
    return "other"


def clean_preference_clause(clause: str) -> str:
    cleaned = clause.strip()
    cleaned = re.sub(r"^(?:第一天|第二天|第三天|最后一天|周[一二三四五六日天末]|星期[一二三四五六日天]|某天)", "", cleaned)
    cleaned = re.sub(r"^(?:上午|中午|下午|傍晚|晚上|夜里|夜晚)", "", cleaned)
    cleaned = cleaned.strip("，,。；; ")
    return cleaned or clause.strip()


def clean_soft_preference_clause(clause: str) -> str:
    cleaned = clause.strip()
    cleaned = re.sub(r"^(?:希望|最好|尽量)\s*", "", cleaned)
    cleaned = cleaned.strip("，,。；; ")
    return cleaned or clause.strip()


def extract_fixed_events(lines: list[str]) -> list[ParsedFixedEvent]:
    fixed_events: list[ParsedFixedEvent] = []
    for line in lines:
        fixed_value = extract_value_by_alias(line, KEY_ALIASES["fixed"])
        if not fixed_value:
            continue

        match = re.search(
            r"(?:(?:day|Day)\s*)?(?P<day>\d+)?\s*(?P<start>\d{1,2}:\d{2})?\s*(?:-|到|–|—)?\s*(?P<end>\d{1,2}:\d{2})?\s*(?P<name>.+)",
            fixed_value,
        )
        if not match:
            fixed_events.append(ParsedFixedEvent(name=fixed_value))
            continue

        raw_name = (match.group("name") or "").strip()
        fixed_events.append(
            ParsedFixedEvent(
                name=raw_name or fixed_value,
                fixed_day=int(match.group("day")) if match.group("day") else None,
                fixed_time_start=match.group("start"),
                fixed_time_end=match.group("end"),
            )
        )

    return fixed_events


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
