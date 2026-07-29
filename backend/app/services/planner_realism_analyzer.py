from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt

from app.schemas import (
    DailyRouteLoad,
    ItineraryResponse,
    PlannerRealismAction,
    PlannerRealismIssue,
    PlannerRealismSummary,
    POIType,
    ScheduledPOI,
    TimeBlockType,
)


LONG_TRANSFER_KM = 12.0
LONG_TRANSFER_MINUTES = 45
OUTLIER_KM = 15.0
HALF_DAY_DURATION_MINUTES = 120


def analyze_planner_realism(itinerary: ItineraryResponse) -> PlannerRealismSummary:
    issues: list[PlannerRealismIssue] = []
    actions: list[PlannerRealismAction] = []

    for day in itinerary.days:
        day_items = [item for block in day.blocks for item in block.items]
        issues.extend(find_long_transfer_issues(day_items))
        outliers = find_outlier_items(day_items)
        for item, distance_km in outliers:
            issue = build_outlier_issue(day=day.day, item=item, distance_km=distance_km)
            issues.append(issue)
            actions.append(build_outlier_action(issue, item))

        if not has_restaurant(day_items):
            issues.append(
                PlannerRealismIssue(
                    code="meal_gap",
                    severity="medium",
                    title=f"第 {day.day} 天缺少餐食锚点",
                    detail="这一天还没有明确午餐或晚餐，真实行程会显得像景点列表。",
                    day=day.day,
                )
            )
        if not has_evening_item(day):
            issues.append(
                PlannerRealismIssue(
                    code="evening_gap",
                    severity="medium",
                    title=f"第 {day.day} 天晚上还没收口",
                    detail="晚上没有安排晚餐、夜景或轻量散步，路线到白天结束后会断掉。",
                    day=day.day,
                )
            )

    if has_last_day_departure_risk(itinerary):
        last_day = max((day.day for day in itinerary.days), default=None)
        issues.append(
            PlannerRealismIssue(
                code="departure_boundary_risk",
                severity="medium",
                title="最后一天离开边界还不够稳",
                detail="最后一天仍有空档或缺少明确离开时间，出行前需要再确认收口安排。",
                day=last_day,
            )
        )

    status = realism_status(issues)
    daily_loads = build_daily_route_loads(itinerary, issues)
    return PlannerRealismSummary(
        status=status,
        headline=realism_headline(status, issues),
        issues=issues,
        suggested_actions=actions,
        daily_loads=daily_loads,
    )


def build_daily_route_loads(
    itinerary: ItineraryResponse,
    issues: list[PlannerRealismIssue],
) -> list[DailyRouteLoad]:
    """Classify daily execution load once on the server for every client surface."""
    loads: list[DailyRouteLoad] = []
    for day in itinerary.days:
        items = [item for block in day.blocks for item in block.items]
        activity_minutes = sum(item.duration_minutes for item in items)
        travel_minutes = round(sum(item.travel_duration_s or 0 for item in items) / 60)
        known_distances = [item.travel_distance_m for item in items if item.travel_distance_m is not None]
        distance_m = sum(known_distances) if known_distances else None
        day_issues = [issue for issue in issues if issue.day == day.day]
        has_blocking_issue = any(issue.severity == "high" for issue in day_issues)
        total_minutes = activity_minutes + travel_minutes
        if has_blocking_issue:
            classification = "infeasible"
            reason_codes = [issue.code for issue in day_issues if issue.severity == "high"]
            explanation = "当天存在需要先解决的路线冲突，不能当作可直接出发的安排。"
        elif len(items) >= 5 or travel_minutes >= 120 or total_minutes > 510:
            classification = "rushed"
            reason_codes = ["daily_load_high"]
            explanation = (
                f"安排了 {len(items)} 项活动，预计移动 {travel_minutes} 分钟，"
                "当天衔接偏紧。"
            )
        elif len(items) <= 2 and total_minutes <= 260:
            classification = "relaxed"
            reason_codes = ["daily_load_light"]
            explanation = "活动和移动时间留有余量，适合慢慢逛。"
        else:
            classification = "balanced"
            reason_codes = ["daily_load_balanced"]
            explanation = "活动、移动和可用时间大致均衡。"
        loads.append(
            DailyRouteLoad(
                day=day.day,
                classification=classification,
                activity_count=len(items),
                fixed_count=sum(1 for item in items if item.is_fixed),
                activity_minutes=activity_minutes,
                travel_minutes=travel_minutes,
                route_distance_m=distance_m,
                reason_codes=reason_codes,
                explanation=explanation,
            )
        )
    return loads


