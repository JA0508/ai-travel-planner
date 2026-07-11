from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from app.schemas import (
    DepartureHubCandidateTrace,
    DepartureHubDecisionTrace,
    DepartureOption,
    DepartureRecommendation,
    ItineraryResponse,
    ScheduledPOI,
    TravelMode,
)
from app.services.transport_hub_service import TransportHub, find_transport_hubs


def build_departure_recommendation(
    itinerary: ItineraryResponse,
    departure_anchor_was_provided: bool,
    preferred_mode: TravelMode | None = None,
) -> DepartureRecommendation | None:
    """
    Recommend one concrete departure hub when the user has not already decided it.

    This keeps the feature deterministic: use the user's preferred transport mode
    to filter/rank real city hubs, then choose the hub closest to the final-day
    route centroid with the overall trip centroid as a tie-breaker.
    """
    if departure_anchor_was_provided:
        return None

    scheduled_items = collect_schedulable_items(itinerary)
    if not scheduled_items:
        return None

    last_day = max((day.day for day in itinerary.days), default=None)
    if last_day is None:
        return None

    last_day_items = [item for item in scheduled_items if item.day == last_day]
    if not last_day_items:
        return None

    option = build_recommended_hub_option(
        itinerary=itinerary,
        scheduled_items=scheduled_items,
        last_day_items=last_day_items,
        preferred_mode=preferred_mode,
    )
    if option is None:
        option = build_area_fallback_option(last_day_items)
    if option is None:
        return None

    return DepartureRecommendation(options=[option])


def build_recommended_hub_option(
    itinerary: ItineraryResponse,
    scheduled_items: list[ScheduledPOI],
    last_day_items: list[ScheduledPOI],
    preferred_mode: TravelMode | None,
) -> DepartureOption | None:
    city = infer_trip_city(itinerary, scheduled_items)
    if city is None:
        return None

    hubs = find_transport_hubs(city)
    if not hubs:
        return None

    preferred_category = preferred_category_for_mode(preferred_mode)
    category_filtered_hubs = filter_hubs_for_preferred_category(
        hubs=hubs,
        preferred_category=preferred_category,
    )
    ranked_hubs = rank_hubs_for_departure(
        hubs=category_filtered_hubs,
        scheduled_items=scheduled_items,
        last_day_items=last_day_items,
        preferred_category=preferred_category,
    )
    if not ranked_hubs:
        return None

    best = ranked_hubs[0]
    rejected = ranked_hubs[1:3]
    anchor_pois = [item.name for item in representative_items_for(last_day_items)]
    last_day_center = centroid(last_day_items)
    distance_km = haversine_km(
        best.latitude,
        best.longitude,
        last_day_center[0],
        last_day_center[1],
    )
    rejected_text = format_rejected_hubs(rejected, last_day_center)
    decision_trace = build_departure_hub_decision_trace(
        selected=best,
        ranked_hubs=ranked_hubs,
        preferred_mode=preferred_mode,
        preferred_category=preferred_category,
        target_summary=format_anchor_pois(anchor_pois),
        target=last_day_center,
    )

    return DepartureOption(
        option_title=f"推荐从 {best.name} 离开",
        fit_label=fit_label_for_mode(preferred_mode, best),
        suggested_departure_label=best.name,
        anchor_pois=anchor_pois,
        reasoning_summary=(
            f"按你的{format_preferred_mode(preferred_mode)}偏好，在候选{format_hub_category(best.category)}里选择"
            f"离最后一天收口区域最近的 {best.name}，估算直线距离约 {format_km(distance_km)}。"
        ),
        itinerary_relation_summary=(
            f"最后一天主要收在 {format_anchor_pois(anchor_pois)} 一带；"
            f"{rejected_text}"
        ),
        decision_trace=decision_trace,
    )


