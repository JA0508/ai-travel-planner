from __future__ import annotations

from app.schemas import (
    CompletionIntelligenceSummary,
    CompletionScoreFactor,
    CompletionScoreBreakdown,
    CompletionTaskCard,
    DayItinerary,
    DepartureRecommendation,
    ItineraryCompletionRecommendation,
    ItineraryResponse,
    POIType,
    PlanningAssumptionSummary,
    ScheduledPOI,
    ScheduledPOISourceType,
    StayRecommendation,
    TimeBlockType,
)


def build_completion_task_instance_key(task_id: str, target: str) -> str:
    normalized_target = (
        target.strip()
        .lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("：", "-")
        .replace(":", "-")
    )
    normalized_target = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-"
        for char in normalized_target
    )
    while "--" in normalized_target:
        normalized_target = normalized_target.replace("--", "-")
    return f"{task_id}:{normalized_target.strip('-') or 'default'}"


def build_completion_intelligence_summary(
    *,
    itinerary: ItineraryResponse,
    planning_assumptions: PlanningAssumptionSummary,
    completion_recommendation: ItineraryCompletionRecommendation | None,
    stay_recommendation: StayRecommendation | None,
    departure_recommendation: DepartureRecommendation | None,
    auto_fill_attempted: bool = False,
    auto_fill_blocked_reasons: list[str] | None = None,
) -> CompletionIntelligenceSummary:
    """
    Summarize the product-level Trip Skeleton Completion result.

    This deliberately sits above the scheduler: deterministic scheduling still
    decides the route, while this service explains how complete and executable
    the resulting skeleton feels.
    """
    sparse_blocks = build_sparse_block_labels(completion_recommendation)
    stay_area = first_stay_area_recommendation(stay_recommendation)
    departure_hub = first_departure_hub_recommendation(departure_recommendation)
    score_breakdown = build_completion_score_breakdown(
        itinerary=itinerary,
        planning_assumptions=planning_assumptions,
        sparse_block_count=len(sparse_blocks),
        stay_area_available=stay_area is not None,
        departure_hub_available=departure_hub is not None,
    )
    system_filled_items = collect_system_filled_items(itinerary)

    return CompletionIntelligenceSummary(
        trip_completeness=calculate_trip_completeness(score_breakdown),
        score_breakdown=score_breakdown,
        action_tasks=build_completion_action_tasks(
            itinerary=itinerary,
            score_breakdown=score_breakdown,
            sparse_blocks=sparse_blocks,
            stay_area=stay_area,
            departure_hub=departure_hub,
        ),
        sparse_blocks_detected=sparse_blocks,
        auto_filled_scenic_count=sum(
            1 for _block_type, item in system_filled_items if item.type == POIType.SCENIC
        ),
        auto_filled_meal_count=sum(
            1 for _block_type, item in system_filled_items if item.type == POIType.RESTAURANT
        ),
        auto_filled_evening_count=sum(
            1 for block_type, _item in system_filled_items if block_type == TimeBlockType.EVENING
        ),
        auto_fill_attempted=auto_fill_attempted,
        auto_fill_blocked_reasons=list(auto_fill_blocked_reasons or []),
        stay_area_recommendation=stay_area,
        departure_hub_recommendation=departure_hub,
        why_this_plan_works=build_completion_intelligence_reasons(
            planning_assumptions=planning_assumptions,
            sparse_block_count=len(sparse_blocks),
            stay_area=stay_area,
            departure_hub=departure_hub,
        ),
    )


