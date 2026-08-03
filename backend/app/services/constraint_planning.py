from __future__ import annotations

import hashlib
import json
from datetime import time

from app.api.routes.itinerary import build_itinerary_response
from app.schemas.plan_candidates import (
    CandidateComparison, CandidateMetrics, ConflictCore, ConstraintEdge,
    ConstraintGraph, ConstraintNode, ConstraintSourceRef, PlanCandidate,
)
from app.schemas.trip_compiler import TravelIntent


STRATEGY_ORDER = ("relaxed", "balanced", "low_travel")


def canonical_digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def intent_digest(intent: TravelIntent) -> str:
    return canonical_digest(intent.model_dump(mode="json"))


def build_constraint_graph(intent: TravelIntent) -> ConstraintGraph:
    digest = intent_digest(intent)
    nodes: list[ConstraintNode] = []
    edges: list[ConstraintEdge] = []

    def add(node_id: str, kind: str, strength: str, status: str, label: str, source_ids: list[str]) -> None:
        nodes.append(ConstraintNode(
            id=node_id, kind=kind, strength=strength, status=status, label=label,
            source_refs=[ConstraintSourceRef(source_fragment_id=source_id) for source_id in source_ids],
        ))

    add("destination", "destination", "hard", "satisfied" if intent.destination else "unsatisfied", intent.destination or "未确认目的地", _source_ids(intent))
    add("trip_duration", "trip_duration", "hard", "satisfied" if intent.trip_days else "unsatisfied", f"{intent.trip_days or '未确认'} 天", _source_ids(intent))
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
    add("pace", "pace", "soft", "satisfied", {"relaxed": "轻松节奏", "balanced": "均衡节奏", "intensive": "紧凑节奏"}[intent.pace], _source_ids(intent))
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
        metrics = _metrics(itinerary, intent)
        skeleton = itinerary.model_dump(mode="json")
        candidate_hash = canonical_digest({"strategy": strategy, "intent_digest": graph.intent_digest, "itinerary": skeleton})
        candidates.append(PlanCandidate(
            id=f"candidate_{candidate_hash[:20]}", candidate_hash=candidate_hash, strategy=strategy,
            title={"relaxed": "留出更多空白", "balanced": "把想去的尽量安排进去", "low_travel": "少移动一些"}[strategy],
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
    return request.model_copy(update={"scenic_spots": [spot for spot in request.scenic_spots if spot.name not in optional_names]})


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
    window_minutes = len(itinerary.days) * ((3 * 60) + (4 * 60) + (3 * 60 + 30))
    return CandidateMetrics(
        fixed_coverage=fixed, must_coverage=must, optional_coverage=optional,
        total_travel_minutes=sum(travel_values) // 60 if travel_known else None,
        activity_minutes=activity, max_daily_activity_minutes=max(daily, default=0),
        free_buffer_minutes=max(0, window_minutes - activity), missing_travel_data=not travel_known,
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
    no_worse = a.fixed_coverage >= b.fixed_coverage and a.must_coverage >= b.must_coverage and a.optional_coverage >= b.optional_coverage and a.activity_minutes <= b.activity_minutes and a.free_buffer_minutes >= b.free_buffer_minutes and travel_no_worse
    better = a.fixed_coverage > b.fixed_coverage or a.must_coverage > b.must_coverage or a.optional_coverage > b.optional_coverage or a.activity_minutes < b.activity_minutes or a.free_buffer_minutes > b.free_buffer_minutes or travel_better
    return no_worse and better


def _tradeoff(strategy: str, metrics: CandidateMetrics) -> str:
    if strategy == "balanced":
        return f"保留全部必去地点，并安排 {metrics.optional_coverage} 个可调整地点。"
    return f"保留固定安排和必去地点，预留约 {metrics.free_buffer_minutes // 60} 小时弹性时间。"


def _comparison(candidate: PlanCandidate) -> CandidateComparison:
    metrics = candidate.metrics
    return CandidateComparison(candidate_id=candidate.id, highlights=[
        f"固定安排 {metrics.fixed_coverage} 个均保留", f"必去地点覆盖 {metrics.must_coverage} 个",
        f"可调整地点安排 {metrics.optional_coverage} 个", f"预留 {metrics.free_buffer_minutes // 60} 小时弹性时间",
    ])


def _source_ids(intent: TravelIntent, token: str | None = None) -> list[str]:
    fragments = intent.source_fragments
    if token:
        matched = [fragment.stable_id for fragment in fragments if token in fragment.text]
        if matched:
            return matched
    return [fragment.stable_id for fragment in fragments[:1]]


def _refs(ids: list[str]) -> list[ConstraintSourceRef]:
    return [ConstraintSourceRef(source_fragment_id=source_id) for source_id in dict.fromkeys(ids)]