def build_area_fallback_option(last_day_items: list[ScheduledPOI]) -> DepartureOption | None:
    representative_items = representative_items_for(last_day_items)
    anchor_pois = [item.name for item in representative_items]
    if not anchor_pois:
        return None

    return DepartureOption(
        option_title="按最后一天收口区域离开",
        fit_label="未拿到真实车站/机场候选",
        suggested_departure_label=format_anchor_pois(anchor_pois),
        anchor_pois=anchor_pois,
        reasoning_summary="暂时没有可用的真实交通枢纽候选，因此先按最后一天实际收口区域给出离开方向。",
        itinerary_relation_summary=f"最后一天主要收在 {format_anchor_pois(anchor_pois)} 一带，后续接入真实候选后会直接推荐具体车站或机场。",
    )


def representative_items_for(items: list[ScheduledPOI]) -> list[ScheduledPOI]:
    centroid_lat = sum(item.latitude for item in items) / len(items)
    centroid_lng = sum(item.longitude for item in items) / len(items)
    return sorted(
        items,
        key=lambda item: squared_distance(
            item.latitude,
            item.longitude,
            centroid_lat,
            centroid_lng,
        ),
    )[:3]


def collect_schedulable_items(itinerary: ItineraryResponse) -> list[ScheduledPOI]:
    return [
        item
        for day in itinerary.days
        for block in day.blocks
        for item in block.items
    ]


def unique_items_by_name(items: list[ScheduledPOI]) -> list[ScheduledPOI]:
    seen: set[str] = set()
    unique_items: list[ScheduledPOI] = []
    for item in items:
        if item.name in seen:
            continue
        seen.add(item.name)
        unique_items.append(item)
    return unique_items


def squared_distance(
    left_lat: float,
    left_lng: float,
    right_lat: float,
    right_lng: float,
) -> float:
    return (left_lat - right_lat) ** 2 + (left_lng - right_lng) ** 2


def format_anchor_pois(anchor_pois: list[str]) -> str:
    if not anchor_pois:
        return "最后一天收口点"
    if len(anchor_pois) == 1:
        return anchor_pois[0]
    if len(anchor_pois) == 2:
        return f"{anchor_pois[0]} 和 {anchor_pois[1]}"
    return f"{anchor_pois[0]}、{anchor_pois[1]} 和 {anchor_pois[2]}"


def build_departure_hub_decision_trace(
    *,
    selected: TransportHub,
    ranked_hubs: list[TransportHub],
    preferred_mode: TravelMode | None,
    preferred_category: str | None,
    target_summary: str,
    target: tuple[float, float],
) -> DepartureHubDecisionTrace:
    top_candidates = [
        build_hub_candidate_trace(
            hub=hub,
            rank=index,
            target=target,
            status="selected" if hub.name == selected.name else "candidate",
            preferred_category=preferred_category,
        )
        for index, hub in enumerate(ranked_hubs[:4], start=1)
    ]
    rejected_candidates = [
        build_hub_candidate_trace(
            hub=hub,
            rank=index,
            target=target,
            status="rejected",
            preferred_category=preferred_category,
        )
        for index, hub in enumerate(ranked_hubs[1:5], start=2)
    ]

    return DepartureHubDecisionTrace(
        selected_hub_name=selected.name,
        preferred_mode=preferred_mode,
        target_summary=target_summary,
        selection_rule=(
            "按用户交通偏好优先筛选 hub 类型，再按最后一天收口区域直线距离排序；"
            "距离相近时用全程中心和名称稳定排序。"
        ),
        top_candidates=top_candidates,
        rejected_candidates=rejected_candidates,
    )


def build_hub_candidate_trace(
    *,
    hub: TransportHub,
    rank: int,
    target: tuple[float, float],
    status: str,
    preferred_category: str | None,
) -> DepartureHubCandidateTrace:
    distance_km = haversine_km(hub.latitude, hub.longitude, target[0], target[1])
    return DepartureHubCandidateTrace(
        name=hub.name,
        category=hub.category,
        rank=rank,
        distance_km=round(distance_km, 2),
        status=status,
        reason=build_hub_candidate_reason(
            hub=hub,
            distance_km=distance_km,
            status=status,
            preferred_category=preferred_category,
        ),
    )


