from __future__ import annotations

import re
from datetime import time

from app.schemas import AvailabilityWindow, ItineraryRequest, RestaurantInput, ScenicSpotInput, TravelMode
from app.schemas.intent import ParsedTripIntentResponse
from app.services.nl_parser import parse_trip_text

from app.schemas.trip_compiler import (
    SourceFragment,
    TravelIntent,
    TripCompilerCompileResponse,
    TripCompilerConstraint,
    TripCompilerFixedEvent,
    TRIP_COMPILER_MAX_DAYS,
    TRIP_COMPILER_MIN_DAYS,
    TripCompilerPlace,
    TripCompilerPreference,
    TripCompilerUnresolvedItem,
    stable_compiler_id,
)


def compile_travel_intent(text: str) -> TripCompilerCompileResponse:
    """Compile language into an editable contract without scheduling anything."""

    from app.services.constraint_planning import build_constraint_graph, find_conflict_cores

    normalized = text.strip()
    parsed = parse_trip_text(normalized)
    fragments = _source_fragments(normalized)
    source_ids = [fragment.stable_id for fragment in fragments[:1]]
    trip_days = _supported_trip_days(parsed.trip_days)
    pace = "relaxed" if any(token in normalized for token in ("不要太赶", "不想太赶", "别太累", "轻松", "不想太累")) else "intensive" if any(token in normalized for token in ("紧凑", "多安排", "尽量多")) else "balanced"
    must, optional = _places(parsed, normalized, fragments)
    fixed_events = _fixed_events(parsed, normalized, fragments)
    constraints = _constraints(parsed, normalized, fragments, trip_days=trip_days)
    avoid_items = _avoid_items(normalized, fragments)
    unresolved = _unresolved(parsed, normalized, fixed_events, source_ids, trip_days=trip_days)
    conflicts = _conflicts(parsed, normalized, fixed_events)
    intent = TravelIntent(
        destination=parsed.city,
        date_window={"start_date": None, "end_date": None, "arrival_time": _arrival_time(normalized), "departure_time": _departure_time(normalized)},
        trip_days=trip_days,
        pace=pace,
        must_visit_places=must,
        optional_places=optional,
        fixed_events=fixed_events,
        preferences=[
            TripCompilerPreference(stable_id=stable_compiler_id("preference", value, index), value=value, confidence=0.8, source_fragment_ids=_matching_source_ids(fragments, value))
            for index, value in enumerate(_unique([*parsed.preferences, *parsed.style_preferences]))
        ],
        constraints=constraints,
        avoid_items=avoid_items,
        unresolved_items=unresolved,
        source_fragments=fragments,
        travel_mode=_travel_mode(normalized),
    )
    graph = build_constraint_graph(intent)
    conflict_cores = find_conflict_cores(intent, graph)
    conflicts = [core.explanation for core in conflict_cores] or conflicts
    status = "hard_conflict" if conflict_cores else "needs_confirmation" if intent.has_blocking_unresolved_items else "ready"
    return TripCompilerCompileResponse(intent=intent, status=status, conflicts=conflicts, conflict_cores=[core.model_dump(mode="json") for core in conflict_cores])


def build_itinerary_request(intent: TravelIntent) -> ItineraryRequest:
    """Map the confirmed compiler contract into the established scheduler input."""

    if not intent.destination or not intent.trip_days:
        raise ValueError("destination and trip_days are required before planning")
    if not TRIP_COMPILER_MIN_DAYS <= intent.trip_days <= TRIP_COMPILER_MAX_DAYS:
        raise ValueError(f"AI Trip Compiler V1 supports {TRIP_COMPILER_MIN_DAYS} to {TRIP_COMPILER_MAX_DAYS} days.")
    if intent.has_blocking_unresolved_items:
        raise ValueError("intent has unresolved blocking information")
    if any(event.day is None or event.start_time is None or event.end_time is None for event in intent.fixed_events):
        raise ValueError("fixed events require a day and a complete time range")
    scenic = [
        ScenicSpotInput(name=place.name, intent_ownership=place.ownership)
        for place in [*intent.must_visit_places, *intent.optional_places]
    ]
    for event in intent.fixed_events:
        start = time.fromisoformat(event.start_time or "00:00")
        end = time.fromisoformat(event.end_time or "00:00")
        scenic.append(
            ScenicSpotInput(
                name=event.name,
                fixed_day=event.day,
                fixed_time_start=start,
                fixed_time_end=end,
                # A fixed reservation occupies its confirmed window. Passing the
                # provider/default POI duration here would make the scheduler
                # reject a valid reservation as longer than its own time range.
                resolved_duration_minutes=((end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)),
            )
        )
    availability: list[AvailabilityWindow] = []
    for constraint in intent.constraints:
        parsed = _availability_from_constraint(constraint.value)
        if parsed is not None:
            availability.append(parsed)
    return ItineraryRequest(
        city=intent.destination,
        trip_days=intent.trip_days,
        scenic_spots=scenic,
        restaurants=[],
        availability_windows=availability,
        preferences=[item.value for item in intent.preferences],
        rejected_scenic_spots=[item.value for item in intent.avoid_items],
        travel_mode=intent.travel_mode,
        auto_fill_sparse_days=True,
    )


