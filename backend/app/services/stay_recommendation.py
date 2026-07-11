from __future__ import annotations

from app.schemas import ItineraryResponse, ScheduledPOI, StayOption, StayRecommendation


REGION_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("滨海新区一带", ("国家海洋博物馆", "滨海", "塘沽", "生态城")),
    ("天津站 / 意风区一带", ("天津站", "意大利风情", "意风区", "海河", "天津之眼")),
    ("五大道 / 小白楼一带", ("五大道", "小白楼", "瓷房子", "怪小妹")),
    ("西北角 / 古文化街一带", ("西北角", "古文化街", "鼓楼")),
    ("西湖 / 湖滨一带", ("西湖", "湖滨", "断桥", "龙翔桥")),
    ("灵隐 / 龙井一带", ("灵隐", "法喜寺", "龙井")),
    ("人民广场 / 南京东路一带", ("人民广场", "南京东路", "外滩", "豫园")),
    ("静安寺 / 愚园路一带", ("静安寺", "愚园路", "武康路")),
)


def build_stay_recommendation(
    itinerary: ItineraryResponse,
    hotel_was_provided: bool,
) -> StayRecommendation | None:
    """
    Offer a small set of stay strategies after itinerary generation when the user
    has not committed to a hotel yet.
    """
    if hotel_was_provided:
        return None

    scheduled_items = collect_schedulable_items(itinerary)
    if not scheduled_items:
        return None

    options: list[StayOption] = []

    balanced_option = build_option_from_items(
        items=scheduled_items,
        option_title="全程均衡住宿区域",
        fit_label="兼顾整趟路线",
        reasoning_summary=(
            "这个区域靠近当前行程的主要活动重心，适合想用一个稳定落脚点覆盖整趟旅行。"
        ),
        itinerary_relation_summary=(
            "它根据当前旅行骨架里最密集的共同中心反推，而不是只贴合第一天或最后一天。"
        ),
    )
    append_distinct_option(options, balanced_option)

    arrival_option = build_arrival_option(itinerary)
    append_distinct_option(options, arrival_option)

    departure_option = build_departure_option(itinerary)
    append_distinct_option(options, departure_option)

    if not options:
        return None

    return StayRecommendation(options=options)


def build_arrival_option(itinerary: ItineraryResponse) -> StayOption | None:
    arrival_anchor_name = (
        itinerary.boundary_explanation.arrival_anchor_name
        or (
            itinerary.planning_anchor_source.source_name
            if itinerary.planning_anchor_source.source_type == "arrival_anchor"
            else None
        )
    )
    if arrival_anchor_name is None:
        return None

    first_day_items = [
        item
        for item in collect_schedulable_items(itinerary)
        if item.day == 1
    ]
    if not first_day_items:
        return None

    first_stop_name = itinerary.boundary_explanation.arrival_poi_name or first_day_items[0].name
    return build_option_from_items(
        items=first_day_items,
        option_title="更适合到达日的住宿区域",
        fit_label="更贴合第一天",
        reasoning_summary=(
            f"这个区域更靠近从 {arrival_anchor_name} 开始进入的行程范围，第一天不用先做一次长距离跨城跳转。"
        ),
        itinerary_relation_summary=(
            f"当前行程从 {first_stop_name} 一带展开，这个区域比完全居中的住宿点更能支撑第一天的路线形状。"
        ),
    )


def build_departure_option(itinerary: ItineraryResponse) -> StayOption | None:
    if itinerary.trip_days < 2:
        return None

    last_day = max(day.day for day in itinerary.days)
    last_day_items = [
        item
        for item in collect_schedulable_items(itinerary)
        if item.day == last_day
    ]
    if not last_day_items:
        return None

    departure_poi_name = (
        itinerary.boundary_explanation.departure_poi_name or last_day_items[-1].name
    )
    return build_option_from_items(
        items=last_day_items,
        option_title="更适合离开日的住宿区域",
        fit_label="更贴合离开日",
        reasoning_summary=(
            "这个区域更靠近最后一天收尾的行程范围，离开时会更顺，不容易临走前被路线拖得太赶。"
        ),
        itinerary_relation_summary=(
            f"当前行程在 {departure_poi_name} 一带收尾，这个区域能更好支撑最后一段路线。"
        ),
    )


def build_option_from_items(
    items: list[ScheduledPOI],
    option_title: str,
    fit_label: str,
    reasoning_summary: str,
    itinerary_relation_summary: str,
) -> StayOption | None:
    unique_items = unique_items_by_name(items)
    if not unique_items:
        return None

    centroid_lat = sum(item.latitude for item in unique_items) / len(unique_items)
    centroid_lng = sum(item.longitude for item in unique_items) / len(unique_items)

    representative_items = sorted(
        unique_items,
        key=lambda item: squared_distance(
            item.latitude,
            item.longitude,
            centroid_lat,
            centroid_lng,
        ),
    )[:3]

    anchor_pois = [item.name for item in representative_items]
    area_label, area_source = infer_area_label(unique_items, anchor_pois)
    return StayOption(
        option_title=option_title,
        suggested_area_label=area_label,
        fit_label=fit_label,
        anchor_pois=anchor_pois,
        reasoning_summary=reasoning_summary,
        itinerary_relation_summary=itinerary_relation_summary,
        area_source=area_source,
    )


def append_distinct_option(options: list[StayOption], option: StayOption | None) -> None:
    if option is None:
        return

    if any(
        existing.suggested_area_label == option.suggested_area_label
        or existing.anchor_pois == option.anchor_pois
        for existing in options
    ):
        return

    options.append(option)


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
        return "当前路线里的主要地点"
    if len(anchor_pois) == 1:
        return anchor_pois[0]
    if len(anchor_pois) == 2:
        return f"{anchor_pois[0]} 和 {anchor_pois[1]}"
    return f"{anchor_pois[0]}、{anchor_pois[1]} 和 {anchor_pois[2]}"


def infer_area_label(
    items: list[ScheduledPOI],
    representative_pois: list[str],
) -> tuple[str, str]:
    best_label = ""
    best_score = 0
    item_names = [item.name for item in items]
    for label, keywords in REGION_KEYWORDS:
        score = sum(
            1
            for name in item_names
            for keyword in keywords
            if keyword in name
        )
        if score > best_score:
            best_label = label
            best_score = score
    if best_label:
        return best_label, "keyword_region"
    if representative_pois:
        return f"{format_anchor_pois(representative_pois)} 一带", "route_centroid"
    return "当前路线中心一带", "route_centroid"