def build_completion_action_tasks(
    *,
    itinerary: ItineraryResponse,
    score_breakdown: CompletionScoreBreakdown,
    sparse_blocks: list[str],
    stay_area: str | None,
    departure_hub: str | None,
) -> list[CompletionTaskCard]:
    tasks: list[CompletionTaskCard] = []

    if sparse_blocks:
        first_gap = sparse_blocks[0]
        first_gap_display = format_sparse_block_display_label(first_gap)
        tasks.append(
            CompletionTaskCard(
                task_id="fill_sparse_block",
                task_instance_key=build_completion_task_instance_key(
                    "fill_sparse_block",
                    first_gap,
                ),
                title=f"补齐 {first_gap_display} 的空档",
                reason="这段时间还没有形成可执行安排，补一个顺路点会让当天更像完整路线。",
                action_label="补一个顺路点",
                action_prompt=(
                    f"请优先补齐 {first_gap_display} 的空档，选择离当天已排地点更顺路、不会挤掉午餐或晚餐的轻量地点。"
                ),
                priority="high",
            )
        )

    missing_meals = factor_value_by_code(
        score_breakdown.meals_penalties,
        "missing_meal_slots",
    )
    missing_meal_slots = find_missing_meal_slots(itinerary)
    if missing_meals and missing_meal_slots:
        for meal_day, meal_block in missing_meal_slots:
            meal_gap_label = format_user_time_window_label(meal_day, meal_block)
            meal_gap_key = format_internal_time_window_key(meal_day, meal_block)
            meal_name = "午餐" if meal_block == TimeBlockType.AFTERNOON else "晚餐"
            tasks.append(
                CompletionTaskCard(
                    task_id="add_meal_anchor",
                    task_instance_key=build_completion_task_instance_key(
                        "add_meal_anchor",
                        meal_gap_key,
                    ),
                    title=f"补齐 {meal_gap_label} 的{meal_name}锚点",
                    reason=(
                        f"{meal_gap_label} 还缺少{meal_name}安排，路线可能会像景点列表而不像真实一天。"
                    ),
                    action_label=f"补{meal_name}锚点",
                    action_prompt=(
                        f"请为 {meal_gap_label} 补一个顺路{meal_name}锚点，餐厅应服务当天路线节奏，不要占用上午核心景点时间。"
                    ),
                    priority="high",
                )
            )

    missing_evenings = factor_value_by_code(
        score_breakdown.evening_penalties,
        "missing_evening_blocks",
    )
    missing_evening_blocks = find_missing_evening_blocks(itinerary)
    if missing_evenings and missing_evening_blocks:
        for evening_day, evening_block in missing_evening_blocks:
            evening_gap_label = format_user_time_window_label(evening_day, evening_block)
            evening_gap_key = format_internal_time_window_key(evening_day, evening_block)
            tasks.append(
                CompletionTaskCard(
                    task_id="add_evening_close",
                    task_instance_key=build_completion_task_instance_key(
                        "add_evening_close",
                        evening_gap_key,
                    ),
                    title=f"补一个 {evening_gap_label} 收口",
                    reason=f"{evening_gap_label} 还没有清晰的晚餐、夜景或散步收口。",
                    action_label="补夜间收口",
                    action_prompt=(
                        f"请为 {evening_gap_label} 补一个晚餐、夜景、散步或夜市收口，让当天从下午自然过渡到晚上。"
                    ),
                    priority="medium",
                )
            )

    if stay_area is None:
        tasks.append(
            CompletionTaskCard(
                task_id="add_stay_area",
                task_instance_key=build_completion_task_instance_key(
                    "add_stay_area",
                    "stay-area",
                ),
                title="补住宿区域判断",
                reason="路线已经成形后，住宿区域能帮助判断每天出发和收口是否顺。",
                action_label="补住宿区域",
                action_prompt="请根据当前旅行骨架推荐一个最顺的住宿区域，只推荐区域，不推荐具体酒店。",
                priority="medium",
            )
        )

    if departure_hub is None:
        tasks.append(
            CompletionTaskCard(
                task_id="add_departure_hub",
                task_instance_key=build_completion_task_instance_key(
                    "add_departure_hub",
                    "departure-hub",
                ),
                title="补离开枢纽判断",
                reason="最后一天还缺少明确离开方向，用户上路前会想知道更适合从哪个站点或机场走。",
                action_label="补离开枢纽",
                action_prompt="请根据用户交通偏好和最后一天收口区域，直接推荐一个最顺的离开车站或机场。",
                priority="medium",
            )
        )

    return tasks


def factor_value_by_code(
    factors: list[CompletionScoreFactor],
    code: str,
) -> int | str | None:
    for factor in factors:
        if factor.code == code:
            return factor.value
    return None


