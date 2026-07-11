from __future__ import annotations

from app.schemas import (
    DayItinerary,
    DayTimeBlock,
    ItineraryResponse,
    POIResearchSummary,
    POIType,
    ScheduledPOI,
    TimeBlockType,
)


def attach_poi_research_summaries(itinerary: ItineraryResponse) -> ItineraryResponse:
    """Attach lightweight, deterministic POI card content to scheduled stops."""

    next_days = [
        day.model_copy(update={"blocks": [build_block_with_research(day, block) for block in day.blocks]})
        for day in itinerary.days
    ]
    return itinerary.model_copy(update={"days": next_days})


def build_block_with_research(day: DayItinerary, block: DayTimeBlock) -> DayTimeBlock:
    next_items = [
        item.model_copy(update={"poi_research": build_poi_research_summary(day, block, item)})
        for item in block.items
    ]
    return block.model_copy(update={"items": next_items})


def build_poi_research_summary(
    day: DayItinerary,
    block: DayTimeBlock,
    item: ScheduledPOI,
) -> POIResearchSummary:
    return POIResearchSummary(
        overview=build_overview(item),
        access_tip=build_access_tip(item),
        practical_tip=build_practical_tip(item),
        best_for=build_best_for(day, block, item),
        source=build_source_label(item),
    )


def build_overview(item: ScheduledPOI) -> str:
    if item.source_reason:
        return shorten(item.source_reason, 88)
    if item.placement_reason:
        return shorten(item.placement_reason, 88)
    if item.type == POIType.RESTAURANT:
        return "这类地点更适合作为午餐或晚餐锚点，用来让当天路线有真实停顿。"
    if item.type == POIType.HOTEL:
        return "住宿点会影响每天起收口和跨天移动，适合在路线骨架稳定后再确认。"
    return "这是当前旅行骨架里的停留点，已经参与当天路线顺序和后续补全判断。"


def build_access_tip(item: ScheduledPOI) -> str:
    if item.travel_from_name and item.travel_duration_s:
        distance = (
            f"，约 {format_distance(item.travel_distance_m)}"
            if item.travel_distance_m is not None
            else ""
        )
        return f"从 {item.travel_from_name} 过来约 {format_duration(item.travel_duration_s)}{distance}。"
    if item.travel_from_name:
        return f"从 {item.travel_from_name} 进入这一站，当前没有更细的路段时间。"
    return "当前还没有可确认的上一站路段，下一次规划会重新校验到达方式。"


def build_practical_tip(item: ScheduledPOI) -> str:
    if item.is_fixed:
        return "已固定在当前时间，后续自动规划会围绕它调整，不适合频繁移动。"
    if item.type == POIType.RESTAURANT:
        return "餐食点建议保留一定缓冲，不要把前后景点排得太紧。"
    if item.source_type.value.startswith("auto_"):
        return "这是系统补入或起步点，如果不合口味，可以在编辑路线里替换或删除。"
    if item.placement_reason and "departure" in item.placement_reason.casefold():
        return "这一站影响最后一天收口，调整时要一起看离开交通。"
    return "如果这里感觉不顺，可以先移动到别的时间段，再让系统重新生成确认路段。"


def build_best_for(day: DayItinerary, block: DayTimeBlock, item: ScheduledPOI) -> str:
    if item.type == POIType.RESTAURANT:
        return f"适合放在第 {day.day} 天{format_block(block.block_type)}，作为当天餐食和休息节点。"
    if block.block_type == TimeBlockType.MORNING:
        return "适合放在上午作为当天的主要游玩起点。"
    if block.block_type == TimeBlockType.EVENING:
        return "适合放在晚上作为轻量散步、夜景或收尾安排。"
    return f"适合放在第 {day.day} 天{format_block(block.block_type)}，和前后地点串成同一段路线。"


def build_source_label(item: ScheduledPOI) -> str:
    if item.source_type.value.startswith("auto_"):
        return "planner_completion"
    if item.is_fixed:
        return "fixed_route_context"
    return "route_context"


def format_block(block_type: TimeBlockType) -> str:
    if block_type == TimeBlockType.MORNING:
        return "上午"
    if block_type == TimeBlockType.AFTERNOON:
        return "下午"
    return "晚上"


def format_duration(duration_seconds: int) -> str:
    return f"{round(duration_seconds / 60)} 分钟"


def format_distance(distance_meters: int) -> str:
    if distance_meters >= 1000:
        return f"{distance_meters / 1000:.1f} km"
    return f"{distance_meters} m"


def shorten(value: str, max_length: int) -> str:
    text = value.strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1]}…"
