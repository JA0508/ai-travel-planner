from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from app.schemas import (
    ItineraryResponse,
    JourneyApproachRecommendation,
    JourneyApproachSuggestion,
    ScheduledPOI,
    TravelMode,
)
from app.services.transport_hub_service import TransportHub, find_transport_hubs


@dataclass(frozen=True, slots=True)
class PhaseContext:
    phase: str
    preferred_category: str | None
    fit_label: str


def build_journey_approach_recommendation(
    itinerary: ItineraryResponse,
    preferred_mode: TravelMode | None = None,
) -> JourneyApproachRecommendation | None:
    scheduled_items = collect_schedulable_items(itinerary)
    if not scheduled_items:
        return None

    city = infer_trip_city(itinerary, scheduled_items)
    if city is None:
        return None

    hubs = find_transport_hubs(city)
    if not hubs:
        return None

    first_day = min((day.day for day in itinerary.days), default=None)
    last_day = max((day.day for day in itinerary.days), default=None)
    if first_day is None or last_day is None:
        return None

    first_day_items = [item for item in scheduled_items if item.day == first_day]
    last_day_items = [item for item in scheduled_items if item.day == last_day]
    if not first_day_items or not last_day_items:
        return None

    arrival = build_phase_suggestion(
        items=first_day_items,
        all_items=scheduled_items,
        hubs=hubs,
        phase_context=arrival_phase_context(first_day_items, preferred_mode),
    )
    departure = build_phase_suggestion(
        items=last_day_items,
        all_items=scheduled_items,
        hubs=hubs,
        phase_context=departure_phase_context(last_day_items, itinerary.trip_days, preferred_mode),
    )

    if arrival is None and departure is None:
        return None

    return JourneyApproachRecommendation(arrival=arrival, departure=departure)


def build_phase_suggestion(
    items: list[ScheduledPOI],
    all_items: list[ScheduledPOI],
    hubs: list[TransportHub],
    phase_context: PhaseContext,
) -> JourneyApproachSuggestion | None:
    anchor_pois = representative_items(items)
    if not anchor_pois:
        return None

    hub = best_hub_for_phase(
        items=items,
        all_items=all_items,
        hubs=hubs,
        phase_context=phase_context,
    )
    if hub is None:
        return None

    verb = "建议从" if phase_context.phase == "arrival" else "建议从"
    recommendation_title = (
        "推荐到达方式"
        if phase_context.phase == "arrival"
        else "推荐离开方式"
    )
    route_focus = format_anchor_pois(anchor_pois)
    reasoning_summary = build_reasoning_summary(
        phase=phase_context.phase,
        hub=hub,
        route_focus=route_focus,
        preferred_category=phase_context.preferred_category,
    )
    itinerary_relation_summary = build_relation_summary(
        phase=phase_context.phase,
        hub=hub,
        route_focus=route_focus,
    )

    return JourneyApproachSuggestion(
        recommendation_title=recommendation_title,
        recommended_mode=mode_for_hub(hub),
        recommended_hub_name=hub.name,
        fit_label=phase_context.fit_label,
        suggested_area_label=route_focus,
        anchor_pois=anchor_pois,
        reasoning_summary=f"{verb} {hub.name} 衔接。{reasoning_summary}",
        itinerary_relation_summary=itinerary_relation_summary,
    )


def arrival_phase_context(
    first_day_items: list[ScheduledPOI],
    preferred_mode: TravelMode | None,
) -> PhaseContext:
    explicit = preferred_category_for_mode(preferred_mode)
    first_start = min(item.start_time for item in first_day_items)
    total_minutes = sum(item.duration_minutes for item in first_day_items)
    evening_like = count_time_style_matches(
        first_day_items,
        ("night_view", "waterfront", "leisure_district", "food_district"),
    )

    if explicit is not None:
        return PhaseContext(
            phase="arrival",
            preferred_category=explicit,
            fit_label="匹配你偏好的到达方式",
        )

    if first_start >= time(hour=13) or total_minutes <= 180 or evening_like >= 1:
        return PhaseContext(
            phase="arrival",
            preferred_category="airport",
            fit_label="更适合第一天轻量进入",
        )

    return PhaseContext(
        phase="arrival",
        preferred_category="rail",
        fit_label="更适合尽早进入路线",
    )


def departure_phase_context(
    last_day_items: list[ScheduledPOI],
    trip_days: int,
    preferred_mode: TravelMode | None,
) -> PhaseContext:
    explicit = preferred_category_for_mode(preferred_mode)
    last_end = max(item.end_time for item in last_day_items)
    total_minutes = sum(item.duration_minutes for item in last_day_items)

    if explicit is not None:
        return PhaseContext(
            phase="departure",
            preferred_category=explicit,
            fit_label="匹配你偏好的离开方式",
        )

    if last_end <= time(hour=17, minute=30) or total_minutes <= 180:
        return PhaseContext(
            phase="departure",
            preferred_category="airport",
            fit_label="给机场离开留出更多缓冲",
        )

    if len(last_day_items) >= 3 or (trip_days <= 2 and total_minutes >= 210):
        return PhaseContext(
            phase="departure",
            preferred_category="rail",
            fit_label="更适合保留较完整的最后一天",
        )

    return PhaseContext(
        phase="departure",
        preferred_category=None,
        fit_label="最自然的通用离开方案",
    )


