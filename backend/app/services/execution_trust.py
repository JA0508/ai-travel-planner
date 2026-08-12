"""Build a persisted execution-evidence summary without rerunning planning."""

from __future__ import annotations

from app.planner.trace.models import ProviderSnapshotSummary
from app.schemas.itinerary import ExecutionTrustFact, ExecutionTrustSummary, ItineraryResponse


def build_execution_trust_summary(
    *,
    itinerary: ItineraryResponse,
    provider_summary: ProviderSnapshotSummary | None,
) -> ExecutionTrustSummary:
    """Translate existing planner output into explicit evidence boundaries.

    Provider snapshots do not currently include observation timestamps. A known
    provider result is therefore shown as returned-at-planning-time with unknown
    freshness, rather than being presented as a currently verified fact.
    """

    realism = itinerary.planner_realism
    blocking_reasons = [
        issue.detail
        for issue in (realism.issues if realism is not None else [])
        if issue.severity == "high"
    ]
    warning_reasons = [
        issue.detail
        for issue in (realism.issues if realism is not None else [])
        if issue.severity != "high"
    ]
    facts: list[ExecutionTrustFact] = []

    if realism is not None and realism.status == "unstable":
        facts.append(
            ExecutionTrustFact(
                key="execution-conflicts",
                category="execution",
                status="conflicting",
                source_kind="deterministic",
                verification_status="not_applicable",
                freshness_status="not_applicable",
                label="执行冲突",
                detail="确定性检查发现当前路线存在不能忽略的执行冲突，需要先调整。",
                count=max(1, len(blocking_reasons)),
            )
        )

    fixed_count = sum(
        1
        for day in itinerary.days
        for block in day.blocks
        for item in block.items
        if item.is_fixed
    )
    if fixed_count:
        facts.append(
            ExecutionTrustFact(
                key="fixed-arrangements",
                category="fixed_event",
                status="confirmed",
                source_kind="user",
                verification_status="user_confirmed",
                freshness_status="not_applicable",
                label="固定安排",
                detail="这些时间边界来自用户确认或已锁定安排，路线不会把它们当作可随意移动的建议。",
                count=fixed_count,
            )
        )

    heuristic_count = sum(
        1
        for day in itinerary.days
        for block in day.blocks
        for item in block.items
        if item.source_type.value in {"auto_seeded_poi", "auto_seeded_meal", "auto_filled"}
    )
    if heuristic_count:
        facts.append(
            ExecutionTrustFact(
                key="system-suggestions",
                category="schedule",
                status="heuristic",
                source_kind="heuristic",
                verification_status="not_applicable",
                freshness_status="not_applicable",
                label="系统补充",
                detail="这些停留点和排序是系统建议，用于补齐路线，不等同于用户已确认的事实。",
                count=heuristic_count,
            )
        )

    if provider_summary is None:
        facts.append(
            ExecutionTrustFact(
                key="provider-evidence-unrecorded",
                category="route",
                status="unknown",
                source_kind="missing_data",
                verification_status="unknown",
                freshness_status="unknown",
                label="外部事实记录",
                detail="这版路线没有保存独立 provider evidence；不要把路线时间或地点详情当作实时确认。",
                count=0,
            )
        )
    else:
        _append_place_facts(facts, provider_summary)
        _append_route_facts(facts, provider_summary, warning_reasons)

    status = "blocked" if blocking_reasons else "needs_attention" if warning_reasons else "ready"
    headline = _headline(status, facts)
    return ExecutionTrustSummary(
        status=status,
        headline=headline,
        blocking_reasons=blocking_reasons,
        warning_reasons=warning_reasons,
        facts=facts,
    )


def _append_place_facts(facts: list[ExecutionTrustFact], provider: ProviderSnapshotSummary) -> None:
    if provider.place_known_count:
        facts.append(
            ExecutionTrustFact(
                key="place-facts",
                category="place",
                status="confirmed",
                source_kind="provider",
                verification_status="provider_returned",
                freshness_status="unknown",
                label="地点解析",
                detail="地点身份在规划时已获得 provider 返回；本次记录没有保存新鲜度时间戳。",
                count=provider.place_known_count,
            )
        )
    missing = provider.place_missing_count + provider.place_failed_count
    if missing:
        facts.append(
            ExecutionTrustFact(
                key="place-facts-missing",
                category="place",
                status="missing",
                source_kind="missing_data",
                verification_status="unavailable",
                freshness_status="unknown",
                label="地点事实缺失",
                detail="部分地点未获得可验证的 provider 详情，地址、营业信息或精确位置仍需复核。",
                count=missing,
            )
        )


def _append_route_facts(
    facts: list[ExecutionTrustFact],
    provider: ProviderSnapshotSummary,
    warning_reasons: list[str],
) -> None:
    if provider.route_known_count:
        facts.append(
            ExecutionTrustFact(
                key="route-facts",
                category="route",
                status="confirmed",
                source_kind="provider",
                verification_status="provider_returned",
                freshness_status="unknown",
                label="路线事实",
                detail="这些路线段在规划时获得 provider 返回；新鲜度未记录，不能视为实时路况。",
                count=provider.route_known_count,
            )
        )
    missing = provider.route_missing_count + provider.route_failed_count
    if missing:
        facts.append(
            ExecutionTrustFact(
                key="route-facts-missing",
                category="route",
                status="missing",
                source_kind="missing_data",
                verification_status="unavailable",
                freshness_status="unknown",
                label="路线事实缺失",
                detail="部分路线段没有可验证的 provider 数据，当前时间与距离仅用于规划估算。",
                count=missing,
            )
        )
        warning_reasons.append("部分路线没有可验证的 provider 数据，出发前应复核移动时间。")


def _headline(status: str, facts: list[ExecutionTrustFact]) -> str:
    if status == "blocked":
        return "当前路线存在执行冲突，先处理阻断项再按路线出行。"
    if status == "needs_attention":
        return "路线骨架可以继续查看，但仍有需要复核的执行事实。"
    if any(fact.freshness_status == "unknown" for fact in facts):
        return "路线骨架已形成；provider 事实的新鲜度未记录，出发前仍应复核。"
    return "路线、边界和已保存事实目前没有发现高优先级阻断。"
