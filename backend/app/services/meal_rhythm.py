from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from app.schemas import (
    DayItinerary,
    ItineraryResponse,
    MealCoverageStatus,
    MealRhythmDay,
    MealRhythmSlot,
    MealRhythmSummary,
    MealRole,
    POIType,
    ScheduledPOI,
    ScheduledPOISourceType,
)


@dataclass(frozen=True, slots=True)
class MealWindow:
    role: MealRole
    start: time
    end: time


@dataclass(frozen=True, slots=True)
class MealRhythmPolicy:
    version: str
    windows: tuple[MealWindow, ...]
    preferred_duration_minutes: int
    minimum_applicable_overlap_minutes: int
    minimum_coverage_overlap_minutes: int


@dataclass(frozen=True, slots=True)
class MealRhythmDiagnostics:
    meal_slots_evaluated: int = 0
    poi_candidates_evaluated: int = 0
    route_calls: int = 0
    successful_completions: int = 0


MEAL_RHYTHM_POLICY = MealRhythmPolicy(
    version="meal-rhythm-v1",
    windows=(
        MealWindow(MealRole.LUNCH, time(11, 30), time(14, 0)),
        MealWindow(MealRole.DINNER, time(17, 30), time(20, 30)),
    ),
    preferred_duration_minutes=60,
    minimum_applicable_overlap_minutes=60,
    minimum_coverage_overlap_minutes=30,
)

NON_MEAL_CATEGORY_TOKENS = (
    "咖啡",
    "coffee",
    "茶艺",
    "茶馆",
    "茶饮",
    "甜品",
    "dessert",
    "冷饮",
    "面包",
    "bakery",
    "小吃",
    "snack",
    "夜市",
)
MEAL_CATEGORY_TOKENS = (
    "餐饮",
    "餐厅",
    "中餐",
    "西餐",
    "火锅",
    "烧烤",
    "烤肉",
    "杭帮菜",
    "本帮菜",
    "快餐",
)


def meal_window(role: MealRole) -> MealWindow:
    return next(window for window in MEAL_RHYTHM_POLICY.windows if window.role == role)


def assess_meal_rhythm(
    itinerary: ItineraryResponse,
    *,
    diagnostics: MealRhythmDiagnostics | None = None,
) -> MealRhythmSummary:
    effective_diagnostics = diagnostics or MealRhythmDiagnostics()
    days = [assess_day_meals(day) for day in itinerary.days]
    unresolved = sum(
        slot.status == MealCoverageStatus.UNRESOLVED
        for day in days
        for slot in day.slots
    )
    return MealRhythmSummary(
        policy_version=MEAL_RHYTHM_POLICY.version,
        days=days,
        meal_slots_evaluated=sum(len(day.slots) for day in days),
        poi_candidates_evaluated=effective_diagnostics.poi_candidates_evaluated,
        route_calls=effective_diagnostics.route_calls,
        successful_completions=effective_diagnostics.successful_completions,
        unresolved_gaps=unresolved,
    )


def assess_day_meals(day: DayItinerary) -> MealRhythmDay:
    items = sorted(
        (item for block in day.blocks for item in block.items),
        key=lambda item: (item.start_time, item.end_time, item.name),
    )
    slots = [assess_meal_slot(day=day, items=items, window=window) for window in MEAL_RHYTHM_POLICY.windows]
    return MealRhythmDay(
        day=day.day,
        slots=slots,
        field_notes=[
            unresolved_meal_note(slot.role, day)
            for slot in slots
            if slot.status == MealCoverageStatus.UNRESOLVED
        ],
    )


