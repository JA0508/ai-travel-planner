from __future__ import annotations

from app.schemas.intent import ParsedTripIntentResponse
from app.schemas.planning_state import (
    AnchorStateType,
    FixedEventStateType,
    HotelStateType,
    IntentReadinessAssessment,
    IntentReadinessIssue,
    IntentReadinessIssueSeverity,
    IntentReadinessLevel,
    PlanningInputState,
    POIStateType,
    PreferenceMode,
    PreferenceState,
    PreferenceStrength,
    TimeStateType,
)
from app.services.preference_policy import build_preference_policy
from app.services.trip_scope_estimator import estimate_trip_scope


def build_planning_input_state(parsed_intent: ParsedTripIntentResponse) -> PlanningInputState:
    preferences = parsed_intent.preferences
    scenic_spots = parsed_intent.scenic_spots
    restaurants = parsed_intent.restaurants
    total_explicit_pois = len(scenic_spots) + len(restaurants)
    preference_state = classify_preference_state(preferences)
    preference_policy = build_preference_policy(preferences)
    trip_scope_estimate = estimate_trip_scope(parsed_intent, preference_state.strength)

    planning_state = PlanningInputState(
        city=parsed_intent.city,
        trip_days=parsed_intent.trip_days,
        hotel=parsed_intent.hotel,
        arrival_anchor=parsed_intent.arrival_anchor,
        departure_anchor=parsed_intent.departure_anchor,
        availability_windows=parsed_intent.availability_windows,
        scenic_spots=scenic_spots,
        restaurants=restaurants,
        fixed_events=parsed_intent.fixed_events,
        preferences=preferences,
        style_preferences=parsed_intent.style_preferences,
        style_preference_sources=parsed_intent.style_preference_sources,
        disambiguation_summary=parsed_intent.disambiguation_summary,
        time_state=classify_time_state(parsed_intent),
        hotel_state=classify_hotel_state(parsed_intent.hotel),
        arrival_anchor_state=classify_anchor_state(parsed_intent.arrival_anchor),
        departure_anchor_state=classify_anchor_state(parsed_intent.departure_anchor),
        poi_state=classify_poi_state(total_explicit_pois, preferences),
        fixed_event_state=classify_fixed_event_state(parsed_intent.fixed_events),
        preference_state=preference_state,
        preference_policy=preference_policy,
        trip_scope_estimate=trip_scope_estimate,
        readiness=build_intent_readiness_assessment(
            parsed_intent=parsed_intent,
            total_explicit_pois=total_explicit_pois,
            preference_state=preference_state,
        ),
    )
    planning_state._style_preference_evidence = dict(
        getattr(parsed_intent, "_style_preference_evidence", {})
    )
    return planning_state


def classify_time_state(parsed_intent: ParsedTripIntentResponse) -> TimeStateType:
    if parsed_intent.availability_windows:
        return TimeStateType.SEMI_FIXED_DURATION
    if parsed_intent.trip_days is not None:
        return TimeStateType.FIXED_DURATION
    return TimeStateType.FLEXIBLE_DURATION


def classify_hotel_state(hotel: str | None) -> HotelStateType:
    if not hotel:
        return HotelStateType.UNKNOWN
    if any(token in hotel for token in ("附近", "near", "around", "区域", "area")):
        return HotelStateType.ROUGHLY_KNOWN
    return HotelStateType.KNOWN


def classify_anchor_state(anchor: str | None) -> AnchorStateType:
    if anchor:
        return AnchorStateType.KNOWN
    return AnchorStateType.UNKNOWN


def classify_poi_state(total_explicit_pois: int, preferences: list[str]) -> POIStateType:
    if total_explicit_pois >= 2:
        return POIStateType.EXPLICIT_POIS
    if total_explicit_pois == 1:
        return POIStateType.PARTIAL_POIS
    if preferences:
        return POIStateType.MOSTLY_PREFERENCE_DRIVEN
    return POIStateType.PARTIAL_POIS


def classify_fixed_event_state(fixed_events: list) -> FixedEventStateType:
    return FixedEventStateType.PRESENT if fixed_events else FixedEventStateType.ABSENT


def classify_preference_state(preferences: list[str]) -> PreferenceState:
    if not preferences:
        return PreferenceState(
            mode=PreferenceMode.IMPLICIT,
            strength=PreferenceStrength.WEAK,
            extracted_preferences=[],
        )

    strength = PreferenceStrength.STRONG if len(preferences) >= 2 else PreferenceStrength.WEAK
    return PreferenceState(
        mode=PreferenceMode.EXPLICIT,
        strength=strength,
        extracted_preferences=preferences,
    )