def build_sparse_block_labels(
    completion_recommendation: ItineraryCompletionRecommendation | None,
) -> list[str]:
    if completion_recommendation is None:
        return []

    labels: list[str] = []
    for day in completion_recommendation.sparse_days:
        if not day.missing_blocks:
            labels.append(f"Day {day.day}")
            continue
        for block in day.missing_blocks:
            labels.append(f"Day {day.day} {format_time_block_label(block)}")
    return labels


def format_user_time_window_label(day: int, block: TimeBlockType) -> str:
    block_label = {
        TimeBlockType.MORNING: "上午",
        TimeBlockType.AFTERNOON: "下午",
        TimeBlockType.EVENING: "晚上",
    }.get(block, block.value)
    return f"第 {day} 天{block_label}"


def format_internal_time_window_key(day: int, block: TimeBlockType) -> str:
    return f"Day {day} {format_time_block_label(block)}"


def format_sparse_block_display_label(label: str) -> str:
    parts = label.strip().split()
    if len(parts) >= 2 and parts[0].lower() == "day" and parts[1].isdigit():
        day = int(parts[1])
        if len(parts) >= 3:
            block = {
                "morning": TimeBlockType.MORNING,
                "afternoon": TimeBlockType.AFTERNOON,
                "evening": TimeBlockType.EVENING,
            }.get(parts[2].lower())
            if block is not None:
                return format_user_time_window_label(day, block)
        return f"第 {day} 天"
    return label


def find_missing_meal_slots(itinerary: ItineraryResponse) -> list[tuple[int, TimeBlockType]]:
    missing_slots: list[tuple[int, TimeBlockType]] = []
    for day in itinerary.days:
        for block_type in (TimeBlockType.AFTERNOON, TimeBlockType.EVENING):
            if not day_has_restaurant_in_block(day, block_type):
                missing_slots.append((day.day, block_type))
    return missing_slots


def find_missing_evening_blocks(itinerary: ItineraryResponse) -> list[tuple[int, TimeBlockType]]:
    missing_blocks: list[tuple[int, TimeBlockType]] = []
    for day in itinerary.days:
        evening_block = next(
            (block for block in day.blocks if block.block_type == TimeBlockType.EVENING),
            None,
        )
        if evening_block is not None and not evening_block.items:
            missing_blocks.append((day.day, TimeBlockType.EVENING))
    return missing_blocks


def build_completion_score_breakdown(
    *,
    itinerary: ItineraryResponse,
    planning_assumptions: PlanningAssumptionSummary,
    sparse_block_count: int,
    stay_area_available: bool,
    departure_hub_available: bool,
) -> CompletionScoreBreakdown:
    (
        density_score,
        density_reason,
        density_signals,
        density_penalties,
    ) = score_itinerary_density_with_reason(
        itinerary=itinerary,
        sparse_block_count=sparse_block_count,
    )
    meals_score, meals_reason, meals_signals, meals_penalties = (
        score_meal_structure_with_reason(itinerary)
    )
    evening_score, evening_reason, evening_signals, evening_penalties = (
        score_evening_coverage_with_reason(itinerary)
    )
    (
        boundary_score,
        boundary_reason,
        boundary_signals,
        boundary_penalties,
    ) = score_transport_boundary_readiness_with_reason(
        itinerary=itinerary,
        planning_assumptions=planning_assumptions,
        stay_area_available=stay_area_available,
        departure_hub_available=departure_hub_available,
    )

    return CompletionScoreBreakdown(
        density=density_score,
        density_reason=density_reason,
        density_signals=density_signals,
        density_penalties=density_penalties,
        meals=meals_score,
        meals_reason=meals_reason,
        meals_signals=meals_signals,
        meals_penalties=meals_penalties,
        evening=evening_score,
        evening_reason=evening_reason,
        evening_signals=evening_signals,
        evening_penalties=evening_penalties,
        transport_boundary=boundary_score,
        transport_boundary_reason=boundary_reason,
        transport_boundary_signals=boundary_signals,
        transport_boundary_penalties=boundary_penalties,
    )


def calculate_trip_completeness(score_breakdown: CompletionScoreBreakdown) -> int:
    weighted_score = (
        score_breakdown.density * 0.35
        + score_breakdown.meals * 0.25
        + score_breakdown.evening * 0.15
        + score_breakdown.transport_boundary * 0.25
    )
    return clamp_percentage(round(weighted_score))