def build_hub_candidate_reason(
    *,
    hub: TransportHub,
    distance_km: float,
    status: str,
    preferred_category: str | None,
) -> str:
    category_fit = (
        "匹配交通偏好"
        if preferred_category is not None and hub.category == preferred_category
        else "交通类型不是首选"
        if preferred_category is not None
        else "未固定交通偏好"
    )
    if status == "selected":
        return f"{category_fit}，距离最后一天收口区域约 {format_km(distance_km)}，因此入选。"
    return f"{category_fit}，距离最后一天收口区域约 {format_km(distance_km)}，排序低于已选 hub。"


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


def preferred_category_for_mode(mode: TravelMode | None) -> str | None:
    if mode == TravelMode.AIRPLANE:
        return "airport"
    if mode in (TravelMode.HIGH_SPEED_RAIL, TravelMode.RAIL):
        return "rail"
    return None


def rank_hubs_for_departure(
    hubs: list[TransportHub],
    scheduled_items: list[ScheduledPOI],
    last_day_items: list[ScheduledPOI],
    preferred_category: str | None,
) -> list[TransportHub]:
    last_day_center = centroid(last_day_items)
    trip_center = centroid(scheduled_items)
    return sorted(
        hubs,
        key=lambda hub: (
            category_rank(hub, preferred_category),
            squared_distance(hub.latitude, hub.longitude, last_day_center[0], last_day_center[1]),
            squared_distance(hub.latitude, hub.longitude, trip_center[0], trip_center[1]),
            hub.name,
        ),
    )


def filter_hubs_for_preferred_category(
    hubs: list[TransportHub],
    preferred_category: str | None,
) -> list[TransportHub]:
    if preferred_category is None:
        return hubs
    preferred_hubs = [hub for hub in hubs if hub.category == preferred_category]
    return preferred_hubs or hubs


def category_rank(hub: TransportHub, preferred_category: str | None) -> int:
    if preferred_category is None:
        return 0
    return 0 if hub.category == preferred_category else 1


def centroid(items: list[ScheduledPOI]) -> tuple[float, float]:
    return (
        sum(item.latitude for item in items) / len(items),
        sum(item.longitude for item in items) / len(items),
    )


def fit_label_for_mode(mode: TravelMode | None, hub: TransportHub) -> str:
    if mode == TravelMode.AIRPLANE and hub.category == "airport":
        return "匹配你的飞机偏好"
    if mode == TravelMode.HIGH_SPEED_RAIL and hub.category == "rail":
        return "匹配你的高铁偏好"
    if mode == TravelMode.RAIL and hub.category == "rail":
        return "匹配你的火车偏好"
    if mode in (TravelMode.CAR, TravelMode.UNDECIDED, None):
        return "按最后一天距离推荐"
    return "按距离优先推荐"


def format_preferred_mode(mode: TravelMode | None) -> str:
    if mode == TravelMode.AIRPLANE:
        return "飞机"
    if mode == TravelMode.HIGH_SPEED_RAIL:
        return "高铁"
    if mode == TravelMode.RAIL:
        return "火车"
    if mode == TravelMode.CAR:
        return "自驾/其他"
    return "未固定交通方式"


def format_hub_category(category: str) -> str:
    if category == "airport":
        return "机场"
    if category == "rail":
        return "车站"
    return "交通枢纽"


def format_rejected_hubs(
    rejected_hubs: list[TransportHub],
    target: tuple[float, float],
) -> str:
    if not rejected_hubs:
        return "没有更近的同类候选。"

    names = [
        f"{hub.name}（约 {format_km(haversine_km(hub.latitude, hub.longitude, target[0], target[1]))}）"
        for hub in rejected_hubs
    ]
    return f"相比 {format_anchor_pois(names)}，这个离最后一天收口区域更近。"


def haversine_km(
    left_lat: float,
    left_lng: float,
    right_lat: float,
    right_lng: float,
) -> float:
    radius_km = 6371.0
    lat1 = radians(left_lat)
    lat2 = radians(right_lat)
    delta_lat = radians(right_lat - left_lat)
    delta_lng = radians(right_lng - left_lng)
    value = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lng / 2) ** 2
    )
    return 2 * radius_km * asin(sqrt(value))


def format_km(value: float) -> str:
    if value < 10:
        return f"{value:.1f} km"
    return f"{value:.0f} km"
