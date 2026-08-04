from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.schemas.plan_candidates import PlanningRunRecordResponse
from app.schemas.trip_compiler import TravelIntent
from app.services.constraint_planning import (
    PLANNER_POLICY_VERSION,
    SNAPSHOT_CONTRACT_VERSION,
    build_planning_snapshot_manifest,
    canonical_digest,
    generate_candidates,
    intent_digest,
    itinerary_request_for_strategy,
)
from app.trips.access import generate_capability, hash_capability


class PlanningRunCreationError(ValueError):
    def __init__(self, code: str, message: str, *, conflict_cores: list[dict] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.conflict_cores = conflict_cores or []


@dataclass(frozen=True)
class CreatedPlanningRun:
    record: PlanningRunRecordResponse
    capability: str


def create_planning_run_from_confirmed_intent(
    *,
    intent: TravelIntent,
    source_context: dict[str, str] | None = None,
) -> CreatedPlanningRun:
    """Create the existing persisted Planning Run from a confirmed intent view.

    This is shared orchestration only: candidate generation, snapshots, selection,
    idempotency, and TripRevision materialisation remain in their existing owners.
    """

    # Import lazily: the repository dependency also exposes Trip persistence,
    # while this helper is called from the Draft Trip service during app startup.
    from app.services.planning_run_dependencies import get_planning_run_repository

    graph, cores, candidates, comparison = generate_candidates(intent)
    if cores:
        raise PlanningRunCreationError(
            "hard_constraint_conflict",
            "当前确认的信息无法同时满足。",
            conflict_cores=[core.model_dump(mode="json") for core in cores],
        )
    if not candidates:
        raise PlanningRunCreationError("planning_run_empty", "当前信息无法生成可执行路线候选。")
    capability = generate_capability()
    run_id = f"planning_run_{uuid4().hex}"
    now = datetime.now(timezone.utc)
    strategy_inputs = {
        candidate.id: itinerary_request_for_strategy(intent, candidate.strategy).model_dump(mode="json")
        for candidate in candidates
    }
    manifest, poi_snapshot, route_snapshot, strategy_manifest = build_planning_snapshot_manifest(
        intent=intent,
        graph=graph,
        candidates=candidates,
        strategy_inputs=strategy_inputs,
    )
    if source_context:
        strategy_manifest = {**strategy_manifest, "intent_source_context": source_context}
        manifest = {**manifest, "intent_source_context": source_context}
    record = get_planning_run_repository().create(
        run_id=run_id,
        capability_hash=hash_capability(capability),
        intent_digest=intent_digest(intent),
        intent_json=intent.model_dump(mode="json"),
        graph=graph,
        candidates=candidates,
        comparison=comparison,
        strategy_inputs=strategy_inputs,
        planner_policy_version=PLANNER_POLICY_VERSION,
        snapshot_contract_version=SNAPSHOT_CONTRACT_VERSION,
        candidate_set_hash=canonical_digest([candidate.candidate_hash for candidate in candidates]),
        poi_snapshot=poi_snapshot,
        route_snapshot=route_snapshot,
        strategy_manifest=strategy_manifest,
        snapshot_manifest=manifest,
        created_at=now.isoformat().replace("+00:00", "Z"),
        expires_at=(now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
    )
    return CreatedPlanningRun(record=record, capability=capability)