def score_itinerary_density(
    *,
    itinerary: ItineraryResponse,
    sparse_block_count: int,
) -> int:
    score, _reason, _signals, _penalties = score_itinerary_density_with_reason(
        itinerary=itinerary,
        sparse_block_count=sparse_block_count,
    )
    return score


def score_itinerary_density_with_reason(
    *,
    itinerary: ItineraryResponse,
    sparse_block_count: int,
) -> tuple[int, str, list[CompletionScoreFactor], list[CompletionScoreFactor]]:
    expected_blocks = max(itinerary.trip_days * 3, 1)
    covered_blocks = sum(
        1
        for day in itinerary.days
        for block in day.blocks
        if block.items
    )
    raw_score = round(covered_blocks / expected_blocks * 100)
    sparse_penalty = min(sparse_block_count * 8, 35)
    score = clamp_percentage(raw_score - sparse_penalty)
    signals = [
        score_factor(
            code="covered_core_blocks",
            label="核心时段已覆盖",
            value=f"{covered_blocks}/{expected_blocks}",
        ),
        score_factor(code="base_density_score", label="基础密度分", value=raw_score),
    ]
    penalties: list[CompletionScoreFactor] = []
    empty_blocks = max(expected_blocks - covered_blocks, 0)
    if empty_blocks:
        penalties.append(
            score_factor(
                code="empty_core_blocks",
                label="仍有核心时段为空",
                value=empty_blocks,
            )
        )
    if sparse_block_count:
        penalties.append(
            score_factor(
                code="sparse_blocks_detected",
                label="检测到稀疏时段",
                value=sparse_block_count,
                impact=-sparse_penalty,
            )
        )
    else:
        signals.append(score_factor(code="no_sparse_blocks", label="没有明显稀疏时段"))
    if sparse_block_count:
        reason = (
            f"{covered_blocks}/{expected_blocks} 个核心时段已有内容，"
            f"但仍有 {sparse_block_count} 个稀疏时段让密度降低 {sparse_penalty} 分。"
        )
    else:
        reason = (
            f"{covered_blocks}/{expected_blocks} 个核心时段已覆盖，没有明显大空档。"
        )
    return score, reason, signals, penalties


def score_meal_structure(itinerary: ItineraryResponse) -> int:
    score, _reason, _signals, _penalties = score_meal_structure_with_reason(itinerary)
    return score


def score_meal_structure_with_reason(
    itinerary: ItineraryResponse,
) -> tuple[int, str, list[CompletionScoreFactor], list[CompletionScoreFactor]]:
    expected_meal_slots = max(itinerary.trip_days * 2, 1)
    covered_meal_slots = 0
    for day in itinerary.days:
        covered_meal_slots += int(day_has_restaurant_in_block(day, TimeBlockType.AFTERNOON))
        covered_meal_slots += int(day_has_restaurant_in_block(day, TimeBlockType.EVENING))
    score = clamp_percentage(round(covered_meal_slots / expected_meal_slots * 100))
    missing_meal_slots = max(expected_meal_slots - covered_meal_slots, 0)
    signals = [
        score_factor(
            code="covered_meal_slots",
            label="午餐/晚餐锚点已覆盖",
            value=f"{covered_meal_slots}/{expected_meal_slots}",
        )
    ]
    if covered_meal_slots:
        signals.append(
            score_factor(
                code="meal_anchor_policy_applied",
                label="餐厅已作为节奏锚点",
            )
        )
    penalties = (
        [
            score_factor(
                code="missing_meal_slots",
                label="仍缺午餐/晚餐锚点",
                value=missing_meal_slots,
            )
        ]
        if missing_meal_slots
        else []
    )
    if covered_meal_slots >= expected_meal_slots:
        reason = "整趟旅行的午餐和晚餐锚点已经覆盖，餐食能支撑每天节奏。"
    elif covered_meal_slots:
        reason = (
            f"{covered_meal_slots}/{expected_meal_slots} 个午餐/晚餐锚点已覆盖；"
            "剩余餐食空档会拉低可执行节奏分。"
        )
    else:
        reason = "目前还没有明确午餐或晚餐锚点，餐食安排会显得像临时填充。"
    return score, reason, signals, penalties


