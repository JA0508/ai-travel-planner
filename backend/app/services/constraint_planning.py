from __future__ import annotations

from datetime import datetime, time

from app.api.routes.itinerary import build_itinerary_response
from app.schemas.plan_candidates import (
    CandidateComparison, CandidateMetrics, ConflictCore, ConstraintEdge,
    ConstraintGraph, ConstraintNode, ConstraintSourceRef, PlanCandidate,
)
from app.schemas.trip_compiler import TravelIntent
from app.trips.digests import sha256_digest
from app.trips.mutation_commands import ensure_stable_item_ids
from app.schemas.itinerary import ItineraryResponse


STRATEGY_ORDER = ("balanced", "relaxed", "low_travel")
PLANNER_POLICY_VERSION = "trip-compiler-candidates-v1"
SNAPSHOT_CONTRACT_VERSION = "planning-snapshot-v1"
METRIC_POLICY_VERSION = "candidate-metrics-v1"
STRATEGY_MANIFEST_VERSION = "candidate-strategies-v1"


def canonical_digest(value: object) -> str:
    return sha256_digest(value)


def intent_digest(intent: TravelIntent) -> str:
    payload = intent.model_dump(mode="json")
    # Source fragments are evidence, not a requested visit sequence. The UI can
    # reorder them for display without changing the planner's semantic input.
    payload["source_fragments"] = sorted(
        payload.get("source_fragments", []),
        key=lambda fragment: str(fragment.get("stable_id", "")),
    )
    _sort_provenance_reference_lists(payload)
    return canonical_digest(payload)