def find_long_transfer_issues(items: list[ScheduledPOI]) -> list[PlannerRealismIssue]:
    issues: list[PlannerRealismIssue] = []
    ordered = sorted(items, key=lambda item: (item.start_time, item.end_time, item.name))
    for previous, current in zip(ordered, ordered[1:]):
        distance_km = haversine_km(
            previous.latitude,
            previous.longitude,
            current.latitude,
            current.longitude,
        )
        travel_minutes = (
            round(current.travel_duration_s / 60)
            if current.travel_duration_s is not None
            else None
        )
        if distance_km <= LONG_TRANSFER_KM and (
            travel_minutes is None or travel_minutes <= LONG_TRANSFER_MINUTES
        ):
            continue
        detail = f"{previous.name} 到 {current.name} 距离约 {distance_km:.1f} km。"
        if travel_minutes is not None:
            detail += f" 当前步行/换乘估计约 {travel_minutes} 分钟。"
        detail += " 这段移动会让路线不像真人会顺手安排。"
        issues.append(
            PlannerRealismIssue(
                code="long_transfer",
                severity="high" if distance_km >= OUTLIER_KM else "medium",
                title="相邻地点移动过长",
                detail=detail,
                day=current.day,
                item_names=[previous.name, current.name],
            )
        )
    return issues


def find_outlier_items(items: list[ScheduledPOI]) -> list[tuple[ScheduledPOI, float]]:
    if len(items) < 3:
        return []
    outliers: list[tuple[ScheduledPOI, float]] = []
    for item in items:
        others = [candidate for candidate in items if candidate.name != item.name]
        centroid = (
            sum(candidate.latitude for candidate in others) / len(others),
            sum(candidate.longitude for candidate in others) / len(others),
        )
        distance_km = haversine_km(item.latitude, item.longitude, centroid[0], centroid[1])
        if distance_km >= OUTLIER_KM:
            outliers.append((item, distance_km))
    return outliers


def build_outlier_issue(day: int, item: ScheduledPOI, distance_km: float) -> PlannerRealismIssue:
    severity = "high" if item.duration_minutes >= HALF_DAY_DURATION_MINUTES else "medium"
    if item.type == POIType.SCENIC and item.duration_minutes >= HALF_DAY_DURATION_MINUTES:
        detail = (
            f"{item.name} 距离当天其他地点约 {distance_km:.1f} km，且停留时间较长，"
            "更像需要单独半天处理的重点点。"
        )
    else:
        detail = (
            f"{item.name} 距离当天其他地点约 {distance_km:.1f} km，"
            "容易把当天路线拉成跨区折返。"
        )
    return PlannerRealismIssue(
        code="distance_outlier",
        severity=severity,
        title="有地点离当天主线太远",
        detail=detail,
        day=day,
        item_names=[item.name],
    )


def build_outlier_action(
    issue: PlannerRealismIssue,
    item: ScheduledPOI,
) -> PlannerRealismAction:
    return PlannerRealismAction(
        action_id=f"separate-outlier:{item.day}:{item.name}",
        label=f"把 {item.name} 单独成半日线",
        prompt=(
            f"{item.name} 离当前市区主线较远，请把它单独安排成半日线；"
            "如果时间不够，就提示我是否要放弃它。"
        ),
        priority="high" if issue.severity == "high" else "medium",
        related_issue_code=issue.code,
    )


def has_restaurant(items: list[ScheduledPOI]) -> bool:
    return any(item.type == POIType.RESTAURANT for item in items)


def has_evening_item(day) -> bool:
    return any(
        block.block_type == TimeBlockType.EVENING and block.items
        for block in day.blocks
    )


def has_last_day_departure_risk(itinerary: ItineraryResponse) -> bool:
    if itinerary.departure_recommendation and itinerary.departure_recommendation.options:
        return False
    if not itinerary.days:
        return False
    last_day = max(itinerary.days, key=lambda day: day.day)
    return not has_evening_item(last_day)


def realism_status(issues: list[PlannerRealismIssue]) -> str:
    if any(issue.severity == "high" for issue in issues):
        return "unstable"
    if issues:
        return "needs_repair"
    return "executable"


def realism_headline(status: str, issues: list[PlannerRealismIssue]) -> str:
    if status == "executable":
        return "这版旅行骨架基本可执行。"
    if any(issue.code == "distance_outlier" for issue in issues):
        return "这版骨架还不稳：有远距离点需要单独成组。"
    if any(issue.code in {"meal_gap", "evening_gap"} for issue in issues):
        return "这版骨架还需要补餐食或夜间收口。"
    return "这版骨架还需要继续修到更顺路。"


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
    a = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lng / 2) ** 2
    return radius_km * 2 * atan2(sqrt(a), sqrt(1 - a))