def score_evening_coverage(itinerary: ItineraryResponse) -> int:
    score, _reason, _signals, _penalties = score_evening_coverage_with_reason(itinerary)
    return score


def score_evening_coverage_with_reason(
    itinerary: ItineraryResponse,
) -> tuple[int, str, list[CompletionScoreFactor], list[CompletionScoreFactor]]:
    expected_evenings = max(itinerary.trip_days, 1)
    covered_evenings = sum(
        1
        for day in itinerary.days
        if any(block.block_type == TimeBlockType.EVENING and block.items for block in day.blocks)
    )
    score = clamp_percentage(round(covered_evenings / expected_evenings * 100))
    missing_evenings = max(expected_evenings - covered_evenings, 0)
    signals = [
        score_factor(
            code="covered_evening_blocks",
            label="夜间时段已覆盖",
            value=f"{covered_evenings}/{expected_evenings}",
        )
    ]
    if covered_evenings:
        signals.append(
            score_factor(
                code="night_rhythm_continues",
                label="白天后有夜间收口",
            )
        )
    penalties = (
        [
            score_factor(
                code="missing_evening_blocks",
                label="仍有夜间时段未明确",
                value=missing_evenings,
            )
        ]
        if missing_evenings
        else []
    )
    if covered_evenings >= expected_evenings:
        reason = "每个晚上都有活动、餐食或适合夜间的收口锚点。"
    elif covered_evenings:
        reason = (
            f"{covered_evenings}/{expected_evenings} 个夜间时段已覆盖；"
            "部分夜晚仍需要更明确的晚餐或夜景安排。"
        )
    else:
        reason = "夜间时段仍为空，白天结束后行程会显得没有收口。"
    return score, reason, signals, penalties


def score_transport_boundary_readiness(
    *,
    itinerary: ItineraryResponse,
    planning_assumptions: PlanningAssumptionSummary,
    stay_area_available: bool,
    departure_hub_available: bool,
) -> int:
    score, _reason, _signals, _penalties = score_transport_boundary_readiness_with_reason(
        itinerary=itinerary,
        planning_assumptions=planning_assumptions,
        stay_area_available=stay_area_available,
        departure_hub_available=departure_hub_available,
    )
    return score


def score_transport_boundary_readiness_with_reason(
    *,
    itinerary: ItineraryResponse,
    planning_assumptions: PlanningAssumptionSummary,
    stay_area_available: bool,
    departure_hub_available: bool,
) -> tuple[int, str, list[CompletionScoreFactor], list[CompletionScoreFactor]]:
    score = 45
    signals = [
        score_factor(
            code="base_route_shape_available",
            label="基础路线形状已生成",
            impact=45,
        )
    ]
    penalties: list[CompletionScoreFactor] = []
    if stay_area_available:
        score += 15
        signals.append(score_factor(code="stay_area_advice", label="住宿区域建议", impact=15))
    else:
        penalties.append(score_factor(code="stay_area_missing", label="住宿区域建议暂不可用"))
    if departure_hub_available:
        score += 20
        signals.append(
            score_factor(code="departure_hub_advice", label="离开枢纽建议", impact=20)
        )
    else:
        penalties.append(
            score_factor(code="departure_hub_missing", label="离开枢纽建议暂不可用")
        )
    if planning_assumptions.availability_window_count > 0:
        score += 8
        signals.append(
            score_factor(
                code="availability_windows",
                label="可用时间窗",
                value=planning_assumptions.availability_window_count,
                impact=8,
            )
        )
    else:
        penalties.append(
            score_factor(code="availability_window_missing", label="未明确可用时间窗")
        )
    if planning_assumptions.fixed_event_count > 0:
        score += 8
        signals.append(
            score_factor(
                code="fixed_events",
                label="固定安排",
                value=planning_assumptions.fixed_event_count,
                impact=8,
            )
        )
    else:
        penalties.append(score_factor(code="fixed_event_missing", label="未提供固定安排锚点"))
    if itinerary.boundary_explanation.arrival_anchor_influenced:
        score += 7
        signals.append(score_factor(code="arrival_boundary", label="到达边界", impact=7))
    else:
        penalties.append(score_factor(code="arrival_boundary_missing", label="到达边界不明确"))
    if itinerary.boundary_explanation.departure_anchor_influenced:
        score += 7
        signals.append(score_factor(code="departure_boundary", label="离开边界", impact=7))
    else:
        penalties.append(
            score_factor(code="departure_boundary_missing", label="离开边界不明确")
        )
    final_score = clamp_percentage(score)
    if signals:
        reason = (
            "交通边界已由"
            f"{'、'.join(factor.label for factor in signals)}支撑；"
            "但仍有缺失信号，所以还不是完全锁定的出行交接。"
        )
    else:
        reason = (
            "交通边界目前只依赖基础行程形状，还没有住宿、离开、固定时间或可用时间窗来加强判断。"
        )
    return final_score, reason, signals, penalties