def _sort_provenance_reference_lists(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "source_fragment_ids" and isinstance(child, list):
                child.sort()
            else:
                _sort_provenance_reference_lists(child)
    elif isinstance(value, list):
        for child in value:
            _sort_provenance_reference_lists(child)


def build_planning_snapshot_manifest(
    *,
    intent: TravelIntent,
    graph: ConstraintGraph,
    candidates: list[PlanCandidate],
    strategy_inputs: dict[str, dict],
) -> tuple[dict, list[dict], list[dict], dict]:
    """Freeze the planner inputs actually used, without making another provider call."""
    poi_by_id: dict[str, dict] = {}
    route_segments: list[dict] = []
    for candidate in candidates:
        for day in candidate.itinerary.days:
            for block in day.blocks:
                for item in block.items:
                    poi_by_id.setdefault(item.stable_id or f"{item.name}:{item.latitude}:{item.longitude}", {
                        "stable_poi_identity": item.stable_id or item.name,
                        "canonical_name": item.name,
                        "city": item.city or intent.destination,
                        "coordinates": [item.latitude, item.longitude],
                        "category": item.type.value,
                        "duration_minutes": item.duration_minutes,
                        "opening_hour_status": "scheduler_accepted",
                        "source_status": "frozen_scheduler_input",
                    })
                    if item.travel_from_name:
                        route_segments.append({
                            "from_poi": item.travel_from_name,
                            "to_poi": item.name,
                            "travel_mode": intent.travel_mode.value if intent.travel_mode else None,
                            "duration_seconds": item.travel_duration_s,
                            "distance_meters": item.travel_distance_m,
                            "calculation_status": "known" if item.travel_duration_s is not None else "unknown",
                            "source": "frozen_scheduler_output",
                            "fallback_algorithm_version": "scheduler-route-v1",
                        })
    poi_snapshot = sorted(poi_by_id.values(), key=lambda item: item["stable_poi_identity"])
    route_snapshot = sorted(route_segments, key=lambda item: (item["from_poi"], item["to_poi"], item["travel_mode"] or ""))
    strategy_manifest = {
        "version": STRATEGY_MANIFEST_VERSION,
        "tie_breaker_version": "strategy-order-v1",
        "metric_policy_version": METRIC_POLICY_VERSION,
        "dominance_version": "pareto-v1",
        "candidate_ordering_version": "strategy-order-v1",
        "strategies": [{"candidate_id": candidate.id, "strategy": candidate.strategy, "input": strategy_inputs[candidate.id]} for candidate in candidates],
        "candidate_records": [
            {
                "candidate_id": candidate.id,
                "candidate_hash": candidate.candidate_hash,
                "strategy": candidate.strategy,
                "itinerary_digest": canonical_digest(candidate.itinerary.model_dump(mode="json")),
                "metrics_digest": canonical_digest(candidate.metrics.model_dump(mode="json")),
                "comparison_digest": canonical_digest(_comparison(candidate).model_dump(mode="json")),
            }
            for candidate in candidates
        ],
    }
    candidate_set_hash = canonical_digest([candidate.candidate_hash for candidate in candidates])
    manifest = {
        "snapshot_contract_version": SNAPSHOT_CONTRACT_VERSION,
        "planner_policy_version": PLANNER_POLICY_VERSION,
        "metric_policy_version": METRIC_POLICY_VERSION,
        "intent_digest": intent_digest(intent),
        "constraint_graph_digest": canonical_digest(graph.model_dump(mode="json")),
        "poi_snapshot_digest": canonical_digest(poi_snapshot),
        "route_snapshot_digest": canonical_digest(route_snapshot),
        "strategy_manifest_digest": canonical_digest(strategy_manifest),
        "candidate_set_hash": candidate_set_hash,
        "candidate_count": len(candidates),
    }
    return manifest, poi_snapshot, route_snapshot, strategy_manifest


def build_constraint_graph(intent: TravelIntent) -> ConstraintGraph:
    digest = intent_digest(intent)
    nodes: list[ConstraintNode] = []
    edges: list[ConstraintEdge] = []

    def add(node_id: str, kind: str, strength: str, status: str, label: str, source_ids: list[str]) -> None:
        nodes.append(ConstraintNode(
            id=node_id, kind=kind, strength=strength, status=status, label=label,
            source_refs=[ConstraintSourceRef(source_fragment_id=source_id) for source_id in source_ids],
        ))

    add("destination", "destination", "hard", "satisfied" if intent.destination else "unsatisfied", intent.destination or "未确认目的地", _source_ids(intent, intent.destination))
    add("trip_duration", "trip_duration", "hard", "satisfied" if intent.trip_days else "unsatisfied", f"{intent.trip_days or '未确认'} 天", _source_ids(intent, str(intent.trip_days) if intent.trip_days else None))
    if intent.date_window.get("arrival_time"):
        add("arrival", "arrival_boundary", "hard", "satisfied", f"第 1 天 {intent.date_window['arrival_time']} 后到达", _source_ids(intent, "arrival"))
    if intent.date_window.get("departure_time"):
        add("departure", "departure_boundary", "hard", "satisfied", f"最后一天 {intent.date_window['departure_time']} 前离开", _source_ids(intent, "departure"))
    for place in intent.must_visit_places:
        add(f"must:{place.stable_id}", "must_visit", "hard", "satisfied", place.name, place.source_fragment_ids)
    for place in intent.optional_places:
        add(f"optional:{place.stable_id}", "optional_visit", "soft", "satisfied", place.name, place.source_fragment_ids)
    for event in intent.fixed_events:
        node_id = f"fixed:{event.stable_id}"
        add(node_id, "fixed_event", "hard", "satisfied" if event.day and event.start_time and event.end_time else "unsatisfied", event.name, event.source_fragment_ids)
        edges.append(ConstraintEdge(from_node_id=node_id, to_node_id="trip_duration", relationship="bounds"))
    add("pace", "pace", "soft", "satisfied", {"relaxed": "轻松节奏", "balanced": "均衡节奏", "intensive": "紧凑节奏"}[intent.pace], _source_ids(intent, "赶" if intent.pace == "relaxed" else None))
    if intent.travel_mode:
        add("travel_mode", "travel_mode", "soft", "satisfied", intent.travel_mode.value, _source_ids(intent))
    for constraint in intent.constraints:
        kind = "arrival_boundary" if constraint.kind == "arrival" else "departure_boundary" if constraint.kind == "departure" else "daily_load"
        add(f"constraint:{constraint.stable_id}", kind, "hard" if constraint.hard else "soft", "satisfied", constraint.value, constraint.source_fragment_ids)
    for constraint in intent.avoid_items:
        add(f"avoid:{constraint.stable_id}", "avoidance", "hard" if constraint.hard else "soft", "satisfied", constraint.value, constraint.source_fragment_ids)
    return ConstraintGraph(intent_digest=digest, nodes=nodes, edges=edges)


def find_conflict_cores(intent: TravelIntent, graph: ConstraintGraph) -> list[ConflictCore]:
    cores: list[ConflictCore] = []
    arrival = intent.date_window.get("arrival_time")
    if arrival:
        for event in intent.fixed_events:
            if event.day == 1 and event.start_time and arrival > event.start_time:
                cores.append(ConflictCore(
                    code="arrival_after_fixed_event", node_ids=["arrival", f"fixed:{event.stable_id}"],
                    source_refs=_refs(_source_ids(intent, "arrival") + event.source_fragment_ids),
                    explanation=f"第 1 天到达时间晚于固定安排“{event.name}”的开始时间，无法同时满足。",
                ))
    events = [event for event in intent.fixed_events if event.day and event.start_time and event.end_time]
    for index, left in enumerate(events):
        for right in events[index + 1:]:
            if left.day == right.day and max(left.start_time or "", right.start_time or "") < min(left.end_time or "", right.end_time or ""):
                cores.append(ConflictCore(
                    code="fixed_event_overlap", node_ids=[f"fixed:{left.stable_id}", f"fixed:{right.stable_id}"],
                    source_refs=_refs(left.source_fragment_ids + right.source_fragment_ids),
                    explanation=f"固定安排“{left.name}”与“{right.name}”在第 {left.day} 天时间重叠，无法同时保留。",
                ))
    departure = intent.date_window.get("departure_time")
    if departure:
        for event in events:
            if event.day == intent.trip_days and event.end_time and event.end_time > departure:
                cores.append(ConflictCore(
                    code="departure_before_required_activity", node_ids=["departure", f"fixed:{event.stable_id}"],
                    source_refs=_refs(_source_ids(intent, "departure") + event.source_fragment_ids),
                    explanation=f"固定安排“{event.name}”结束时间晚于最后一天返程时间，无法同时满足。",
                ))
    return cores


def generate_candidates(intent: TravelIntent) -> tuple[ConstraintGraph, list[ConflictCore], list[PlanCandidate], list[CandidateComparison]]:
    graph = build_constraint_graph(intent)
    cores = find_conflict_cores(intent, graph)
    if cores:
        return graph, cores, [], []
    candidates: list[PlanCandidate] = []
    for strategy in STRATEGY_ORDER:
        request = itinerary_request_for_strategy(intent, strategy)
        try:
            itinerary = build_itinerary_response(request)
        except Exception:
            continue
        # Candidate snapshots are the exact source of Revision 1. Give every
        # scheduled item its stable identity before candidate hashing, selection,
        # manifest creation, and any later safe patch all see the same route.
        itinerary = ItineraryResponse.model_validate(
            ensure_stable_item_ids(itinerary.model_dump(mode="json"))
        )
        metrics = _metrics(itinerary, intent)
        skeleton = itinerary.model_dump(mode="json")
        candidate_hash = canonical_digest({"strategy": strategy, "intent_digest": graph.intent_digest, "itinerary": skeleton})
        candidates.append(PlanCandidate(
            id=f"candidate_{candidate_hash[:20]}", candidate_hash=candidate_hash, strategy=strategy,
            title=_title(strategy, metrics),
            tradeoff_summary=_tradeoff(strategy, metrics), itinerary=itinerary, constraint_graph=graph,
            applied_constraint_ids=[node.id for node in graph.nodes if node.strength == "hard"],
            relaxed_constraint_ids=[f"optional:{place.stable_id}" for place in intent.optional_places] if strategy != "balanced" else [],
            unsatisfied_constraint_ids=[], metrics=metrics,
        ))
    frontier = _pareto_frontier(candidates)
    return graph, [], frontier, [_comparison(candidate) for candidate in frontier]


def itinerary_request_for_strategy(intent: TravelIntent, strategy: str):
    from app.services.trip_compiler import build_itinerary_request

    request = build_itinerary_request(intent)
    if strategy == "balanced":
        return request
    optional_names = {place.name for place in intent.optional_places}
    if strategy == "relaxed":
        return request.model_copy(update={"scenic_spots": [spot for spot in request.scenic_spots if spot.name not in optional_names]})
    # Low travel keeps optional places but supplies a stable locality-first order to
    # the existing deterministic scheduler. It never claims a travel advantage when
    # the resulting route data is incomplete.
    scenic = sorted(
        request.scenic_spots,
        key=lambda spot: (spot.resolved_latitude is None, spot.resolved_latitude or 0, spot.resolved_longitude or 0, spot.name),
    )
    return request.model_copy(update={"scenic_spots": scenic})


def _metrics(itinerary, intent: TravelIntent) -> CandidateMetrics:
    items = [item for day in itinerary.days for block in day.blocks for item in block.items]
    fixed = sum(1 for item in items if item.is_fixed)
    names = {item.name for item in items}
    must = sum(place.name in names for place in intent.must_visit_places)
    optional = sum(place.name in names for place in intent.optional_places)
    travel_values = [item.travel_duration_s for item in items if item.travel_duration_s is not None]
    travel_known = len(travel_values) == len([item for item in items if item.travel_from_name])
    activity = sum(item.duration_minutes for item in items)
    daily = [sum(item.duration_minutes for block in day.blocks for item in block.items) for day in itinerary.days]
    day_windows = _daily_windows(intent, itinerary)
    daily_travel = [sum(item.travel_duration_s or 0 for block in day.blocks for item in block.items) // 60 for day in itinerary.days]
    daily_slack = [max(0, window["available_window_minutes"] - duration - travel) for window, duration, travel in zip(day_windows, daily, daily_travel)]
    known_segments = [item for item in items if item.travel_from_name]
    completeness = "complete" if known_segments and travel_known else "missing" if not travel_values else "partial"
    return CandidateMetrics(
        fixed_coverage=fixed, must_coverage=must, optional_coverage=optional,
        total_travel_minutes=sum(travel_values) // 60 if travel_known else None,
        activity_minutes=activity, max_daily_activity_minutes=max(daily, default=0),
        free_buffer_minutes=sum(daily_slack), missing_travel_data=not travel_known,
        minimum_daily_slack_minutes=min(daily_slack, default=0),
        rushed_day_count=sum(slack < 60 for slack in daily_slack),
        infeasible_day_count=sum((window["available_window_minutes"] - duration - travel) < 0 for window, duration, travel in zip(day_windows, daily, daily_travel)),
        risk_count=sum(1 for window in day_windows if window["available_window_minutes"] < 180),
        travel_data_completeness=completeness,
        daily_windows=[{**window, "activity_minutes": duration, "travel_minutes": travel, "slack_minutes": slack} for window, duration, travel, slack in zip(day_windows, daily, daily_travel, daily_slack)],
    )


def _pareto_frontier(candidates: list[PlanCandidate]) -> list[PlanCandidate]:
    unique: list[PlanCandidate] = []
    signatures: set[str] = set()
    for candidate in candidates:
        signature = canonical_digest(candidate.itinerary.model_dump(mode="json"))
        if signature not in signatures:
            signatures.add(signature)
            unique.append(candidate)
    result = [candidate for candidate in unique if not any(_dominates(other, candidate) for other in unique if other.id != candidate.id)]
    return sorted(result, key=lambda item: (STRATEGY_ORDER.index(item.strategy), item.id))[:3]


def _dominates(left: PlanCandidate, right: PlanCandidate) -> bool:
    a, b = left.metrics, right.metrics
    if a.total_travel_minutes is None or b.total_travel_minutes is None:
        travel_no_worse = True
        travel_better = False
    else:
        travel_no_worse, travel_better = a.total_travel_minutes <= b.total_travel_minutes, a.total_travel_minutes < b.total_travel_minutes
    no_worse = a.fixed_coverage >= b.fixed_coverage and a.must_coverage >= b.must_coverage and a.optional_coverage >= b.optional_coverage and a.activity_minutes <= b.activity_minutes and a.minimum_daily_slack_minutes >= b.minimum_daily_slack_minutes and travel_no_worse
    better = a.fixed_coverage > b.fixed_coverage or a.must_coverage > b.must_coverage or a.optional_coverage > b.optional_coverage or a.activity_minutes < b.activity_minutes or a.minimum_daily_slack_minutes > b.minimum_daily_slack_minutes or travel_better
    return no_worse and better


def _tradeoff(strategy: str, metrics: CandidateMetrics) -> str:
    if strategy == "balanced":
        return f"保留全部必去地点，并安排 {metrics.optional_coverage} 个可调整地点。"
    if strategy == "low_travel" and metrics.travel_data_completeness == "complete":
        return f"保留全部地点，预计移动 {metrics.total_travel_minutes} 分钟。"
    return f"保留固定安排和必去地点，最少每天预留 {metrics.minimum_daily_slack_minutes} 分钟弹性时间。"


def _comparison(candidate: PlanCandidate) -> CandidateComparison:
    metrics = candidate.metrics
    return CandidateComparison(candidate_id=candidate.id, highlights=[
        f"固定安排 {metrics.fixed_coverage} 个均保留", f"必去地点覆盖 {metrics.must_coverage} 个",
        f"可调整地点安排 {metrics.optional_coverage} 个", f"最少每天预留 {metrics.minimum_daily_slack_minutes} 分钟",
    ])


def _source_ids(intent: TravelIntent, token: str | None = None) -> list[str]:
    fragments = intent.source_fragments
    if token:
        matched = [fragment.stable_id for fragment in fragments if token in fragment.text]
        if matched:
            return matched
    return []


def _refs(ids: list[str]) -> list[ConstraintSourceRef]:
    return [ConstraintSourceRef(source_fragment_id=source_id) for source_id in dict.fromkeys(ids)]


def _daily_windows(intent: TravelIntent, itinerary) -> list[dict[str, object]]:
    windows: list[dict[str, object]] = []
    for day in itinerary.days:
        start, end = "09:00", "20:00"
        if day.day == 1 and intent.date_window.get("arrival_time"):
            start = max(start, intent.date_window["arrival_time"])
        if day.day == itinerary.trip_days and intent.date_window.get("departure_time"):
            end = min(end, intent.date_window["departure_time"])
        start_minutes = _minutes(start)
        end_minutes = _minutes(end)
        windows.append({"day": day.day, "available_start": start, "available_end": end, "available_window_minutes": max(0, end_minutes - start_minutes)})
    return windows


def _minutes(value: str) -> int:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def _title(strategy: str, metrics: CandidateMetrics) -> str:
    if strategy == "balanced":
        return "保留更多想去地点"
    if strategy == "low_travel" and metrics.travel_data_completeness == "complete":
        return "少走一些路"
    if strategy == "relaxed":
        return "留出更多空白"
    return "路线方案"