def _places(parsed: ParsedTripIntentResponse, text: str, fragments: list[SourceFragment]) -> tuple[list[TripCompilerPlace], list[TripCompilerPlace]]:
    must: list[TripCompilerPlace] = []
    optional: list[TripCompilerPlace] = []
    explicit_must, explicit_optional = _explicit_places(text)
    names = _unique([*explicit_must, *explicit_optional, *parsed.scenic_spots])
    for index, name in enumerate(names):
        if not _usable_place_name(name):
            continue
        optional_hint = name in explicit_optional or (name not in explicit_must and _place_is_optional(text, name))
        ownership = "user_optional" if optional_hint else "user_must"
        item = TripCompilerPlace(
            stable_id=stable_compiler_id("place", name, index), name=name, ownership=ownership,
            confidence=0.85, source_fragment_ids=_matching_source_ids(fragments, name),
        )
        (optional if optional_hint else must).append(item)
    return must, optional


def _fixed_events(parsed: ParsedTripIntentResponse, text: str, fragments: list[SourceFragment]) -> list[TripCompilerFixedEvent]:
    events: list[TripCompilerFixedEvent] = []
    extracted = _explicit_fixed_events(text)
    raw_events = extracted or [(event.name, event.fixed_day, event.fixed_time_start, event.fixed_time_end) for event in parsed.fixed_events]
    for index, (name, day, start_time, end_time) in enumerate(raw_events):
        events.append(TripCompilerFixedEvent(
            stable_id=stable_compiler_id("fixed", name, index), name=name,
            day=day, start_time=start_time, end_time=end_time,
            fixed_reason="你明确说明这是预约或固定时间安排。", confidence=0.9,
            source_fragment_ids=_matching_source_ids(fragments, name),
        ))
    return events


def _constraints(
    parsed: ParsedTripIntentResponse,
    text: str,
    fragments: list[SourceFragment],
    *,
    trip_days: int | None,
) -> list[TripCompilerConstraint]:
    constraints: list[TripCompilerConstraint] = []
    for index, window in enumerate(parsed.availability_windows):
        day = trip_days if window.available_end and ("周日" in text or "星期日" in text) and trip_days else window.day or index + 1
        bits = [f"第 {day} 天"]
        if window.available_start: bits.append(f"{window.available_start} 后")
        if window.available_end: bits.append(f"{window.available_end} 前")
        constraints.append(TripCompilerConstraint(stable_id=stable_compiler_id("availability", ":".join(bits), index), value=" ".join(bits), kind="availability", source_fragment_ids=_matching_source_ids(fragments, window.available_start or window.available_end or str(day))))
    arrival = _arrival_time(text)
    if arrival:
        constraints.append(TripCompilerConstraint(stable_id=stable_compiler_id("arrival", arrival), value=f"第 1 天 {arrival} 后可开始安排", kind="arrival", source_fragment_ids=_matching_source_ids(fragments, arrival)))
    departure = _departure_time(text)
    if departure:
        day = trip_days or 1
        constraints.append(TripCompilerConstraint(stable_id=stable_compiler_id("departure", departure), value=f"第 {day} 天 {departure} 前需要结束行程", kind="departure", source_fragment_ids=_matching_source_ids(fragments, departure)))
    return constraints


def _avoid_items(text: str, fragments: list[SourceFragment]) -> list[TripCompilerConstraint]:
    values = [match.strip("。 ，,；;") for match in re.findall(r"(?:不想去|不去|避开|不要安排)([^。；;，,\n]{1,30})", text)]
    return [TripCompilerConstraint(stable_id=stable_compiler_id("avoid", value, index), value=value, kind="avoid", source_fragment_ids=_matching_source_ids(fragments, value)) for index, value in enumerate(_unique(values))]