def assess_meal_slot(
    *,
    day: DayItinerary,
    items: list[ScheduledPOI],
    window: MealWindow,
) -> MealRhythmSlot:
    if not meal_is_applicable(day, window):
        return MealRhythmSlot(
            role=window.role,
            status=MealCoverageStatus.NOT_APPLICABLE,
            window_start=window.start,
            window_end=window.end,
            explanation=f"当天可旅行时间没有覆盖完整的{meal_role_label(window.role)}时段。",
        )

    covering_item = next(
        (
            item
            for item in items
            if is_meal_capable_item(item)
            and item_overlaps_window(item, window)
        ),
        None,
    )
    if covering_item is None:
        return MealRhythmSlot(
            role=window.role,
            status=MealCoverageStatus.UNRESOLVED,
            window_start=window.start,
            window_end=window.end,
            explanation=f"{meal_role_label(window.role)}还没找到合适的时间和真实地点。",
        )

    auto_completed = (
        covering_item.meal_role == window.role
        and covering_item.source_type == ScheduledPOISourceType.AUTO_SEEDED_MEAL
    )
    return MealRhythmSlot(
        role=window.role,
        status=(
            MealCoverageStatus.AUTO_COMPLETED
            if auto_completed
            else MealCoverageStatus.COVERED
        ),
        window_start=window.start,
        window_end=window.end,
        scheduled_item_stable_id=covering_item.stable_id,
        scheduled_item_name=covering_item.name,
        explanation=(
            f"系统已把 {covering_item.name} 安排为{meal_role_label(window.role)}。"
            if auto_completed
            else f"现有安排 {covering_item.name} 已覆盖{meal_role_label(window.role)}。"
        ),
    )


def meal_is_applicable(day: DayItinerary, window: MealWindow) -> bool:
    active_start, active_end = day_active_period(day)
    return overlap_minutes(active_start, active_end, window.start, window.end) >= (
        MEAL_RHYTHM_POLICY.minimum_applicable_overlap_minutes
    )


def day_active_period(day: DayItinerary) -> tuple[time, time]:
    starts = [block.start_time for block in day.blocks if block.start_time < block.end_time]
    ends = [block.end_time for block in day.blocks if block.start_time < block.end_time]
    start = day.availability_summary.effective_start or (min(starts) if starts else time(9, 0))
    end = day.availability_summary.effective_end or (max(ends) if ends else time(21, 0))
    return start, end


def is_meal_capable_item(item: ScheduledPOI) -> bool:
    if item.type != POIType.RESTAURANT:
        return False
    if item.meal_role is not None:
        return True
    if item.duration_minutes < MEAL_RHYTHM_POLICY.minimum_coverage_overlap_minutes:
        return False
    category = (item.verified_place.category if item.verified_place else "") or ""
    if category:
        return is_meal_capable_category(category, name=item.name)
    if item.source_type in {
        ScheduledPOISourceType.AUTO_SEEDED_MEAL,
        ScheduledPOISourceType.AUTO_FILLED,
    }:
        return False
    return not any(token in item.name.casefold() for token in NON_MEAL_CATEGORY_TOKENS)


def is_meal_capable_category(
    category: str,
    typecode: str | None = None,
    *,
    name: str | None = None,
) -> bool:
    normalized = f"{category} {name or ''}".casefold()
    normalized_typecode = (typecode or "").strip()
    if normalized_typecode and not normalized_typecode.startswith("05"):
        return False
    if any(token in normalized for token in NON_MEAL_CATEGORY_TOKENS):
        return False
    return normalized_typecode.startswith("05") or any(
        token in normalized for token in MEAL_CATEGORY_TOKENS
    )


def item_overlaps_window(item: ScheduledPOI, window: MealWindow) -> bool:
    if item.meal_role is not None and item.meal_role != window.role:
        return False
    return overlap_minutes(item.start_time, item.end_time, window.start, window.end) >= (
        MEAL_RHYTHM_POLICY.minimum_coverage_overlap_minutes
    )


def unresolved_meal_note(role: MealRole, day: DayItinerary) -> str:
    fixed_in_window = any(
        item.is_fixed
        and overlap_minutes(
            item.start_time,
            item.end_time,
            meal_window(role).start,
            meal_window(role).end,
        )
        > 0
        for block in day.blocks
        for item in block.items
    )
    if fixed_in_window:
        return (
            f"{meal_role_label(role)}还没找到合适的位置。当天有已经留好的安排，"
            "我们没有为了塞进一顿饭移动它。"
        )
    return f"{meal_role_label(role)}还没找到合适的位置；系统没有硬塞一个未经验证的餐饮点。"


def meal_role_label(role: MealRole) -> str:
    return "午饭" if role == MealRole.LUNCH else "晚饭"


def overlap_minutes(
    left_start: time,
    left_end: time,
    right_start: time,
    right_end: time,
) -> int:
    start = max(minutes(left_start), minutes(right_start))
    end = min(minutes(left_end), minutes(right_end))
    return max(0, end - start)


def minutes(value: time) -> int:
    return value.hour * 60 + value.minute