def score_factor(
    *,
    code: str,
    label: str,
    value: int | str | None = None,
    impact: int | None = None,
) -> CompletionScoreFactor:
    return CompletionScoreFactor(code=code, label=label, value=value, impact=impact)


def day_has_restaurant_in_block(day: DayItinerary, block_type: TimeBlockType) -> bool:
    return any(
        block.block_type == block_type
        and any(item.type == POIType.RESTAURANT for item in block.items)
        for block in day.blocks
    )


def collect_system_filled_items(
    itinerary: ItineraryResponse,
) -> list[tuple[TimeBlockType, ScheduledPOI]]:
    system_sources = {
        ScheduledPOISourceType.AUTO_FILLED,
        ScheduledPOISourceType.AUTO_SEEDED_POI,
        ScheduledPOISourceType.AUTO_SEEDED_MEAL,
    }
    return [
        (block.block_type, item)
        for day in itinerary.days
        for block in day.blocks
        for item in block.items
        if item.source_type in system_sources
    ]


def first_stay_area_recommendation(
    stay_recommendation: StayRecommendation | None,
) -> str | None:
    if stay_recommendation is None or not stay_recommendation.options:
        return None
    option = stay_recommendation.options[0]
    return f"{option.suggested_area_label} · {option.fit_label}"


def first_departure_hub_recommendation(
    departure_recommendation: DepartureRecommendation | None,
) -> str | None:
    if departure_recommendation is None or not departure_recommendation.options:
        return None
    option = departure_recommendation.options[0]
    return f"{option.suggested_departure_label} · {option.fit_label}"


def build_completion_intelligence_reasons(
    *,
    planning_assumptions: PlanningAssumptionSummary,
    sparse_block_count: int,
    stay_area: str | None,
    departure_hub: str | None,
) -> list[str]:
    reasons = [
        (
            "系统先保护了 "
            f"{planning_assumptions.user_seed_scenic_count + planning_assumptions.user_seed_restaurant_count} "
            "个用户种草点和 "
            f"{planning_assumptions.fixed_event_count} 个固定安排，再补齐剩余旅行骨架。"
        ),
        (
            f"自动补齐后仍有 {sparse_block_count} 个稀疏时段，所以把空档显性展示，而不是悄悄藏掉。"
            if sparse_block_count
            else "骨架补齐后没有明显的大空档，可以先进入路线编辑。"
        ),
    ]
    if planning_assumptions.meal_structure_applied:
        reasons.append("午餐和晚餐会被当作路线节奏锚点，避免一天只像景点清单。")
    if stay_area:
        reasons.append(f"住宿区域建议来自已成型的路线分布：{stay_area}。")
    if departure_hub:
        reasons.append(f"离开建议会贴合最后一天的收口位置：{departure_hub}。")
    return unique_preserve_order(reasons)[:6]


def format_time_block_label(block_type: TimeBlockType) -> str:
    if block_type == TimeBlockType.MORNING:
        return "morning"
    if block_type == TimeBlockType.AFTERNOON:
        return "afternoon"
    if block_type == TimeBlockType.EVENING:
        return "evening"
    return block_type.value


def clamp_percentage(value: int) -> int:
    return max(0, min(100, value))


def unique_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