def best_hub_for_phase(
    items: list[ScheduledPOI],
    all_items: list[ScheduledPOI],
    hubs: list[TransportHub],
    phase_context: PhaseContext,
) -> TransportHub | None:
    if not hubs:
        return None

    target_lat = sum(item.latitude for item in items) / len(items)
    target_lng = sum(item.longitude for item in items) / len(items)
    trip_lat = sum(item.latitude for item in all_items) / len(all_items)
    trip_lng = sum(item.longitude for item in all_items) / len(all_items)

    return min(
        hubs,
        key=lambda hub: (
            category_rank(hub, phase_context.preferred_category),
            distance_band(squared_distance(hub.latitude, hub.longitude, target_lat, target_lng)),
            squared_distance(hub.latitude, hub.longitude, target_lat, target_lng),
            squared_distance(hub.latitude, hub.longitude, trip_lat, trip_lng),
            hub.name,
        ),
    )


def preferred_category_for_mode(mode: TravelMode | None) -> str | None:
    if mode is None or mode == TravelMode.UNDECIDED or mode == TravelMode.CAR:
        return None
    if mode == TravelMode.AIRPLANE:
        return "airport"
    return "rail"


def category_rank(hub: TransportHub, preferred_category: str | None) -> int:
    if preferred_category is None:
        return 0
    return 0 if hub.category == preferred_category else 1


def distance_band(value: float) -> int:
    if value <= 0.0008:
        return 0
    if value <= 0.003:
        return 1
    if value <= 0.008:
        return 2
    return 3


def build_reasoning_summary(
    phase: str,
    hub: TransportHub,
    route_focus: str,
    preferred_category: str | None,
) -> str:
    hub_kind = "机场" if hub.category == "airport" else "车站"
    if preferred_category == hub.category:
        return (
            f"这个选择能让{_phase_label(phase)}顺着 {route_focus} 一带展开，也贴合你偏好的{hub_kind}方式。"
        )

    if phase == "arrival":
        return f"这是进入 {route_focus} 一带路线最顺的真实枢纽，不会让第一天一开始就跨城折返。"

    return f"这是从 {route_focus} 一带收束行程最顺的真实枢纽，避免最后一天被拉到城市另一侧。"


def build_relation_summary(phase: str, hub: TransportHub, route_focus: str) -> str:
    if phase == "arrival":
        return f"这趟行程从 {route_focus} 一带展开，{hub.name} 是最适合接入这个起点的强枢纽。"
    return f"这趟行程在 {route_focus} 一带收尾，{hub.name} 是最适合从这里离开的强枢纽。"


def _phase_label(phase: str) -> str:
    return "到达" if phase == "arrival" else "离开"


def mode_for_hub(hub: TransportHub) -> TravelMode:
    if hub.category == "airport":
        return TravelMode.AIRPLANE

    if any(token in hub.name for token in ("高铁", "动车", "虹桥", "东站", "西站", "南站", "北站")):
        return TravelMode.HIGH_SPEED_RAIL
    return TravelMode.RAIL


def infer_trip_city(
    itinerary: ItineraryResponse,
    scheduled_items: list[ScheduledPOI],
) -> str | None:
    if itinerary.hotel is not None and itinerary.hotel.city:
        return itinerary.hotel.city
    for item in scheduled_items:
        if item.city:
            return item.city
    return None


def collect_schedulable_items(itinerary: ItineraryResponse) -> list[ScheduledPOI]:
    return [
        item
        for day in itinerary.days
        for block in day.blocks
        for item in block.items
    ]


def representative_items(items: list[ScheduledPOI]) -> list[str]:
    unique_items = unique_items_by_name(items)
    if not unique_items:
        return []

    centroid_lat = sum(item.latitude for item in unique_items) / len(unique_items)
    centroid_lng = sum(item.longitude for item in unique_items) / len(unique_items)
    sorted_items = sorted(
        unique_items,
        key=lambda item: squared_distance(
            item.latitude,
            item.longitude,
            centroid_lat,
            centroid_lng,
        ),
    )
    return [item.name for item in sorted_items[:3]]


def unique_items_by_name(items: list[ScheduledPOI]) -> list[ScheduledPOI]:
    seen: set[str] = set()
    unique_items: list[ScheduledPOI] = []
    for item in items:
        if item.name in seen:
            continue
        seen.add(item.name)
        unique_items.append(item)
    return unique_items


def count_time_style_matches(items: list[ScheduledPOI], styles: tuple[str, ...]) -> int:
    total = 0
    for item in items:
        reason = (item.placement_reason or "").casefold()
        name = item.name.casefold()
        if any(style in reason or style in name for style in styles):
            total += 1
    return total


def squared_distance(
    left_lat: float,
    left_lng: float,
    right_lat: float,
    right_lng: float,
) -> float:
    return (left_lat - right_lat) ** 2 + (left_lng - right_lng) ** 2


def format_anchor_pois(anchor_pois: list[str]) -> str:
    if not anchor_pois:
        return "当前路线里的主要地点"
    if len(anchor_pois) == 1:
        return anchor_pois[0]
    if len(anchor_pois) == 2:
        return f"{anchor_pois[0]} 和 {anchor_pois[1]}"
    return f"{anchor_pois[0]}、{anchor_pois[1]} 和 {anchor_pois[2]}"