def _unresolved(
    parsed: ParsedTripIntentResponse,
    text: str,
    events: list[TripCompilerFixedEvent],
    source_ids: list[str],
    *,
    trip_days: int | None,
) -> list[TripCompilerUnresolvedItem]:
    unresolved: list[TripCompilerUnresolvedItem] = []
    if not parsed.city:
        unresolved.append(TripCompilerUnresolvedItem(stable_id="unresolved_destination", field="destination", question="这次想去哪个城市？", blocking=True, source_fragment_ids=source_ids))
    if parsed.trip_days is not None and trip_days is None:
        unresolved.append(TripCompilerUnresolvedItem(
            stable_id="unresolved_trip_days_v1_limit",
            field="trip_days",
            question=f"当前版本先支持 {TRIP_COMPILER_MIN_DAYS} 到 {TRIP_COMPILER_MAX_DAYS} 天的行程，请调整旅行天数后再继续。",
            blocking=True,
            source_fragment_ids=source_ids,
        ))
    elif not trip_days:
        unresolved.append(TripCompilerUnresolvedItem(stable_id="unresolved_trip_days", field="trip_days", question="准备玩几天？", blocking=True, source_fragment_ids=source_ids))
    if "周末" in text and not trip_days:
        unresolved.append(TripCompilerUnresolvedItem(stable_id="unresolved_weekend", field="date_window", question="“周末”具体是哪几天？", blocking=False, source_fragment_ids=source_ids))
    for event in events:
        if event.day is None or event.start_time is None or event.end_time is None:
            unresolved.append(TripCompilerUnresolvedItem(stable_id=f"unresolved_{event.stable_id}", field="fixed_events", question=f"请补充“{event.name}”的具体日期和完整时间。", blocking=True, source_fragment_ids=source_ids))
    if not parsed.scenic_spots and parsed.city:
        unresolved.append(TripCompilerUnresolvedItem(stable_id="unresolved_place_preference", field="places", question="更想看园林、历史文化、自然景观，还是城市街区？", blocking=False, source_fragment_ids=source_ids))
    return unresolved


def _supported_trip_days(value: int | None) -> int | None:
    if value is None or not TRIP_COMPILER_MIN_DAYS <= value <= TRIP_COMPILER_MAX_DAYS:
        return None
    return value


def _conflicts(parsed: ParsedTripIntentResponse, text: str, events: list[TripCompilerFixedEvent]) -> list[str]:
    conflicts: list[str] = []
    arrival = _arrival_time(text) or _arrival_time_from_parsed(parsed)
    for event in events:
        if event.day == 1 and event.start_time and arrival and arrival > event.start_time:
            conflicts.append(f"到达时间晚于固定安排“{event.name}”的开始时间。")
    return conflicts


def _arrival_time_from_parsed(parsed: ParsedTripIntentResponse) -> str | None:
    for window in parsed.availability_windows:
        if window.day == 1 and window.available_start:
            return window.available_start
    return None


def _explicit_places(text: str) -> tuple[list[str], list[str]]:
    must: list[str] = []
    optional: list[str] = []
    for match in re.finditer(r"(?:已经)?(?:想去|必去)([^。；;\n]+)", text):
        section = re.split(r"(?:朋友推荐|但不是必须|不是必须|如果有空|另外)", match.group(1))[0]
        must.extend(_split_place_names(section))
    for match in re.finditer(r"(?:朋友推荐|推荐)([^。；;，,\n]+)", text):
        optional.extend(_split_place_names(match.group(1)))
    return _unique(must), _unique(optional)


def _split_place_names(value: str) -> list[str]:
    cleaned = value.replace("和", "、").replace("及", "、").replace("与", "、")
    return [item.strip(" ：:，,。") for item in re.split(r"[、，,]", cleaned) if item.strip(" ：:，,。")]


def _usable_place_name(value: str) -> bool:
    if len(value) < 2 or len(value) > 30:
        return False
    return not any(token in value for token in ("朋友推荐", "不是必须", "预约", "周六", "周日", "不想", "想吃", "但"))


def _explicit_fixed_events(text: str) -> list[tuple[str, int | None, str | None, str | None]]:
    events: list[tuple[str, int | None, str | None, str | None]] = []
    for match in re.finditer(r"(?:预约(?:了)?|固定安排(?:是)?)([^。；;，,\n]+)", text):
        name = match.group(1).strip(" ：:")
        if not _usable_place_name(name):
            continue
        context = text[max(0, match.start() - 28): match.end() + 12]
        start, end = _last_time_range(context)
        if start and not end:
            end = f"{(int(start[:2]) + 2) % 24:02d}:{start[3:]}"
        events.append((name, _day_from_context(context) or 1, start, end))
    return events


def _time_range(text: str) -> tuple[str | None, str | None]:
    match = re.search(r"(?:(上午|下午|晚上|中午|早上)\s*)?([零一二三四五六七八九十两\d]+)(?:点|:)(\d{1,2})?\s*(?:到|至|-)?\s*([零一二三四五六七八九十两\d]+)?(?:点|:)?(\d{1,2})?", text)
    if not match:
        return None, None
    meridiem, start_raw, start_minute, end_raw, end_minute = match.groups()
    start_hour = _number(start_raw)
    if start_hour is None:
        return None, None
    start_hour = _apply_meridiem(start_hour, meridiem)
    start = f"{start_hour:02d}:{int(start_minute or 0):02d}"
    if end_raw is None:
        return start, None
    end_hour = _number(end_raw)
    if end_hour is None:
        return start, None
    end_hour = _apply_meridiem(end_hour, meridiem)
    return start, f"{end_hour:02d}:{int(end_minute or 0):02d}"