def build_intent_readiness_assessment(
    *,
    parsed_intent: ParsedTripIntentResponse,
    total_explicit_pois: int,
    preference_state: PreferenceState,
) -> IntentReadinessAssessment:
    issues: list[IntentReadinessIssue] = []
    auto_assumptions: list[str] = []
    clarification_questions: list[str] = []

    has_city = bool(parsed_intent.city)
    has_preferences = bool(parsed_intent.preferences or parsed_intent.style_preferences)
    has_time_boundary = bool(
        parsed_intent.trip_days
        or parsed_intent.arrival_anchor
        or parsed_intent.departure_anchor
        or parsed_intent.availability_windows
        or parsed_intent.fixed_events
    )

    if total_explicit_pois == 0 and not has_preferences and not has_time_boundary:
        issues.append(
            IntentReadinessIssue(
                code="too_little_input",
                severity=IntentReadinessIssueSeverity.BLOCKING,
                message="缺少种草点、偏好或时间线索，系统还无法负责任地整理出有个人味道的可执行路线。",
                can_auto_assume=False,
            )
        )
        clarification_questions.append("先给我一个目的地里的种草点，或者说一句你想要的旅行风格。")

    if not has_city and (total_explicit_pois > 0 or has_preferences):
        issues.append(
            IntentReadinessIssue(
                code="missing_destination",
                severity=IntentReadinessIssueSeverity.WARNING,
                message="没有明确目的地；如果种草点不够唯一，后续地理解析可能需要补充城市。",
                can_auto_assume=False,
            )
        )
        clarification_questions.append("这次主要想去哪个城市或区域？")

    if total_explicit_pois == 0 and has_preferences:
        issues.append(
            IntentReadinessIssue(
                code="preference_only_seed",
                severity=IntentReadinessIssueSeverity.INFO,
                message="当前更像偏好驱动输入，系统会先自动补一批可排程的候选点。",
            )
        )
        auto_assumptions.append("根据城市和偏好自动补齐第一批 seed POIs，再进入确定性排程。")

    if total_explicit_pois == 1:
        issues.append(
            IntentReadinessIssue(
                code="sparse_seed_pois",
                severity=IntentReadinessIssueSeverity.INFO,
                message="只有一个明确种草点，系统会围绕它补齐顺路的景点或活动。",
            )
        )
        auto_assumptions.append("围绕已有种草点自动补齐可执行的一日/多日行程骨架。")

    if not parsed_intent.restaurants:
        issues.append(
            IntentReadinessIssue(
                code="missing_meals",
                severity=IntentReadinessIssueSeverity.INFO,
                message="没有明确餐食点，系统会把午餐和晚餐作为结构性锚点自动补齐。",
            )
        )
        auto_assumptions.append("自动补午餐和晚餐，让路线节奏更像真实出行。")

    if parsed_intent.trip_days is None:
        issues.append(
            IntentReadinessIssue(
                code="flexible_duration",
                severity=IntentReadinessIssueSeverity.INFO,
                message="没有固定天数，系统会根据种草点密度和时间边界估算合理行程范围。",
            )
        )
        auto_assumptions.append("先估算合理天数，再生成可执行行程。")

    if not has_time_boundary:
        issues.append(
            IntentReadinessIssue(
                code="open_time_boundaries",
                severity=IntentReadinessIssueSeverity.INFO,
                message="没有明确到达/离开/固定事件，系统会使用默认日程窗口安排。",
            )
        )
        auto_assumptions.append("使用默认白天出行窗口，保留基础缓冲。")

    level = IntentReadinessLevel.READY
    can_generate = True
    if any(issue.severity == IntentReadinessIssueSeverity.BLOCKING for issue in issues):
        level = IntentReadinessLevel.NEEDS_CLARIFICATION
        can_generate = False
    elif issues:
        level = IntentReadinessLevel.NEEDS_ASSUMPTION

    if level == IntentReadinessLevel.READY:
        summary = "输入已经足够明确，可以直接交给确定性排程层生成路线。"
    elif level == IntentReadinessLevel.NEEDS_ASSUMPTION:
        summary = f"可以先生成；系统会显式采用 {len(auto_assumptions)} 个自动补全/估算假设。"
    else:
        summary = "建议先补一句关键信息，再生成更可靠的行程。"

    return IntentReadinessAssessment(
        level=level,
        can_generate=can_generate,
        issue_count=len(issues),
        issues=issues,
        auto_assumptions=dedupe_preserve_order(auto_assumptions),
        clarification_questions=dedupe_preserve_order(clarification_questions),
        summary=summary,
    )


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
