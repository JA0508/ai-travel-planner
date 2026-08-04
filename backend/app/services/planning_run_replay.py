from __future__ import annotations

import json
from contextlib import closing

from app.schemas.plan_candidates import ReplayDifference, ReplayResult
from app.services.constraint_planning import (
    METRIC_POLICY_VERSION,
    PLANNER_POLICY_VERSION,
    SNAPSHOT_CONTRACT_VERSION,
    canonical_digest,
)
from app.services.planning_run_repository import SQLitePlanningRunRepository, _now


def replay_planning_run(repository: SQLitePlanningRunRepository, planning_run_id: str) -> ReplayResult:
    """Verify a frozen planning decision without parsing, provider calls, or Trip writes."""
    with closing(repository.connection_factory()) as connection:
        run = connection.execute("SELECT * FROM planning_runs WHERE id = ?", (planning_run_id,)).fetchone()
        if run is None:
            return ReplayResult(status="planning_run_not_found", planning_run_id=planning_run_id)
        if run["planner_policy_version"] != PLANNER_POLICY_VERSION:
            return ReplayResult(
                status="unsupported_policy_version", planning_run_id=planning_run_id,
                planner_policy_version=run["planner_policy_version"],
            )
        try:
            manifest = json.loads(run["snapshot_manifest_json"])
            poi_snapshot = json.loads(run["poi_snapshot_json"])
            route_snapshot = json.loads(run["route_snapshot_json"])
            strategy_manifest = json.loads(run["strategy_manifest_json"])
        except (TypeError, json.JSONDecodeError):
            return ReplayResult(status="invalid_snapshot", planning_run_id=planning_run_id, planner_policy_version=run["planner_policy_version"])
        expected_hashes = {
            "intent_digest": run["intent_digest"],
            "constraint_graph_digest": canonical_digest(json.loads(run["constraint_graph_json"])),
            "poi_snapshot_digest": canonical_digest(poi_snapshot),
            "route_snapshot_digest": canonical_digest(route_snapshot),
            "strategy_manifest_digest": canonical_digest(strategy_manifest),
            "candidate_set_hash": run["candidate_set_hash"],
        }
        if manifest.get("snapshot_contract_version") != SNAPSHOT_CONTRACT_VERSION or manifest.get("metric_policy_version") != METRIC_POLICY_VERSION:
            return ReplayResult(status="invalid_snapshot", planning_run_id=planning_run_id, planner_policy_version=run["planner_policy_version"])
        manifest_differences = [
            ReplayDifference(kind="snapshot_digest", expected=value, actual=manifest.get(name))
            for name, value in expected_hashes.items() if manifest.get(name) != value
        ]
        if manifest_differences:
            return _persist_result(repository, ReplayResult(
                status="invalid_snapshot", planning_run_id=planning_run_id,
                planner_policy_version=run["planner_policy_version"], differences=manifest_differences,
            ))

        expected_candidates = strategy_manifest.get("candidate_records")
        if not isinstance(expected_candidates, list):
            return ReplayResult(status="invalid_snapshot", planning_run_id=planning_run_id, planner_policy_version=run["planner_policy_version"])
        actual_rows = connection.execute(
            "SELECT * FROM planning_run_candidates WHERE planning_run_id = ? ORDER BY rank", (planning_run_id,)
        ).fetchall()
    differences = _candidate_differences(expected_candidates, actual_rows)
    actual_set_hash = canonical_digest([row["candidate_hash"] for row in actual_rows])
    if actual_set_hash != expected_hashes["candidate_set_hash"]:
        differences.append(ReplayDifference(kind="candidate_set_hash", expected=expected_hashes["candidate_set_hash"], actual=actual_set_hash))
    result = ReplayResult(
        status="verified" if not differences else "mismatch",
        planning_run_id=planning_run_id,
        planner_policy_version=run["planner_policy_version"],
        expected_candidate_set_hash=expected_hashes["candidate_set_hash"],
        actual_candidate_set_hash=actual_set_hash,
        differences=differences,
    )
    return _persist_result(repository, result)


def _candidate_differences(expected: list[dict], actual_rows) -> list[ReplayDifference]:
    differences: list[ReplayDifference] = []
    if len(expected) != len(actual_rows):
        differences.append(ReplayDifference(kind="candidate_count", expected=len(expected), actual=len(actual_rows)))
    for index, expected_item in enumerate(expected):
        if index >= len(actual_rows):
            differences.append(ReplayDifference(kind="candidate_missing", candidate_id=expected_item.get("candidate_id"), expected=expected_item, actual=None))
            continue
        row = actual_rows[index]
        candidate_id = expected_item.get("candidate_id")
        if row["candidate_id"] != candidate_id or row["strategy"] != expected_item.get("strategy"):
            differences.append(ReplayDifference(kind="candidate_order", candidate_id=candidate_id, expected={"candidate_id": candidate_id, "strategy": expected_item.get("strategy")}, actual={"candidate_id": row["candidate_id"], "strategy": row["strategy"]}))
        if row["candidate_hash"] != expected_item.get("candidate_hash"):
            differences.append(ReplayDifference(kind="candidate_hash", candidate_id=candidate_id, expected=expected_item.get("candidate_hash"), actual=row["candidate_hash"]))
        if canonical_digest(json.loads(row["itinerary_snapshot_json"])) != expected_item.get("itinerary_digest"):
            differences.append(ReplayDifference(kind="candidate_itinerary", candidate_id=candidate_id, expected=expected_item.get("itinerary_digest"), actual=canonical_digest(json.loads(row["itinerary_snapshot_json"]))))
        if canonical_digest(json.loads(row["metrics_json"])) != expected_item.get("metrics_digest"):
            differences.append(ReplayDifference(kind="candidate_metrics", candidate_id=candidate_id, expected=expected_item.get("metrics_digest"), actual=canonical_digest(json.loads(row["metrics_json"]))))
    return differences


def _persist_result(repository: SQLitePlanningRunRepository, result: ReplayResult) -> ReplayResult:
    # Replay may append an audit event but never mutates a snapshot, candidate, Trip, or Revision.
    repository.append_replay_event(
        run_id=result.planning_run_id,
        result="verified" if result.status == "verified" else "mismatch",
        metadata={"status": result.status, "difference_count": len(result.differences)},
    )
    return result