def _last_time_range(text: str) -> tuple[str | None, str | None]:
    pattern = re.compile(r"(?:(上午|下午|晚上|中午|早上)\s*)?([零一二三四五六七八九十两\d]+)(?:点|:)(\d{1,2})?\s*(?:到|至|-)\s*([零一二三四五六七八九十两\d]+)(?:点|:)(\d{1,2})?")
    matches = list(pattern.finditer(text))
    if matches:
        meridiem, start_raw, start_minute, end_raw, end_minute = matches[-1].groups()
        start_hour, end_hour = _number(start_raw), _number(end_raw)
        if start_hour is not None and end_hour is not None:
            return f"{_apply_meridiem(start_hour, meridiem):02d}:{int(start_minute or 0):02d}", f"{_apply_meridiem(end_hour, meridiem):02d}:{int(end_minute or 0):02d}"
    return _time_range(text)


def _number(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    values = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if value in values:
        return values[value]
    if len(value) == 2 and value[0] == "十" and value[1] in values:
        return 10 + values[value[1]]
    return None


def _apply_meridiem(hour: int, meridiem: str | None) -> int:
    if meridiem in {"下午", "晚上", "中午"} and hour < 12:
        return hour + 12
    return hour


def _day_from_context(text: str) -> int | None:
    if "周六" in text or "星期六" in text:
        return 1
    if "周日" in text or "星期日" in text or "星期天" in text:
        return 2
    if "第一天" in text or "第1天" in text:
        return 1
    if "第二天" in text or "第2天" in text:
        return 2
    return None


def _arrival_time(text: str) -> str | None:
    match = re.search(r"(?:第[一1]天)?(中午|下午|晚上|早上|上午)?\s*([零一二三四五六七八九十两\d]+)(?::|点)(\d{1,2})?\s*(?:到|抵达)", text)
    if not match:
        return None
    hour = _number(match.group(2))
    return f"{_apply_meridiem(hour, match.group(1)):02d}:{int(match.group(3) or 0):02d}" if hour is not None else None


def _departure_time(text: str) -> str | None:
    match = re.search(r"(下午|晚上|早上|上午)?\s*([零一二三四五六七八九十两\d]+)(?::|点)(\d{1,2})?\s*(?:前|以后)?(?:要|需)?\s*(?:回到|到|离开|坐高铁|坐火车|飞走)", text)
    if not match:
        return None
    hour = _number(match.group(2))
    return f"{_apply_meridiem(hour, match.group(1)):02d}:{int(match.group(3) or 0):02d}" if hour is not None else None


def _travel_mode(text: str) -> TravelMode | None:
    if "高铁" in text:
        return TravelMode.HIGH_SPEED_RAIL
    if "飞机" in text or "机场" in text:
        return TravelMode.AIRPLANE
    if "火车" in text:
        return TravelMode.RAIL
    return None


def _place_is_optional(text: str, name: str) -> bool:
    index = text.find(name)
    nearby = text[max(0, index - 18): index + len(name) + 18] if index >= 0 else text
    return any(token in nearby for token in ("不是必须", "不一定", "可调整", "朋友推荐", "有空"))


def _availability_from_constraint(value: str) -> AvailabilityWindow | None:
    match = re.match(r"第\s*(\d+)\s*天\s*(?:(\d{2}:\d{2}) 后)?\s*(?:(\d{2}:\d{2}) 前)?", value)
    if not match:
        return None
    return AvailabilityWindow(day=int(match.group(1)), available_start=match.group(2), available_end=match.group(3))


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    return [value for value in values if value.strip() and not (value in seen or seen.add(value))]


def _source_fragments(text: str) -> list[SourceFragment]:
    """Keep exact sentence offsets where they are mechanically reliable."""

    fragments: list[SourceFragment] = []
    for index, match in enumerate(re.finditer(r"[^。！？!?\n]+[。！？!?]?", text)):
        sentence = match.group(0).strip()
        if not sentence:
            continue
        start = match.start() + (len(match.group(0)) - len(match.group(0).lstrip()))
        fragments.append(SourceFragment(
            stable_id=stable_compiler_id("source", sentence, index), text=sentence,
            start_offset=start, end_offset=start + len(sentence),
        ))
    return fragments or [SourceFragment(stable_id=stable_compiler_id("source", text), text=text, start_offset=0, end_offset=len(text))]


def _matching_source_ids(fragments: list[SourceFragment], value: str) -> list[str]:
    matches = [fragment.stable_id for fragment in fragments if value and value in fragment.text]
    return matches or [fragments[0].stable_id]
