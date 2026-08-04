from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterator, TYPE_CHECKING

from app.schemas.plan_candidates import (
    CandidateComparison,
    ConstraintGraph,
    PlanCandidate,
    PlanningRunHistoryResponse,
    PlanningRunRecordResponse,
)
from app.trips.digests import canonical_json, sha256_digest

if TYPE_CHECKING:
    from app.persistence.sqlite_trip_repository import SQLiteTripRepository


class PlanningRunError(ValueError):
    def __init__(self, code: str, message: str, *, recoverable: bool = True, selected_candidate_id: str | None = None, trip_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable
        self.selected_candidate_id = selected_candidate_id
        self.trip_id = trip_id


@dataclass(frozen=True)
class StoredPlanningRun:
    id: str
    status: str
    capability_hash: str
    intent_digest: str
    intent_json: dict
    constraint_graph: ConstraintGraph
    planner_policy_version: str
    snapshot_contract_version: str
    candidate_set_hash: str
    created_at: str
    expires_at: str
    selected_candidate_id: str | None
    trip_id: str | None
    selection_idempotency_key_hash: str | None
    selection_request_digest: str | None


@dataclass(frozen=True)
class PlanningSelectionResult:
    trip_id: str
    idempotent_replay: bool


class SQLitePlanningRunRepository:
    def __init__(self, connection_factory) -> None:
        self.connection_factory = connection_factory

    def create(
        self,
        *,
        run_id: str,
        capability_hash: str,
        intent_digest: str,
        intent_json: dict,
        graph: ConstraintGraph,
        candidates: list[PlanCandidate],
        comparison: list[CandidateComparison],
        strategy_inputs: dict[str, dict],
        planner_policy_version: str,
        snapshot_contract_version: str,
        candidate_set_hash: str,
        poi_snapshot: list[dict],
        route_snapshot: list[dict],
        strategy_manifest: dict,
        snapshot_manifest: dict,
        created_at: str,
        expires_at: str,
    ) -> PlanningRunRecordResponse:
        comparison_by_id = {item.candidate_id: item.model_dump(mode="json") for item in comparison}
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO planning_runs(id, status, capability_hash, intent_digest, confirmed_intent_json,
                   constraint_graph_json, planner_policy_version, snapshot_contract_version, candidate_set_hash,
                   poi_snapshot_json, route_snapshot_json, strategy_manifest_json, snapshot_manifest_json,
                   created_at, expires_at)
                   VALUES (?, 'generated', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, capability_hash, intent_digest, canonical_json(intent_json), canonical_json(graph.model_dump(mode="json")),
                 planner_policy_version, snapshot_contract_version, candidate_set_hash, canonical_json(poi_snapshot),
                 canonical_json(route_snapshot), canonical_json(strategy_manifest), canonical_json(snapshot_manifest),
                 created_at, expires_at),
            )
            self._append_event(connection, run_id, "planning_run_created", created_at, {"policy_version": planner_policy_version})
            self._append_event(connection, run_id, "constraint_graph_built", created_at, {"constraint_count": len(graph.nodes)})
            for rank, candidate in enumerate(candidates, start=1):
                connection.execute(
                    """INSERT INTO planning_run_candidates(planning_run_id, candidate_id, candidate_hash, strategy,
                       itinerary_snapshot_json, metrics_json, comparison_json, strategy_input_json, rank, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (run_id, candidate.id, candidate.candidate_hash, candidate.strategy,
                     canonical_json(candidate.itinerary.model_dump(mode="json")), canonical_json(candidate.metrics.model_dump(mode="json")),
                     canonical_json(comparison_by_id.get(candidate.id, {})), canonical_json(strategy_inputs[candidate.id]), rank, created_at),
                )
            self._append_event(connection, run_id, "candidates_generated", created_at, {"candidate_count": len(candidates), "candidate_set_hash_prefix": candidate_set_hash[:12]})
        return self.get(run_id=run_id, capability_hash=capability_hash)

    def get(self, *, run_id: str, capability_hash: str) -> PlanningRunRecordResponse:
        with self._transaction() as connection:
            run = self._require_run(connection, run_id, capability_hash)
            self._expire_if_needed(connection, run)
            return self._response_from_connection(connection, run_id)

    def get_stored(self, *, run_id: str, capability_hash: str) -> StoredPlanningRun:
        with closing(self.connection_factory()) as connection:
            run = self._require_run(connection, run_id, capability_hash)
            return run

    def find_run_for_candidate(self, *, candidate_id: str, capability_hash: str) -> str:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """SELECT runs.id FROM planning_runs AS runs
                   JOIN planning_run_candidates AS candidates ON candidates.planning_run_id = runs.id
                   WHERE candidates.candidate_id = ? AND runs.capability_hash = ?""",
                (candidate_id, capability_hash),
            ).fetchone()
        if row is None:
            raise PlanningRunError("planning_run_access_denied", "无法访问这份路线方案。", recoverable=False)
        return str(row["id"])

    def select_candidate_atomically(
        self,
        *,
        trip_repository: "SQLiteTripRepository",
        run_id: str,
        candidate_id: str,
        candidate_hash: str,
        intent_digest: str,
        planning_capability_hash: str,
        trip_capability_hash: str,
        idempotency_key_hash: str,
        request_digest: str,
        failure_hook: Callable[[str], None] | None = None,
    ) -> PlanningSelectionResult:
        """Select one immutable candidate and materialize its first revision atomically."""
        with self._transaction() as connection:
            run = self._require_run(connection, run_id, planning_capability_hash)
            self._expire_if_needed(connection, run)
            run = self._require_run(connection, run_id, planning_capability_hash)
            if run.status == "expired":
                raise PlanningRunError("planning_run_expired", "这批路线方案已经过期，请重新生成。")
            if run.status == "selected":
                if run.selection_idempotency_key_hash == idempotency_key_hash:
                    if run.selection_request_digest != request_digest:
                        raise PlanningRunError("idempotency_payload_mismatch", "同一请求标识不能选择不同路线。", recoverable=False)
                    if run.selected_candidate_id != candidate_id or not run.trip_id:
                        raise PlanningRunError("idempotency_payload_mismatch", "同一请求标识不能选择不同路线。", recoverable=False)
                    # The original HTTP response may have been lost after the
                    # transaction committed, so the browser might never have
                    # received the Trip capability cookie. The Planning Run
                    # capability plus the bound idempotency request authorizes
                    # one safe capability rotation for the already-created Trip.
                    connection.execute(
                        "UPDATE trips SET capability_hash = ?, updated_at = ? WHERE id = ?",
                        (trip_capability_hash, _now(), run.trip_id),
                    )
                    self._append_event(connection, run_id, "selection_replayed", _now(), {"candidate_id": candidate_id})
                    return PlanningSelectionResult(trip_id=run.trip_id, idempotent_replay=True)
                raise PlanningRunError(
                    "planning_run_already_selected",
                    "这批路线已经保存。",
                    selected_candidate_id=run.selected_candidate_id,
                    trip_id=run.trip_id,
                )
            if run.status != "generated":
                raise PlanningRunError("planning_run_not_selectable", "这批路线暂时无法选择，请刷新后重试。")
            if run.intent_digest != intent_digest:
                raise PlanningRunError("candidate_mismatch", "这份路线候选与当前确认信息不一致，请重新生成。")
            candidate_row = connection.execute(
                "SELECT * FROM planning_run_candidates WHERE planning_run_id = ? AND candidate_id = ?",
                (run_id, candidate_id),
            ).fetchone()
            if candidate_row is None or candidate_row["candidate_hash"] != candidate_hash:
                raise PlanningRunError("candidate_mismatch", "这份路线候选与当前确认信息不一致，请重新生成。")

            operation_id = f"selection_{uuid.uuid4().hex}"
            reserved = connection.execute(
                """UPDATE planning_runs SET status = 'selecting', selection_operation_id = ?
                   WHERE id = ? AND status = 'generated' AND selected_candidate_id IS NULL""",
                (operation_id, run_id),
            )
            if reserved.rowcount != 1:
                raise PlanningRunError("planning_run_already_selected", "这批路线已经保存。")
            self._append_event(connection, run_id, "candidate_selection_started", _now(), {"candidate_id": candidate_id})
            _fail_if_requested(failure_hook, "after_selection_reserved")
            _fail_if_requested(failure_hook, "before_revision_inserted")

            snapshot_manifest = json.loads(connection.execute(
                "SELECT snapshot_manifest_json FROM planning_runs WHERE id = ?", (run_id,)
            ).fetchone()["snapshot_manifest_json"])

            lineage_metadata = {
                "root_planning_run_id": run_id,
                "selected_candidate_id": candidate_id,
                "selected_candidate_hash": candidate_hash,
                "intent_digest": intent_digest,
                "constraint_graph_digest": sha256_digest(run.constraint_graph.model_dump(mode="json")),
                "poi_snapshot_digest": snapshot_manifest.get("poi_snapshot_digest"),
                "route_snapshot_digest": snapshot_manifest.get("route_snapshot_digest"),
                "planner_policy_version": run.planner_policy_version,
                "snapshot_contract_version": run.snapshot_contract_version,
                "candidate_set_hash": run.candidate_set_hash,
                "source": "candidate_selection",
            }
            trip_id = trip_repository.create_trip_with_initial_revision_in_transaction(
                connection,
                itinerary_snapshot=json.loads(candidate_row["itinerary_snapshot_json"]),
                capability_hash=trip_capability_hash,
                operation_type="select_planning_run_candidate",
                operation_summary="Created initial trip revision from a persisted planning candidate.",
                request_digest=request_digest,
                planner_run_id=run_id,
                planner_version=run.planner_policy_version,
                trace_schema_version=run.snapshot_contract_version,
                trace_digest=run.candidate_set_hash,
                operation_metadata=lineage_metadata,
            )
            _fail_if_requested(failure_hook, "after_trip_inserted")
            _fail_if_requested(failure_hook, "after_revision_inserted")

            _fail_if_requested(failure_hook, "before_planning_run_selected")
            selected = connection.execute(
                """UPDATE planning_runs
                   SET status = 'selected', selected_candidate_id = ?, selected_at = ?, trip_id = ?,
                       revision_number = 1, selection_operation_id = ?, selection_idempotency_key_hash = ?,
                       selection_request_digest = ?
                   WHERE id = ? AND status = 'selecting' AND selected_candidate_id IS NULL""",
                (candidate_id, _now(), trip_id, operation_id, idempotency_key_hash, request_digest, run_id),
            )
            if selected.rowcount != 1:
                raise PlanningRunError("planning_run_already_selected", "这批路线已经保存。")
            self._append_event(connection, run_id, "candidate_selected", _now(), {"candidate_id": candidate_id})
            self._append_event(connection, run_id, "trip_revision_created", _now(), {"trip_id": trip_id, "revision_number": 1})
            return PlanningSelectionResult(trip_id=trip_id, idempotent_replay=False)

    def history(self, *, run_id: str, capability_hash: str) -> PlanningRunHistoryResponse:
        with closing(self.connection_factory()) as connection:
            run = self._require_run(connection, run_id, capability_hash)
            events = connection.execute("SELECT event_type, occurred_at, metadata_json FROM planning_run_events WHERE planning_run_id = ? ORDER BY occurred_at, event_id", (run_id,)).fetchall()
        summary = [f"你确认了 {len([node for node in run.constraint_graph.nodes if node.kind == 'must_visit'])} 个必去地点"]
        fixed = len([node for node in run.constraint_graph.nodes if node.kind == "fixed_event"])
        if fixed:
            summary.append(f"系统保留了 {fixed} 个固定安排")
        summary.append(f"系统生成了 {len(self._candidate_rows(run_id))} 套可执行路线")
        if run.status == "selected":
            summary.append("这份路线已保存为第一版")
        evidence = [{"label": node.label, "kind": _label_for_kind(node.kind)} for node in run.constraint_graph.nodes if node.source_refs]
        return PlanningRunHistoryResponse(summary=summary, evidence=evidence, status=run.status, selected_candidate_id=run.selected_candidate_id, trip_id=run.trip_id)

    def append_replay_event(self, *, run_id: str, result: str, metadata: dict) -> None:
        with self._transaction() as connection:
            self._append_event(connection, run_id, "replay_verified" if result == "verified" else "replay_mismatch", _now(), metadata)

    def _candidate_rows(self, run_id: str):
        with closing(self.connection_factory()) as connection:
            return connection.execute("SELECT * FROM planning_run_candidates WHERE planning_run_id = ? ORDER BY rank", (run_id,)).fetchall()

    def _response_from_connection(self, connection: sqlite3.Connection, run_id: str) -> PlanningRunRecordResponse:
        run = connection.execute("SELECT * FROM planning_runs WHERE id = ?", (run_id,)).fetchone()
        candidates_rows = connection.execute("SELECT * FROM planning_run_candidates WHERE planning_run_id = ? ORDER BY rank", (run_id,)).fetchall()
        stored = self._row_to_stored(run)
        candidates = [self._candidate_from_row(stored, row) for row in candidates_rows]
        comparisons = [CandidateComparison.model_validate(json.loads(row["comparison_json"])) for row in candidates_rows if json.loads(row["comparison_json"])]
        return PlanningRunRecordResponse(
            planning_run_id=stored.id,
            status=stored.status,
            expires_at=stored.expires_at,
            intent_digest=stored.intent_digest,
            confirmed_intent=stored.intent_json,
            constraint_graph=stored.constraint_graph,
            candidates=candidates,
            comparison=comparisons,
            selected_candidate_id=stored.selected_candidate_id,
            trip_id=stored.trip_id,
        )

    def _candidate_from_row(self, run: StoredPlanningRun, row: sqlite3.Row) -> PlanCandidate:
        return PlanCandidate(
            id=row["candidate_id"], candidate_hash=row["candidate_hash"], strategy=row["strategy"],
            title=_candidate_title(row["strategy"]), tradeoff_summary=_candidate_tradeoff(row["strategy"], json.loads(row["metrics_json"])),
            itinerary=json.loads(row["itinerary_snapshot_json"]), constraint_graph=run.constraint_graph,
            applied_constraint_ids=[node.id for node in run.constraint_graph.nodes if node.strength == "hard"],
            relaxed_constraint_ids=[], unsatisfied_constraint_ids=[], metrics=json.loads(row["metrics_json"]),
        )

    def _require_run(self, connection: sqlite3.Connection, run_id: str, capability_hash: str) -> StoredPlanningRun:
        row = connection.execute("SELECT * FROM planning_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None or row["capability_hash"] != capability_hash:
            raise PlanningRunError("planning_run_access_denied", "无法访问这份路线方案。", recoverable=False)
        return self._row_to_stored(row)

    def _expire_if_needed(self, connection: sqlite3.Connection, run: StoredPlanningRun) -> None:
        if run.status in {"generated", "selecting"} and _parse_time(run.expires_at) <= datetime.now(timezone.utc):
            connection.execute("UPDATE planning_runs SET status = 'expired' WHERE id = ?", (run.id,))
            self._append_event(connection, run.id, "planning_run_expired", _now(), {})

    def _row_to_stored(self, row: sqlite3.Row) -> StoredPlanningRun:
        return StoredPlanningRun(id=row["id"], status=row["status"], capability_hash=row["capability_hash"], intent_digest=row["intent_digest"], intent_json=json.loads(row["confirmed_intent_json"]), constraint_graph=ConstraintGraph.model_validate(json.loads(row["constraint_graph_json"])), planner_policy_version=row["planner_policy_version"], snapshot_contract_version=row["snapshot_contract_version"], candidate_set_hash=row["candidate_set_hash"], created_at=row["created_at"], expires_at=row["expires_at"], selected_candidate_id=row["selected_candidate_id"], trip_id=row["trip_id"], selection_idempotency_key_hash=row["selection_idempotency_key_hash"], selection_request_digest=row["selection_request_digest"])

    def _reject(self, connection: sqlite3.Connection, run_id: str, code: str) -> None:
        self._append_event(connection, run_id, "selection_rejected", _now(), {"code": code})

    def _append_event(self, connection: sqlite3.Connection, run_id: str, event_type: str, occurred_at: str, metadata: dict) -> None:
        import uuid
        connection.execute("INSERT INTO planning_run_events(event_id, planning_run_id, event_type, occurred_at, metadata_json) VALUES (?, ?, ?, ?, ?)", (f"plan_evt_{uuid.uuid4().hex}", run_id, event_type, occurred_at, canonical_json(metadata)))

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connection_factory()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fail_if_requested(hook: Callable[[str], None] | None, point: str) -> None:
    if hook is not None:
        hook(point)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _candidate_title(strategy: str) -> str:
    return {"relaxed": "留出更多空白", "balanced": "保留更多想去地点", "low_travel": "少走一些路"}[strategy]


def _candidate_tradeoff(strategy: str, metrics: dict) -> str:
    if strategy == "balanced":
        return f"保留 {metrics['optional_coverage']} 个可调整地点。"
    if strategy == "low_travel" and metrics.get("travel_data_completeness") == "complete":
        return f"路线数据完整，预计移动 {metrics.get('total_travel_minutes', 0)} 分钟。"
    return f"最少每天留出 {metrics['minimum_daily_slack_minutes']} 分钟弹性时间。"


def _label_for_kind(kind: str) -> str:
    return {"fixed_event": "固定安排", "must_visit": "必去地点", "optional_visit": "想去地点", "arrival_boundary": "到达时间", "departure_boundary": "返程时间"}.get(kind, "旅行信息")
