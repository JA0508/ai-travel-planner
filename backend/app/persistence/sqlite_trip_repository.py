from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Iterator

from app.trips.access import generate_intent_revision_id, generate_operation_id, generate_revision_id, generate_trip_id
from app.trips.intent_contracts import (
    CreateIntentRevisionResult,
    IntentCompileRunDraft,
    SourceLinkedTripIntentEnvelope,
    TripIntentRevisionRecord,
    finalize_intent_envelope_for_revision,
)
from app.trips.candidates import CandidateEvidenceLinkRecord
from app.trips.digests import (
    TRIP_SNAPSHOT_SCHEMA_VERSION,
    canonical_json,
    itinerary_content_digest,
    lineage_digest,
    mutation_proposal_digest,
)
from app.trips.errors import (
    CandidateNotFoundError,
    IdempotencyConflictError,
    ImmutableRevisionViolationError,
    MutationProposalCancelledError,
    MutationProposalExpiredError,
    MutationProposalInvalidatedError,
    MutationProposalNotFoundError,
    PersistenceSchemaMismatchError,
    PersistenceTemporarilyUnavailableError,
    ProposalDigestMismatchError,
    ProposalIntegrityViolationError,
    RevisionNotFoundError,
    StaleBaseRevisionError,
    StaleIntentRevisionError,
    StaleMutationProposalError,
    TripAccessDeniedError,
    TripNotFoundError,
)
from app.trips.models import (
    CandidateDecisionResult,
    CandidateRegistrationResult,
    CreateRevisionResult,
    DraftIntentRevisionRecord,
    ProposalStatus,
    RevisionSourceType,
    TripCandidateDecisionRecord,
    TripCandidateRecord,
    TripAggregate,
    TripLifecycleStatus,
    TripPlanningPhase,
    TripMutationProposalRecord,
    PlannerHandoffRunRecord,
    PrePlanHandoffRunRecord,
    TripRecord,
    TripRevisionRecord,
)
from app.trips.candidates import generate_candidate_decision_id


class SQLiteTripRepository:
    def __init__(self, connection_factory: Callable[[], sqlite3.Connection]) -> None:
        self.connection_factory = connection_factory

    def health_check(self) -> dict[str, Any]:
        try:
            with closing(self.connection_factory()) as connection:
                connection.execute("SELECT 1").fetchone()
                migration = connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY applied_at DESC LIMIT 1"
                ).fetchone()
                return {
                    "mode": "sqlite",
                    "schema_version": migration["version"] if migration else None,
                    "status": "healthy",
                }
        except sqlite3.Error:
            return {"mode": "sqlite", "schema_version": None, "status": "failed"}

    def create_trip_with_initial_revision(
        self,
        *,
        itinerary_snapshot: dict[str, Any],
        capability_hash: str,
        operation_type: str,
        operation_summary: str,
        request_digest: str,
        planner_run_id: str | None,
        planner_version: str | None,
        trace_schema_version: str | None,
        trace_digest: str | None,
    ) -> TripAggregate:
        trip_id = generate_trip_id()
        revision_id = generate_revision_id()
        operation_id = generate_operation_id()
        now = utc_now()
        content_digest = itinerary_content_digest(itinerary_snapshot)
        revision_lineage_digest = lineage_digest(
            parent_lineage_digest=None,
            source_type=RevisionSourceType.PLANNER_GENERATION.value,
            operation_metadata={"operation_type": operation_type},
            content_digest=content_digest,
        )

        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO trips(id, current_revision_id, revision_count, lifecycle_status, capability_hash, created_at, updated_at)
                VALUES (?, NULL, 0, ?, ?, ?, ?)
                """,
                (
                    trip_id,
                    TripLifecycleStatus.ACTIVE.value,
                    capability_hash,
                    now,
                    now,
                ),
            )
            self._insert_revision(
                connection,
                revision_id=revision_id,
                trip_id=trip_id,
                revision_number=1,
                parent_revision_id=None,
                base_revision_id=None,
                source_type=RevisionSourceType.PLANNER_GENERATION.value,
                itinerary_snapshot=itinerary_snapshot,
                content_digest=content_digest,
                parent_lineage_digest=None,
                lineage_digest_value=revision_lineage_digest,
                planner_run_id=planner_run_id,
                planner_version=planner_version,
                trace_schema_version=trace_schema_version,
                trace_digest=trace_digest,
                restored_from_revision_id=None,
                created_at=now,
            )
            self._insert_operation(
                connection,
                operation_id=operation_id,
                trip_id=trip_id,
                revision_id=revision_id,
                base_revision_id=None,
                source_type=RevisionSourceType.PLANNER_GENERATION.value,
                operation_type=operation_type,
                operation_metadata={"operation_type": operation_type},
                request_digest=request_digest,
                idempotency_key_hash=None,
                summary=operation_summary,
                created_at=now,
            )
            connection.execute(
                """
                UPDATE trips
                SET current_revision_id = ?, revision_count = 1, updated_at = ?
                WHERE id = ?
                """,
                (revision_id, now, trip_id),
            )

        return self.get_trip_with_current_revision(trip_id)

    def create_draft_trip(
        self,
        *,
        capability_hash: str,
        direct_user_text: str,
        source_digest: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> tuple[TripRecord, bool]:
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM draft_trip_idempotency_records WHERE idempotency_key_hash = ?",
                (idempotency_key_hash,),
            ).fetchone()
            if existing is not None:
                if existing["request_digest"] != request_digest:
                    raise IdempotencyConflictError()
                row = connection.execute("SELECT * FROM trips WHERE id = ?", (existing["result_trip_id"],)).fetchone()
                if row is None:
                    raise TripNotFoundError(existing["result_trip_id"])
                return row_to_trip(row), True
            trip_id = generate_trip_id()
            now = utc_now()
            connection.execute(
                """
                INSERT INTO trips(id, current_revision_id, revision_count, lifecycle_status, planning_phase, capability_hash, created_at, updated_at)
                VALUES (?, NULL, 0, ?, ?, ?, ?, ?)
                """,
                (trip_id, TripLifecycleStatus.ACTIVE.value, TripPlanningPhase.DRAFT.value, capability_hash, now, now),
            )
            connection.execute(
                """
                INSERT INTO draft_trip_idempotency_records(idempotency_key_hash, request_digest, result_trip_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (idempotency_key_hash, request_digest, trip_id, now),
            )
            connection.execute(
                """
                INSERT INTO draft_trip_source_inputs(trip_id, direct_user_text, source_digest, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (trip_id, direct_user_text, source_digest, now),
            )
            return row_to_trip(connection.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()), False

    def get_draft_source_text(self, *, trip_id: str) -> str:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                "SELECT direct_user_text FROM draft_trip_source_inputs WHERE trip_id = ?",
                (trip_id,),
            ).fetchone()
        if row is None:
            raise TripNotFoundError(trip_id)
        return str(row["direct_user_text"])

    def create_draft_intent_revision(
        self,
        *,
        revision: DraftIntentRevisionRecord,
        request_digest: str,
        idempotency_key_hash: str,
        expected_parent_draft_intent_revision_id: str | None,
    ) -> tuple[DraftIntentRevisionRecord, bool]:
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM draft_intent_idempotency_records WHERE trip_id = ? AND idempotency_key_hash = ?",
                (revision.trip_id, idempotency_key_hash),
            ).fetchone()
            if existing is not None:
                if existing["request_digest"] != request_digest:
                    raise IdempotencyConflictError()
                return self._get_draft_intent_revision_in_connection(connection, revision.trip_id, existing["result_draft_intent_revision_id"]), True
            trip = connection.execute("SELECT * FROM trips WHERE id = ?", (revision.trip_id,)).fetchone()
            if trip is None:
                raise TripNotFoundError(revision.trip_id)
            if trip["planning_phase"] != TripPlanningPhase.DRAFT.value or trip["current_revision_id"] is not None:
                raise StaleBaseRevisionError(trip_id=revision.trip_id, provided_base_revision_id="", current_revision_id=trip["current_revision_id"] or "")
            latest = connection.execute(
                "SELECT * FROM draft_intent_revisions WHERE trip_id = ? ORDER BY revision_number DESC LIMIT 1",
                (revision.trip_id,),
            ).fetchone()
            latest_id = latest["id"] if latest else None
            if latest_id != expected_parent_draft_intent_revision_id:
                raise StaleIntentRevisionError(trip_id=revision.trip_id, provided_intent_revision_id=expected_parent_draft_intent_revision_id or "", current_intent_revision_id=latest_id or "")
            number = 1 if latest is None else int(latest["revision_number"]) + 1
            parent_lineage_digest = None
            if latest is not None:
                parent_envelope = json.loads(latest["envelope_json"])
                parent_lineage_digest = parent_envelope.get("lineage_digest")
            finalized_envelope = finalize_intent_envelope_for_revision(
                SourceLinkedTripIntentEnvelope.model_validate(revision.envelope),
                revision_id=revision.id,
                revision_number=number,
                base_trip_revision_id=None,
                parent_intent_revision_id=expected_parent_draft_intent_revision_id,
                parent_lineage_digest=parent_lineage_digest if isinstance(parent_lineage_digest, str) else None,
                operation="compile_draft_trip_intent_envelope",
                restore_source_revision_id=None,
                created_at=revision.created_at,
            )
            stored = DraftIntentRevisionRecord(
                id=revision.id,
                trip_id=revision.trip_id,
                revision_number=number,
                parent_draft_intent_revision_id=expected_parent_draft_intent_revision_id,
                envelope_schema_version=revision.envelope_schema_version,
                envelope=finalized_envelope.model_dump(mode="json"),
                content_digest=finalized_envelope.content_digest,
                compiler_version=revision.compiler_version,
                source_digest=revision.source_digest,
                validation_report=revision.validation_report,
                created_at=revision.created_at,
            )
            connection.execute(
                """
                INSERT INTO draft_intent_revisions(id, trip_id, revision_number, parent_draft_intent_revision_id,
                  envelope_schema_version, envelope_json, content_digest, compiler_version, source_digest,
                  validation_report_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (stored.id, stored.trip_id, stored.revision_number, stored.parent_draft_intent_revision_id,
                 stored.envelope_schema_version, canonical_json(stored.envelope), stored.content_digest,
                 stored.compiler_version, stored.source_digest, canonical_json(stored.validation_report), stored.created_at),
            )
            connection.execute(
                """
                INSERT INTO draft_intent_idempotency_records(trip_id, idempotency_key_hash, request_digest,
                  result_draft_intent_revision_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (stored.trip_id, idempotency_key_hash, request_digest, stored.id, stored.created_at),
            )
            return stored, False

    def get_draft_intent_revision(self, *, trip_id: str, revision_id: str) -> DraftIntentRevisionRecord:
        with closing(self.connection_factory()) as connection:
            return self._get_draft_intent_revision_in_connection(connection, trip_id, revision_id)

    def get_latest_draft_intent_revision(self, *, trip_id: str) -> DraftIntentRevisionRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute("SELECT * FROM draft_intent_revisions WHERE trip_id = ? ORDER BY revision_number DESC LIMIT 1", (trip_id,)).fetchone()
            return row_to_draft_intent_revision(row) if row is not None else None

    def list_draft_intent_revisions(self, *, trip_id: str) -> list[DraftIntentRevisionRecord]:
        with closing(self.connection_factory()) as connection:
            rows = connection.execute("SELECT * FROM draft_intent_revisions WHERE trip_id = ? ORDER BY revision_number DESC", (trip_id,)).fetchall()
        return [row_to_draft_intent_revision(row) for row in rows]

    def create_preplan_handoff_run(self, *, run: PrePlanHandoffRunRecord) -> PrePlanHandoffRunRecord:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO preplan_handoff_runs(id, trip_id, draft_intent_revision_id, intent_semantic_digest,
                  intent_lineage_digest, input_snapshot_json, input_digest, planner_version, trace_schema_version,
                  trace_snapshot_json, trace_digest, result_snapshot_json, result_content_digest,
                  validation_report_json, status, expires_at, applied_revision_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run.id, run.trip_id, run.draft_intent_revision_id, run.intent_semantic_digest,
                 run.intent_lineage_digest, canonical_json(run.input_snapshot), run.input_digest, run.planner_version,
                 run.trace_schema_version, canonical_json(run.trace_snapshot), run.trace_digest,
                 canonical_json(run.result_snapshot), run.result_content_digest, canonical_json(run.validation_report),
                 run.status, run.expires_at, run.applied_revision_id, run.created_at, run.updated_at),
            )
        return self.get_preplan_handoff_run(trip_id=run.trip_id, run_id=run.id)

    def get_preplan_handoff_run(self, *, trip_id: str, run_id: str) -> PrePlanHandoffRunRecord:
        with closing(self.connection_factory()) as connection:
            row = connection.execute("SELECT * FROM preplan_handoff_runs WHERE id = ? AND trip_id = ?", (run_id, trip_id)).fetchone()
        if row is None:
            raise MutationProposalNotFoundError(run_id)
        return row_to_preplan_handoff_run(row)

    def activate_preplan_handoff(
        self,
        *,
        trip_id: str,
        capability_hash: str,
        run_id: str,
        draft_intent_revision_id: str,
        handoff_digest: str,
        now: str,
        request_digest: str,
        idempotency_key_hash: str,
        operation_metadata: dict[str, Any],
    ) -> CreateRevisionResult:
        with self._transaction() as connection:
            trip_row = connection.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
            if trip_row is None:
                raise TripNotFoundError(trip_id)
            trip = row_to_trip(trip_row)
            if trip.capability_hash != capability_hash:
                raise TripAccessDeniedError()
            replay = connection.execute("SELECT * FROM idempotency_records WHERE trip_id = ? AND idempotency_key_hash = ?", (trip_id, idempotency_key_hash)).fetchone()
            if replay is not None:
                if replay["request_digest"] != request_digest:
                    raise IdempotencyConflictError()
                return CreateRevisionResult(self._get_revision_in_connection(connection, trip_id, replay["result_revision_id"]), True)
            run_row = connection.execute("SELECT * FROM preplan_handoff_runs WHERE id = ? AND trip_id = ?", (run_id, trip_id)).fetchone()
            if run_row is None:
                raise MutationProposalNotFoundError(run_id)
            run = row_to_preplan_handoff_run(run_row)
            if run.draft_intent_revision_id != draft_intent_revision_id or run.trace_digest != handoff_digest:
                raise ProposalDigestMismatchError()
            if run.status == "applied":
                return CreateRevisionResult(self._get_revision_in_connection(connection, trip_id, run.applied_revision_id or ""), True)
            if run.status != "pending" or now >= run.expires_at:
                if run.status == "pending" and now >= run.expires_at:
                    connection.execute("UPDATE preplan_handoff_runs SET status = 'expired', updated_at = ? WHERE id = ?", (now, run_id))
                raise StaleMutationProposalError(trip_id=trip_id, proposal_id=run_id, base_revision_id="", current_revision_id=trip.current_revision_id or "")
            latest = connection.execute("SELECT id FROM draft_intent_revisions WHERE trip_id = ? ORDER BY revision_number DESC LIMIT 1", (trip_id,)).fetchone()
            if latest is None or latest["id"] != draft_intent_revision_id:
                raise StaleIntentRevisionError(trip_id=trip_id, provided_intent_revision_id=draft_intent_revision_id, current_intent_revision_id=latest["id"] if latest else "")
            if trip.planning_phase != TripPlanningPhase.DRAFT.value or trip.current_revision_id is not None:
                raise StaleBaseRevisionError(trip_id=trip_id, provided_base_revision_id="", current_revision_id=trip.current_revision_id or "")
            content_digest = itinerary_content_digest(run.result_snapshot)
            if content_digest != run.result_content_digest:
                raise ProposalIntegrityViolationError()
            revision_id = generate_revision_id()
            lineage = lineage_digest(parent_lineage_digest=None, source_type=RevisionSourceType.PLANNER_INTENT_HANDOFF.value, operation_metadata=operation_metadata, content_digest=content_digest)
            self._insert_revision(connection, revision_id=revision_id, trip_id=trip_id, revision_number=1,
                parent_revision_id=None, base_revision_id=None, source_type=RevisionSourceType.PLANNER_INTENT_HANDOFF.value,
                itinerary_snapshot=run.result_snapshot, content_digest=content_digest, parent_lineage_digest=None,
                lineage_digest_value=lineage, planner_run_id=run.id, planner_version=run.planner_version,
                trace_schema_version=run.trace_schema_version, trace_digest=run.trace_digest, restored_from_revision_id=None, created_at=now)
            self._insert_operation(connection, operation_id=generate_operation_id(), trip_id=trip_id, revision_id=revision_id,
                base_revision_id=None, source_type=RevisionSourceType.PLANNER_INTENT_HANDOFF.value,
                operation_type="apply_preplan_intent_handoff", operation_metadata=operation_metadata,
                request_digest=request_digest, idempotency_key_hash=idempotency_key_hash,
                summary="Created Revision 1 from a confirmed pre-plan intent contract.", created_at=now)
            connection.execute("INSERT INTO idempotency_records(trip_id, idempotency_key_hash, request_digest, result_revision_id, created_at) VALUES (?, ?, ?, ?, ?)", (trip_id, idempotency_key_hash, request_digest, revision_id, now))
            connection.execute("UPDATE preplan_handoff_runs SET status = 'applied', applied_revision_id = ?, updated_at = ? WHERE id = ?", (revision_id, now, run_id))
            connection.execute("UPDATE trips SET current_revision_id = ?, revision_count = 1, planning_phase = ?, updated_at = ? WHERE id = ?", (revision_id, TripPlanningPhase.PLANNED.value, now, trip_id))
            return CreateRevisionResult(self._get_revision_in_connection(connection, trip_id, revision_id))

    def get_trip(self, trip_id: str) -> TripRecord:
        with closing(self.connection_factory()) as connection:
            row = connection.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if row is None:
            raise TripNotFoundError(trip_id)
        return row_to_trip(row)

    def get_trip_for_access(self, trip_id: str, capability_hash: str) -> TripRecord:
        trip = self.get_trip(trip_id)
        if trip.capability_hash != capability_hash:
            raise TripAccessDeniedError()
        return trip

    def get_trip_with_current_revision(self, trip_id: str) -> TripAggregate:
        trip = self.get_trip(trip_id)
        return TripAggregate(trip=trip, current_revision=self.get_revision(trip.id, trip.current_revision_id))

    def get_current_revision(self, trip_id: str) -> TripRevisionRecord:
        trip = self.get_trip(trip_id)
        return self.get_revision(trip_id, trip.current_revision_id)

    def get_revision(self, trip_id: str, revision_id: str) -> TripRevisionRecord:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                "SELECT * FROM trip_revisions WHERE id = ? AND trip_id = ?",
                (revision_id, trip_id),
            ).fetchone()
        if row is None:
            raise RevisionNotFoundError(revision_id)
        return row_to_revision(row)

    def list_revisions(self, trip_id: str) -> list[TripRevisionRecord]:
        with closing(self.connection_factory()) as connection:
            rows = connection.execute(
                "SELECT * FROM trip_revisions WHERE trip_id = ? ORDER BY revision_number DESC",
                (trip_id,),
            ).fetchall()
        return [row_to_revision(row) for row in rows]

    def create_intent_revision(
        self,
        *,
        revision: TripIntentRevisionRecord,
        compile_run: IntentCompileRunDraft | None = None,
        operation: str = "compile_trip_intent_envelope",
        restore_source_revision_id: str | None = None,
        request_digest: str,
        idempotency_key_hash: str,
        expected_parent_intent_revision_id: str | None = None,
        require_latest_parent: bool = False,
        expected_base_revision_id: str | None = None,
    ) -> CreateIntentRevisionResult:
        with self._transaction() as connection:
            idempotency_row = connection.execute(
                """
                SELECT * FROM trip_intent_idempotency_records
                WHERE trip_id = ? AND idempotency_key_hash = ?
                """,
                (revision.trip_id, idempotency_key_hash),
            ).fetchone()
            if idempotency_row is not None:
                if idempotency_row["request_digest"] != request_digest:
                    raise IdempotencyConflictError()
                stored_revision = self._get_intent_revision_in_connection(
                    connection,
                    revision.trip_id,
                    idempotency_row["result_intent_revision_id"],
                )
                return CreateIntentRevisionResult(
                    revision=stored_revision,
                    idempotent_replay=True,
                )

            trip_row = connection.execute(
                "SELECT current_revision_id FROM trips WHERE id = ?",
                (revision.trip_id,),
            ).fetchone()
            if trip_row is None:
                raise TripNotFoundError(revision.trip_id)
            if expected_base_revision_id is not None and trip_row["current_revision_id"] != expected_base_revision_id:
                raise StaleBaseRevisionError(
                    trip_id=revision.trip_id,
                    provided_base_revision_id=expected_base_revision_id,
                    current_revision_id=trip_row["current_revision_id"],
                )
            base_row = connection.execute(
                "SELECT 1 FROM trip_revisions WHERE id = ? AND trip_id = ?",
                (revision.base_trip_revision_id, revision.trip_id),
            ).fetchone()
            if base_row is None:
                raise RevisionNotFoundError(revision.base_trip_revision_id)

            latest_row = connection.execute(
                """
                SELECT * FROM trip_intent_revisions
                WHERE trip_id = ?
                ORDER BY revision_number DESC, created_at DESC
                LIMIT 1
                """,
                (revision.trip_id,),
            ).fetchone()
            latest = row_to_intent_revision(latest_row) if latest_row is not None else None
            if require_latest_parent:
                latest_id = latest.id if latest is not None else None
                if latest_id != expected_parent_intent_revision_id:
                    raise StaleIntentRevisionError(
                        trip_id=revision.trip_id,
                        provided_intent_revision_id=expected_parent_intent_revision_id or "",
                        current_intent_revision_id=latest_id or "",
                    )

            final_revision_number = 1 if latest is None else latest.revision_number + 1
            final_revision_id = generate_intent_revision_id()
            parent_lineage_digest = None
            if latest is not None:
                parent_lineage_digest = latest.envelope.get("lineage_digest") if isinstance(latest.envelope, dict) else None
            finalized_envelope = finalize_intent_envelope_for_revision(
                SourceLinkedTripIntentEnvelope.model_validate(revision.envelope),
                revision_id=final_revision_id,
                revision_number=final_revision_number,
                base_trip_revision_id=revision.base_trip_revision_id,
                parent_intent_revision_id=expected_parent_intent_revision_id,
                parent_lineage_digest=parent_lineage_digest if isinstance(parent_lineage_digest, str) else None,
                operation=operation,
                restore_source_revision_id=restore_source_revision_id,
                created_at=revision.created_at,
            )
            final_revision = TripIntentRevisionRecord(
                id=final_revision_id,
                trip_id=revision.trip_id,
                revision_number=final_revision_number,
                parent_intent_revision_id=expected_parent_intent_revision_id,
                base_trip_revision_id=revision.base_trip_revision_id,
                envelope_schema_version=revision.envelope_schema_version,
                envelope=finalized_envelope.model_dump(mode="json"),
                content_digest=finalized_envelope.content_digest,
                compiler_version=revision.compiler_version,
                source_digest=revision.source_digest,
                validation_report=finalized_envelope.validation_report,
                created_at=revision.created_at,
            )
            self._insert_intent_revision(connection, final_revision)
            if compile_run is not None:
                self._insert_intent_compile_run(connection, compile_run, final_revision)
            connection.execute(
                """
                INSERT INTO trip_intent_idempotency_records(
                  trip_id, idempotency_key_hash, request_digest,
                  result_intent_revision_id, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    revision.trip_id,
                    idempotency_key_hash,
                    request_digest,
                    final_revision.id,
                    revision.created_at,
                ),
            )
            return CreateIntentRevisionResult(revision=final_revision)

    def get_intent_revision_by_idempotency(
        self,
        *,
        trip_id: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> CreateIntentRevisionResult | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT * FROM trip_intent_idempotency_records
                WHERE trip_id = ? AND idempotency_key_hash = ?
                """,
                (trip_id, idempotency_key_hash),
            ).fetchone()
            if row is None:
                return None
            if row["request_digest"] != request_digest:
                raise IdempotencyConflictError()
            revision = self._get_intent_revision_in_connection(
                connection,
                trip_id,
                row["result_intent_revision_id"],
            )
        return CreateIntentRevisionResult(revision=revision, idempotent_replay=True)

    def list_intent_revisions(self, *, trip_id: str) -> list[TripIntentRevisionRecord]:
        with closing(self.connection_factory()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM trip_intent_revisions
                WHERE trip_id = ?
                ORDER BY revision_number DESC, created_at DESC
                """,
                (trip_id,),
            ).fetchall()
        return [row_to_intent_revision(row) for row in rows]

    def get_latest_intent_revision(self, *, trip_id: str) -> TripIntentRevisionRecord | None:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                """
                SELECT * FROM trip_intent_revisions
                WHERE trip_id = ?
                ORDER BY revision_number DESC, created_at DESC
                LIMIT 1
                """,
                (trip_id,),
            ).fetchone()
        return row_to_intent_revision(row) if row is not None else None

    def get_intent_revision(self, *, trip_id: str, revision_id: str) -> TripIntentRevisionRecord:
        with closing(self.connection_factory()) as connection:
            row = connection.execute(
                "SELECT * FROM trip_intent_revisions WHERE id = ? AND trip_id = ?",
                (revision_id, trip_id),
            ).fetchone()
        if row is None:
            raise RevisionNotFoundError(revision_id)
        return row_to_intent_revision(row)

    def create_candidate(
        self,
        *,
        candidate: TripCandidateRecord,
        decision: TripCandidateDecisionRecord,
        request_digest: str,
        idempotency_key_hash: str,
        evidence_links: list[CandidateEvidenceLinkRecord] | None = None,
    ) -> CandidateRegistrationResult:
        with self._transaction() as connection:
            existing_idempotency = connection.execute(
                """
                SELECT * FROM candidate_idempotency_records
                WHERE trip_id = ? AND idempotency_key_hash = ?
                """,
                (candidate.trip_id, idempotency_key_hash),
            ).fetchone()
            if existing_idempotency is not None:
                if existing_idempotency["request_digest"] != request_digest:
                    raise IdempotencyConflictError()
                stored_candidate = self._get_candidate_in_connection(
                    connection,
                    candidate.trip_id,
                    existing_idempotency["result_candidate_id"],
                )
                stored_decision = (
                    self._get_candidate_decision_in_connection(
                        connection,
                        candidate.trip_id,
                        existing_idempotency["result_decision_id"],
                    )
                    if existing_idempotency["result_decision_id"]
                    else None
                )
                return CandidateRegistrationResult(
                    candidate=stored_candidate,
                    decision=stored_decision,
                    idempotent_replay=True,
                )

            duplicate = connection.execute(
                """
                SELECT * FROM trip_candidates
                WHERE trip_id = ? AND content_digest = ?
                """,
                (candidate.trip_id, candidate.content_digest),
            ).fetchone()
            if duplicate is not None:
                stored_candidate = row_to_candidate(duplicate)
                for evidence_link in evidence_links or []:
                    self._insert_candidate_evidence_link(
                        connection,
                        replace(evidence_link, trip_candidate_id=stored_candidate.id),
                    )
                connection.execute(
                    """
                    INSERT INTO candidate_idempotency_records(
                      trip_id, idempotency_key_hash, request_digest,
                      result_candidate_id, result_decision_id, created_at
                    )
                    VALUES (?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        candidate.trip_id,
                        idempotency_key_hash,
                        request_digest,
                        stored_candidate.id,
                        utc_now(),
                    ),
                )
                return CandidateRegistrationResult(candidate=stored_candidate, deduplicated=True)

            self._insert_candidate(connection, candidate)
            for evidence_link in evidence_links or []:
                self._insert_candidate_evidence_link(connection, evidence_link)
            self._insert_candidate_decision(connection, decision)
            connection.execute(
                """
                INSERT INTO candidate_idempotency_records(
                  trip_id, idempotency_key_hash, request_digest,
                  result_candidate_id, result_decision_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.trip_id,
                    idempotency_key_hash,
                    request_digest,
                    candidate.id,
                    decision.id,
                    decision.created_at,
                ),
            )
            return CandidateRegistrationResult(candidate=candidate, decision=decision)

    def get_candidate(self, *, trip_id: str, candidate_id: str) -> TripCandidateRecord:
        with closing(self.connection_factory()) as connection:
            return self._get_candidate_in_connection(connection, trip_id, candidate_id)

    def list_candidates(self, *, trip_id: str) -> list[TripCandidateRecord]:
        with closing(self.connection_factory()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM trip_candidates
                WHERE trip_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (trip_id,),
            ).fetchall()
        return [row_to_candidate(row) for row in rows]

    def list_candidate_evidence_links(
        self,
        *,
        trip_id: str,
        candidate_id: str,
    ) -> list[CandidateEvidenceLinkRecord]:
        with closing(self.connection_factory()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM trip_candidate_evidence_links
                WHERE trip_id = ? AND trip_candidate_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (trip_id, candidate_id),
            ).fetchall()
        return [row_to_candidate_evidence_link(row) for row in rows]

    def list_candidate_decisions(
        self,
        *,
        trip_id: str,
        candidate_id: str | None = None,
    ) -> list[TripCandidateDecisionRecord]:
        with closing(self.connection_factory()) as connection:
            if candidate_id is None:
                rows = connection.execute(
                    """
                    SELECT * FROM trip_candidate_decisions
                    WHERE trip_id = ?
                    ORDER BY created_at ASC, id ASC
                    """,
                    (trip_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM trip_candidate_decisions
                    WHERE trip_id = ? AND candidate_id = ?
                    ORDER BY created_at ASC, id ASC
                    """,
                    (trip_id, candidate_id),
                ).fetchall()
        return [row_to_candidate_decision(row) for row in rows]

    def create_candidate_decision(
        self,
        *,
        decision: TripCandidateDecisionRecord,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> CandidateDecisionResult:
        with self._transaction() as connection:
            idempotency_row = connection.execute(
                """
                SELECT * FROM candidate_idempotency_records
                WHERE trip_id = ? AND idempotency_key_hash = ?
                """,
                (decision.trip_id, idempotency_key_hash),
            ).fetchone()
            if idempotency_row is not None:
                if idempotency_row["request_digest"] != request_digest:
                    raise IdempotencyConflictError()
                stored_decision = self._get_candidate_decision_in_connection(
                    connection,
                    decision.trip_id,
                    idempotency_row["result_decision_id"],
                )
                return CandidateDecisionResult(
                    candidate=self._get_candidate_in_connection(
                        connection,
                        decision.trip_id,
                        stored_decision.candidate_id,
                    ),
                    decision=stored_decision,
                    idempotent_replay=True,
                )
            candidate = self._get_candidate_in_connection(
                connection,
                decision.trip_id,
                decision.candidate_id,
            )
            self._insert_candidate_decision(connection, decision)
            connection.execute(
                """
                INSERT INTO candidate_idempotency_records(
                  trip_id, idempotency_key_hash, request_digest,
                  result_candidate_id, result_decision_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.trip_id,
                    idempotency_key_hash,
                    request_digest,
                    candidate.id,
                    decision.id,
                    decision.created_at,
                ),
            )
            return CandidateDecisionResult(candidate=candidate, decision=decision)

    def get_idempotent_revision(
        self,
        *,
        trip_id: str,
        capability_hash: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> CreateRevisionResult | None:
        trip = self.get_trip_for_access(trip_id, capability_hash)
        with closing(self.connection_factory()) as connection:
            idempotency_row = connection.execute(
                """
                SELECT * FROM idempotency_records
                WHERE trip_id = ? AND idempotency_key_hash = ?
                """,
                (trip.id, idempotency_key_hash),
            ).fetchone()
            if idempotency_row is None:
                return None
            if idempotency_row["request_digest"] != request_digest:
                raise IdempotencyConflictError()
            return CreateRevisionResult(
                revision=self._get_revision_in_connection(
                    connection,
                    trip.id,
                    idempotency_row["result_revision_id"],
                ),
                idempotent_replay=True,
            )

    def create_mutation_proposal(
        self,
        *,
        proposal: TripMutationProposalRecord,
    ) -> TripMutationProposalRecord:
        with self._transaction() as connection:
            self._insert_proposal(connection, proposal)
        return self.get_mutation_proposal(trip_id=proposal.trip_id, proposal_id=proposal.id)

    def create_planner_handoff_preview(
        self,
        *,
        run: PlannerHandoffRunRecord,
        proposal: TripMutationProposalRecord,
    ) -> tuple[PlannerHandoffRunRecord, TripMutationProposalRecord]:
        if proposal.planner_run_id != run.id or proposal.trip_id != run.trip_id:
            raise ProposalIntegrityViolationError()
        with self._transaction() as connection:
            self._insert_proposal(connection, proposal)
            self._insert_planner_handoff_run(connection, run)
            stored_run = self._get_planner_handoff_run_in_connection(connection, run.trip_id, run.id)
            stored_proposal = self._get_proposal_in_connection(connection, proposal.trip_id, proposal.id)
        return stored_run, stored_proposal

    def get_planner_handoff_run(
        self,
        *,
        trip_id: str,
        run_id: str,
    ) -> PlannerHandoffRunRecord:
        with closing(self.connection_factory()) as connection:
            return self._get_planner_handoff_run_in_connection(connection, trip_id, run_id)

    def _insert_proposal(self, connection: sqlite3.Connection, proposal: TripMutationProposalRecord) -> None:
        connection.execute(
                """
                INSERT INTO trip_mutation_proposals(
                  id, trip_id, base_revision_id, proposal_schema_version, source_type,
                  operation_type, request_digest, instruction_digest,
                  preview_snapshot_schema_version, preview_snapshot_json,
                  preview_content_digest, proposal_digest, planner_run_id, planner_version,
                  trace_schema_version, trace_digest, validation_report_json,
                  execution_kind, command_schema_version, mutation_engine_version,
                  mutation_kind, commands_json, command_digest, impact_summary_json,
                  invalidated_surfaces_json, status, expires_at, applied_revision_id,
                  created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.id,
                    proposal.trip_id,
                    proposal.base_revision_id,
                    proposal.proposal_schema_version,
                    proposal.source_type,
                    proposal.operation_type,
                    proposal.request_digest,
                    proposal.instruction_digest,
                    proposal.preview_snapshot_schema_version,
                    canonical_json(proposal.preview_snapshot),
                    proposal.preview_content_digest,
                    proposal.proposal_digest,
                    proposal.planner_run_id,
                    proposal.planner_version,
                    proposal.trace_schema_version,
                    proposal.trace_digest,
                    canonical_json(proposal.validation_report),
                    proposal.execution_kind,
                    proposal.command_schema_version,
                    proposal.mutation_engine_version,
                    proposal.mutation_kind,
                    canonical_json(proposal.commands) if proposal.commands is not None else None,
                    proposal.command_digest,
                    canonical_json(proposal.impact_summary) if proposal.impact_summary is not None else None,
                    canonical_json(proposal.invalidated_surfaces)
                    if proposal.invalidated_surfaces is not None
                    else None,
                    proposal.status,
                    proposal.expires_at,
                    proposal.applied_revision_id,
                    proposal.created_at,
                    proposal.updated_at,
                ),
            )

    def get_mutation_proposal(
        self,
        *,
        trip_id: str,
        proposal_id: str,
    ) -> TripMutationProposalRecord:
        with closing(self.connection_factory()) as connection:
            proposal = self._get_proposal_in_connection(connection, trip_id, proposal_id)
        return proposal

    def apply_mutation_proposal(
        self,
        *,
        trip_id: str,
        capability_hash: str,
        proposal_id: str,
        base_revision_id: str,
        proposal_digest: str,
        now: str,
        operation_summary: str,
        operation_metadata: dict[str, Any],
        request_digest: str,
        idempotency_key_hash: str,
        expected_intent_revision_id: str | None = None,
    ) -> CreateRevisionResult:
        revision_id = generate_revision_id()
        operation_id = generate_operation_id()

        with self._transaction() as connection:
            trip_row = connection.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
            if trip_row is None:
                raise TripNotFoundError(trip_id)
            trip = row_to_trip(trip_row)
            if trip.capability_hash != capability_hash:
                raise TripAccessDeniedError()

            idempotency_row = connection.execute(
                """
                SELECT * FROM idempotency_records
                WHERE trip_id = ? AND idempotency_key_hash = ?
                """,
                (trip_id, idempotency_key_hash),
            ).fetchone()
            if idempotency_row is not None:
                if idempotency_row["request_digest"] != request_digest:
                    raise IdempotencyConflictError()
                return CreateRevisionResult(
                    revision=self._get_revision_in_connection(
                        connection,
                        trip_id,
                        idempotency_row["result_revision_id"],
                    ),
                    idempotent_replay=True,
                )

            proposal = self._get_proposal_in_connection(connection, trip_id, proposal_id)
            if proposal.applied_revision_id is not None:
                return CreateRevisionResult(
                    revision=self._get_revision_in_connection(
                        connection,
                        trip_id,
                        proposal.applied_revision_id,
                    ),
                    idempotent_replay=True,
                )

            if proposal.status == ProposalStatus.EXPIRED.value:
                raise MutationProposalExpiredError(proposal_id)
            if proposal.status == ProposalStatus.CANCELLED.value:
                raise MutationProposalCancelledError(proposal_id)
            if proposal.status == ProposalStatus.INVALIDATED.value:
                raise MutationProposalInvalidatedError(proposal_id)
            if proposal.status != ProposalStatus.PENDING.value:
                raise ProposalIntegrityViolationError()

            if now >= proposal.expires_at:
                connection.execute(
                    """
                    UPDATE trip_mutation_proposals
                    SET status = 'expired', updated_at = ?
                    WHERE id = ? AND trip_id = ?
                    """,
                    (now, proposal_id, trip_id),
                )
                raise MutationProposalExpiredError(proposal_id)

            if proposal.base_revision_id != base_revision_id:
                raise ProposalDigestMismatchError()
            if proposal.proposal_digest != proposal_digest:
                raise ProposalDigestMismatchError()
            self._assert_proposal_integrity(proposal)

            current_revision = self._get_revision_in_connection(
                connection,
                trip_id,
                trip.current_revision_id,
            )
            if current_revision.id != proposal.base_revision_id:
                raise StaleMutationProposalError(
                    trip_id=trip_id,
                    proposal_id=proposal_id,
                    base_revision_id=proposal.base_revision_id,
                    current_revision_id=current_revision.id,
                )

            handoff_run: PlannerHandoffRunRecord | None = None
            if expected_intent_revision_id is not None:
                if proposal.planner_run_id is None:
                    raise ProposalIntegrityViolationError()
                handoff_run = self._get_planner_handoff_run_in_connection(
                    connection,
                    trip_id,
                    proposal.planner_run_id,
                )
                if (
                    handoff_run.status != "pending"
                    or handoff_run.intent_revision_id != expected_intent_revision_id
                    or handoff_run.base_trip_revision_id != proposal.base_revision_id
                    or handoff_run.proposal_id != proposal.id
                    or handoff_run.result_content_digest != proposal.preview_content_digest
                    or handoff_run.trace_digest != proposal.trace_digest
                ):
                    raise ProposalIntegrityViolationError()
                latest_intent_row = connection.execute(
                    """
                    SELECT id FROM trip_intent_revisions
                    WHERE trip_id = ? ORDER BY revision_number DESC, created_at DESC LIMIT 1
                    """,
                    (trip_id,),
                ).fetchone()
                current_intent_revision_id = latest_intent_row["id"] if latest_intent_row is not None else ""
                if current_intent_revision_id != expected_intent_revision_id:
                    raise StaleIntentRevisionError(
                        trip_id=trip_id,
                        provided_intent_revision_id=expected_intent_revision_id,
                        current_intent_revision_id=current_intent_revision_id,
                    )

            content_digest = itinerary_content_digest(proposal.preview_snapshot)
            if content_digest != proposal.preview_content_digest:
                raise ProposalIntegrityViolationError()
            new_lineage_digest = lineage_digest(
                parent_lineage_digest=current_revision.lineage_digest,
                source_type=proposal.source_type,
                operation_metadata=operation_metadata,
                content_digest=content_digest,
            )
            revision_number = trip.revision_count + 1
            self._insert_revision(
                connection,
                revision_id=revision_id,
                trip_id=trip_id,
                revision_number=revision_number,
                parent_revision_id=current_revision.id,
                base_revision_id=proposal.base_revision_id,
                source_type=proposal.source_type,
                itinerary_snapshot=proposal.preview_snapshot,
                content_digest=content_digest,
                parent_lineage_digest=current_revision.lineage_digest,
                lineage_digest_value=new_lineage_digest,
                planner_run_id=proposal.planner_run_id,
                planner_version=proposal.planner_version,
                trace_schema_version=proposal.trace_schema_version,
                trace_digest=proposal.trace_digest,
                restored_from_revision_id=None,
                created_at=now,
            )
            self._insert_operation(
                connection,
                operation_id=operation_id,
                trip_id=trip_id,
                revision_id=revision_id,
                base_revision_id=proposal.base_revision_id,
                source_type=proposal.source_type,
                operation_type=proposal.operation_type,
                operation_metadata=operation_metadata,
                request_digest=request_digest,
                idempotency_key_hash=idempotency_key_hash,
                summary=operation_summary,
                created_at=now,
            )
            connection.execute(
                """
                INSERT INTO idempotency_records(trip_id, idempotency_key_hash, request_digest, result_revision_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (trip_id, idempotency_key_hash, request_digest, revision_id, now),
            )
            connection.execute(
                """
                UPDATE trip_mutation_proposals
                SET status = 'applied', applied_revision_id = ?, updated_at = ?
                WHERE id = ? AND trip_id = ?
                """,
                (revision_id, now, proposal_id, trip_id),
            )
            if handoff_run is not None:
                connection.execute(
                    """
                    UPDATE planner_handoff_runs
                    SET status = 'applied', applied_revision_id = ?, updated_at = ?
                    WHERE id = ? AND trip_id = ?
                    """,
                    (revision_id, now, handoff_run.id, trip_id),
                )
            candidate_admission = operation_metadata.get("candidate_admission")
            if isinstance(candidate_admission, dict):
                candidate_id = str(candidate_admission.get("candidate_id") or "")
                if candidate_id:
                    self._get_candidate_in_connection(connection, trip_id, candidate_id)
                    self._insert_candidate_decision(
                        connection,
                        TripCandidateDecisionRecord(
                            id=generate_candidate_decision_id(),
                            trip_id=trip_id,
                            candidate_id=candidate_id,
                            decision_type="scheduled",
                            reason_code="SCHEDULED_IN_REVISION",
                            base_revision_id=base_revision_id,
                            related_revision_id=revision_id,
                            source="mutation_apply",
                            created_at=now,
                        ),
                    )
            connection.execute(
                """
                UPDATE trips
                SET current_revision_id = ?, revision_count = ?, updated_at = ?
                WHERE id = ?
                """,
                (revision_id, revision_number, now, trip_id),
            )
            return CreateRevisionResult(
                revision=self._get_revision_in_connection(connection, trip_id, revision_id)
            )

    def create_revision(
        self,
        *,
        trip_id: str,
        capability_hash: str,
        base_revision_id: str,
        itinerary_snapshot: dict[str, Any],
        source_type: str,
        operation_type: str,
        operation_summary: str,
        operation_metadata: dict[str, Any],
        request_digest: str,
        idempotency_key_hash: str,
        planner_run_id: str | None = None,
        planner_version: str | None = None,
        trace_schema_version: str | None = None,
        trace_digest: str | None = None,
        restored_from_revision_id: str | None = None,
    ) -> CreateRevisionResult:
        now = utc_now()
        revision_id = generate_revision_id()
        operation_id = generate_operation_id()
        content_digest = itinerary_content_digest(itinerary_snapshot)

        with self._transaction() as connection:
            trip_row = connection.execute(
                "SELECT * FROM trips WHERE id = ?",
                (trip_id,),
            ).fetchone()
            if trip_row is None:
                raise TripNotFoundError(trip_id)
            trip = row_to_trip(trip_row)
            if trip.capability_hash != capability_hash:
                raise TripAccessDeniedError()

            idempotency_row = connection.execute(
                """
                SELECT * FROM idempotency_records
                WHERE trip_id = ? AND idempotency_key_hash = ?
                """,
                (trip_id, idempotency_key_hash),
            ).fetchone()
            if idempotency_row is not None:
                if idempotency_row["request_digest"] != request_digest:
                    raise IdempotencyConflictError()
                return CreateRevisionResult(
                    revision=self._get_revision_in_connection(
                        connection,
                        trip_id,
                        idempotency_row["result_revision_id"],
                    ),
                    idempotent_replay=True,
                )

            current_revision = self._get_revision_in_connection(
                connection,
                trip_id,
                trip.current_revision_id,
            )
            if current_revision.id != base_revision_id:
                raise StaleBaseRevisionError(
                    trip_id=trip_id,
                    provided_base_revision_id=base_revision_id,
                    current_revision_id=current_revision.id,
                )

            new_lineage_digest = lineage_digest(
                parent_lineage_digest=current_revision.lineage_digest,
                source_type=source_type,
                operation_metadata=operation_metadata,
                content_digest=content_digest,
            )
            revision_number = trip.revision_count + 1
            self._insert_revision(
                connection,
                revision_id=revision_id,
                trip_id=trip_id,
                revision_number=revision_number,
                parent_revision_id=current_revision.id,
                base_revision_id=base_revision_id,
                source_type=source_type,
                itinerary_snapshot=itinerary_snapshot,
                content_digest=content_digest,
                parent_lineage_digest=current_revision.lineage_digest,
                lineage_digest_value=new_lineage_digest,
                planner_run_id=planner_run_id,
                planner_version=planner_version,
                trace_schema_version=trace_schema_version,
                trace_digest=trace_digest,
                restored_from_revision_id=restored_from_revision_id,
                created_at=now,
            )
            self._insert_operation(
                connection,
                operation_id=operation_id,
                trip_id=trip_id,
                revision_id=revision_id,
                base_revision_id=base_revision_id,
                source_type=source_type,
                operation_type=operation_type,
                operation_metadata=operation_metadata,
                request_digest=request_digest,
                idempotency_key_hash=idempotency_key_hash,
                summary=operation_summary,
                created_at=now,
            )
            connection.execute(
                """
                INSERT INTO idempotency_records(trip_id, idempotency_key_hash, request_digest, result_revision_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (trip_id, idempotency_key_hash, request_digest, revision_id, now),
            )
            connection.execute(
                """
                UPDATE trips
                SET current_revision_id = ?, revision_count = ?, updated_at = ?
                WHERE id = ?
                """,
                (revision_id, revision_number, now, trip_id),
            )

            revision = self._get_revision_in_connection(connection, trip_id, revision_id)
            return CreateRevisionResult(revision=revision)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connection_factory()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            connection.execute("ROLLBACK")
            if (
                "immutable_revision_violation" in str(exc)
                or "immutable_proposal_violation" in str(exc)
                or "immutable_candidate_violation" in str(exc)
                or "immutable_intent_revision_violation" in str(exc)
            ):
                raise ImmutableRevisionViolationError() from exc
            if "schema_migrations" in str(exc):
                raise PersistenceSchemaMismatchError() from exc
            raise
        except sqlite3.OperationalError as exc:
            connection.execute("ROLLBACK")
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise PersistenceTemporarilyUnavailableError() from exc
            if (
                "immutable_revision_violation" in str(exc)
                or "immutable_proposal_violation" in str(exc)
                or "immutable_candidate_violation" in str(exc)
                or "immutable_intent_revision_violation" in str(exc)
            ):
                raise ImmutableRevisionViolationError() from exc
            raise
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _insert_revision(self, connection: sqlite3.Connection, **values: Any) -> None:
        connection.execute(
            """
            INSERT INTO trip_revisions(
              id, trip_id, revision_number, parent_revision_id, base_revision_id,
              source_type, snapshot_schema_version, itinerary_snapshot, content_digest,
              parent_lineage_digest, lineage_digest, planner_run_id, planner_version,
              trace_schema_version, trace_digest, restored_from_revision_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["revision_id"],
                values["trip_id"],
                values["revision_number"],
                values["parent_revision_id"],
                values["base_revision_id"],
                values["source_type"],
                TRIP_SNAPSHOT_SCHEMA_VERSION,
                canonical_json(values["itinerary_snapshot"]),
                values["content_digest"],
                values["parent_lineage_digest"],
                values["lineage_digest_value"],
                values["planner_run_id"],
                values["planner_version"],
                values["trace_schema_version"],
                values["trace_digest"],
                values["restored_from_revision_id"],
                values["created_at"],
            ),
        )

    def _get_draft_intent_revision_in_connection(
        self,
        connection: sqlite3.Connection,
        trip_id: str,
        revision_id: str,
    ) -> DraftIntentRevisionRecord:
        row = connection.execute(
            "SELECT * FROM draft_intent_revisions WHERE id = ? AND trip_id = ?",
            (revision_id, trip_id),
        ).fetchone()
        if row is None:
            raise RevisionNotFoundError(revision_id)
        return row_to_draft_intent_revision(row)

    def _insert_operation(self, connection: sqlite3.Connection, **values: Any) -> None:
        connection.execute(
            """
            INSERT INTO revision_operations(
              id, trip_id, revision_id, base_revision_id, source_type, operation_type,
              operation_metadata_json, request_digest, idempotency_key_hash, actor_type, summary, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["operation_id"],
                values["trip_id"],
                values["revision_id"],
                values["base_revision_id"],
                values["source_type"],
                values["operation_type"],
                canonical_json(values["operation_metadata"]),
                values["request_digest"],
                values["idempotency_key_hash"],
                "anonymous",
                values["summary"],
                values["created_at"],
            ),
        )

    def _insert_intent_revision(
        self,
        connection: sqlite3.Connection,
        revision: TripIntentRevisionRecord,
    ) -> None:
        connection.execute(
            """
            INSERT INTO trip_intent_revisions(
              id, trip_id, revision_number, parent_intent_revision_id,
              base_trip_revision_id, envelope_schema_version, envelope_json,
              content_digest, compiler_version, source_digest,
              validation_report_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision.id,
                revision.trip_id,
                revision.revision_number,
                revision.parent_intent_revision_id,
                revision.base_trip_revision_id,
                revision.envelope_schema_version,
                canonical_json(revision.envelope),
                revision.content_digest,
                revision.compiler_version,
                revision.source_digest,
                canonical_json(revision.validation_report),
                revision.created_at,
            ),
        )

    def _insert_intent_compile_run(
        self,
        connection: sqlite3.Connection,
        draft: IntentCompileRunDraft,
        revision: TripIntentRevisionRecord,
    ) -> None:
        envelope = SourceLinkedTripIntentEnvelope.model_validate(revision.envelope)
        connection.execute(
            """
            INSERT INTO intent_compile_runs(
              id, trip_id, operation, base_trip_revision_id, base_intent_revision_id,
              result_intent_revision_id, parser_status, parser_name, parser_version,
              model_name, compiler_version, precedence_version, readiness_policy_version,
              date_policy_version, input_digest, proposal_digest, semantic_digest,
              lineage_digest, status, warning_codes_json, error_code, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft.id,
                draft.trip_id,
                draft.operation,
                draft.base_trip_revision_id,
                draft.base_intent_revision_id,
                revision.id,
                draft.parser_status,
                draft.parser_name,
                draft.parser_version,
                draft.model_name,
                draft.compiler_version,
                draft.precedence_version,
                draft.readiness_policy_version,
                draft.date_policy_version,
                draft.input_digest,
                draft.proposal_digest,
                envelope.semantic_digest or "",
                envelope.lineage_digest or "",
                draft.status,
                canonical_json(draft.warning_codes),
                draft.error_code,
                draft.created_at,
            ),
        )

    def _insert_planner_handoff_run(
        self,
        connection: sqlite3.Connection,
        run: PlannerHandoffRunRecord,
    ) -> None:
        connection.execute(
            """
            INSERT INTO planner_handoff_runs(
              id, trip_id, base_trip_revision_id, intent_revision_id,
              intent_semantic_digest, intent_lineage_digest,
              input_schema_version, input_snapshot_json, input_digest,
              planner_version, trace_schema_version, trace_snapshot_json, trace_digest,
              result_snapshot_schema_version, result_snapshot_json, result_content_digest,
              validation_report_json, proposal_id, status, applied_revision_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.id, run.trip_id, run.base_trip_revision_id, run.intent_revision_id,
                run.intent_semantic_digest, run.intent_lineage_digest,
                run.input_schema_version, canonical_json(run.input_snapshot), run.input_digest,
                run.planner_version, run.trace_schema_version, canonical_json(run.trace_snapshot), run.trace_digest,
                run.result_snapshot_schema_version, canonical_json(run.result_snapshot), run.result_content_digest,
                canonical_json(run.validation_report), run.proposal_id, run.status,
                run.applied_revision_id, run.created_at, run.updated_at,
            ),
        )

    def _insert_candidate(
        self,
        connection: sqlite3.Connection,
        candidate: TripCandidateRecord,
    ) -> None:
        connection.execute(
            """
            INSERT INTO trip_candidates(
              id, trip_id, candidate_type, display_name, normalized_name,
              canonical_place_id, provider_place_id, category, coordinates_json,
              address_summary, estimated_duration_minutes, preferred_time_block,
              explicit_day_reference, source_kind, source_ref, evidence_refs_json,
              location_state, route_state, duration_state, confidence,
              content_digest, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.id,
                candidate.trip_id,
                candidate.candidate_type,
                candidate.display_name,
                candidate.normalized_name,
                candidate.canonical_place_id,
                candidate.provider_place_id,
                candidate.category,
                canonical_json(candidate.coordinates) if candidate.coordinates is not None else None,
                candidate.address_summary,
                candidate.estimated_duration_minutes,
                candidate.preferred_time_block,
                candidate.explicit_day_reference,
                candidate.source_kind,
                candidate.source_ref,
                canonical_json(candidate.evidence_refs),
                candidate.location_state,
                candidate.route_state,
                candidate.duration_state,
                candidate.confidence,
                candidate.content_digest,
                candidate.created_at,
            ),
        )

    def _insert_candidate_evidence_link(
        self,
        connection: sqlite3.Connection,
        link: CandidateEvidenceLinkRecord,
    ) -> None:
        connection.execute(
            """
            INSERT INTO trip_candidate_evidence_links(
              id, trip_id, trip_candidate_id, source_artifact_id, import_job_id,
              mention_id, review_decision_id, resolution_candidate_id,
              document_generation_id, document_page_number, document_span_id,
              bounding_boxes_json, source_digest, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link.id, link.trip_id, link.trip_candidate_id, link.source_artifact_id,
                link.import_job_id, link.mention_id, link.review_decision_id,
                link.resolution_candidate_id, link.document_generation_id,
                link.document_page_number, link.document_span_id,
                canonical_json(link.bounding_boxes), link.source_digest, link.created_at,
            ),
        )

    def _insert_candidate_decision(
        self,
        connection: sqlite3.Connection,
        decision: TripCandidateDecisionRecord,
    ) -> None:
        connection.execute(
            """
            INSERT INTO trip_candidate_decisions(
              id, trip_id, candidate_id, decision_type, reason_code,
              base_revision_id, related_revision_id, source, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.id,
                decision.trip_id,
                decision.candidate_id,
                decision.decision_type,
                decision.reason_code,
                decision.base_revision_id,
                decision.related_revision_id,
                decision.source,
                decision.created_at,
            ),
        )

    def _get_revision_in_connection(
        self,
        connection: sqlite3.Connection,
        trip_id: str,
        revision_id: str,
    ) -> TripRevisionRecord:
        row = connection.execute(
            "SELECT * FROM trip_revisions WHERE id = ? AND trip_id = ?",
            (revision_id, trip_id),
        ).fetchone()
        if row is None:
            raise RevisionNotFoundError(revision_id)
        return row_to_revision(row)

    def _get_proposal_in_connection(
        self,
        connection: sqlite3.Connection,
        trip_id: str,
        proposal_id: str,
    ) -> TripMutationProposalRecord:
        row = connection.execute(
            "SELECT * FROM trip_mutation_proposals WHERE id = ? AND trip_id = ?",
            (proposal_id, trip_id),
        ).fetchone()
        if row is None:
            raise MutationProposalNotFoundError(proposal_id)
        return row_to_proposal(row)

    def _get_planner_handoff_run_in_connection(
        self,
        connection: sqlite3.Connection,
        trip_id: str,
        run_id: str,
    ) -> PlannerHandoffRunRecord:
        row = connection.execute(
            "SELECT * FROM planner_handoff_runs WHERE id = ? AND trip_id = ?",
            (run_id, trip_id),
        ).fetchone()
        if row is None:
            raise MutationProposalNotFoundError(run_id)
        return row_to_planner_handoff_run(row)

    def _get_candidate_in_connection(
        self,
        connection: sqlite3.Connection,
        trip_id: str,
        candidate_id: str,
    ) -> TripCandidateRecord:
        row = connection.execute(
            "SELECT * FROM trip_candidates WHERE id = ? AND trip_id = ?",
            (candidate_id, trip_id),
        ).fetchone()
        if row is None:
            raise CandidateNotFoundError(candidate_id)
        return row_to_candidate(row)

    def _get_candidate_decision_in_connection(
        self,
        connection: sqlite3.Connection,
        trip_id: str,
        decision_id: str,
    ) -> TripCandidateDecisionRecord:
        row = connection.execute(
            "SELECT * FROM trip_candidate_decisions WHERE id = ? AND trip_id = ?",
            (decision_id, trip_id),
        ).fetchone()
        if row is None:
            raise CandidateNotFoundError(decision_id)
        return row_to_candidate_decision(row)

    def _get_intent_revision_in_connection(
        self,
        connection: sqlite3.Connection,
        trip_id: str,
        revision_id: str,
    ) -> TripIntentRevisionRecord:
        row = connection.execute(
            "SELECT * FROM trip_intent_revisions WHERE id = ? AND trip_id = ?",
            (revision_id, trip_id),
        ).fetchone()
        if row is None:
            raise RevisionNotFoundError(revision_id)
        return row_to_intent_revision(row)

    def _assert_proposal_integrity(self, proposal: TripMutationProposalRecord) -> None:
        expected = mutation_proposal_digest(
            proposal_schema_version=proposal.proposal_schema_version,
            trip_id=proposal.trip_id,
            base_revision_id=proposal.base_revision_id,
            source_type=proposal.source_type,
            operation_type=proposal.operation_type,
            request_digest=proposal.request_digest,
            preview_snapshot_schema_version=proposal.preview_snapshot_schema_version,
            preview_content_digest=proposal.preview_content_digest,
            planner_run_id=proposal.planner_run_id,
            planner_version=proposal.planner_version,
            trace_schema_version=proposal.trace_schema_version,
            trace_digest=proposal.trace_digest,
            validation_report=proposal.validation_report,
            expires_at=proposal.expires_at,
            execution_kind=proposal.execution_kind,
            command_digest=proposal.command_digest,
            mutation_kind=proposal.mutation_kind,
            mutation_engine_version=proposal.mutation_engine_version,
        )
        if expected != proposal.proposal_digest:
            raise ProposalIntegrityViolationError()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def row_to_trip(row: sqlite3.Row) -> TripRecord:
    return TripRecord(
        id=row["id"],
        current_revision_id=row["current_revision_id"],
        revision_count=row["revision_count"],
        lifecycle_status=row["lifecycle_status"],
        planning_phase=row["planning_phase"],
        capability_hash=row["capability_hash"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_revision(row: sqlite3.Row) -> TripRevisionRecord:
    return TripRevisionRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        revision_number=row["revision_number"],
        parent_revision_id=row["parent_revision_id"],
        base_revision_id=row["base_revision_id"],
        source_type=row["source_type"],
        snapshot_schema_version=row["snapshot_schema_version"],
        itinerary_snapshot=json.loads(row["itinerary_snapshot"]),
        content_digest=row["content_digest"],
        parent_lineage_digest=row["parent_lineage_digest"],
        lineage_digest=row["lineage_digest"],
        planner_run_id=row["planner_run_id"],
        planner_version=row["planner_version"],
        trace_schema_version=row["trace_schema_version"],
        trace_digest=row["trace_digest"],
        restored_from_revision_id=row["restored_from_revision_id"],
        created_at=row["created_at"],
    )


def row_to_intent_revision(row: sqlite3.Row) -> TripIntentRevisionRecord:
    return TripIntentRevisionRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        revision_number=row["revision_number"],
        parent_intent_revision_id=row["parent_intent_revision_id"],
        base_trip_revision_id=row["base_trip_revision_id"],
        envelope_schema_version=row["envelope_schema_version"],
        envelope=json.loads(row["envelope_json"]),
        content_digest=row["content_digest"],
        compiler_version=row["compiler_version"],
        source_digest=row["source_digest"],
        validation_report=json.loads(row["validation_report_json"]),
        created_at=row["created_at"],
    )


def row_to_draft_intent_revision(row: sqlite3.Row) -> DraftIntentRevisionRecord:
    return DraftIntentRevisionRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        revision_number=row["revision_number"],
        parent_draft_intent_revision_id=row["parent_draft_intent_revision_id"],
        envelope_schema_version=row["envelope_schema_version"],
        envelope=json.loads(row["envelope_json"]),
        content_digest=row["content_digest"],
        compiler_version=row["compiler_version"],
        source_digest=row["source_digest"],
        validation_report=json.loads(row["validation_report_json"]),
        created_at=row["created_at"],
    )


def row_to_proposal(row: sqlite3.Row) -> TripMutationProposalRecord:
    return TripMutationProposalRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        base_revision_id=row["base_revision_id"],
        proposal_schema_version=row["proposal_schema_version"],
        source_type=row["source_type"],
        operation_type=row["operation_type"],
        request_digest=row["request_digest"],
        instruction_digest=row["instruction_digest"],
        preview_snapshot_schema_version=row["preview_snapshot_schema_version"],
        preview_snapshot=json.loads(row["preview_snapshot_json"]),
        preview_content_digest=row["preview_content_digest"],
        proposal_digest=row["proposal_digest"],
        planner_run_id=row["planner_run_id"],
        planner_version=row["planner_version"],
        trace_schema_version=row["trace_schema_version"],
        trace_digest=row["trace_digest"],
        validation_report=json.loads(row["validation_report_json"]),
        execution_kind=row["execution_kind"],
        command_schema_version=row["command_schema_version"],
        mutation_engine_version=row["mutation_engine_version"],
        mutation_kind=row["mutation_kind"],
        commands=json.loads(row["commands_json"]) if row["commands_json"] is not None else None,
        command_digest=row["command_digest"],
        impact_summary=json.loads(row["impact_summary_json"]) if row["impact_summary_json"] is not None else None,
        invalidated_surfaces=json.loads(row["invalidated_surfaces_json"])
        if row["invalidated_surfaces_json"] is not None
        else None,
        status=row["status"],
        expires_at=row["expires_at"],
        applied_revision_id=row["applied_revision_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_planner_handoff_run(row: sqlite3.Row) -> PlannerHandoffRunRecord:
    return PlannerHandoffRunRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        base_trip_revision_id=row["base_trip_revision_id"],
        intent_revision_id=row["intent_revision_id"],
        intent_semantic_digest=row["intent_semantic_digest"],
        intent_lineage_digest=row["intent_lineage_digest"],
        input_schema_version=row["input_schema_version"],
        input_snapshot=json.loads(row["input_snapshot_json"]),
        input_digest=row["input_digest"],
        planner_version=row["planner_version"],
        trace_schema_version=row["trace_schema_version"],
        trace_snapshot=json.loads(row["trace_snapshot_json"]),
        trace_digest=row["trace_digest"],
        result_snapshot_schema_version=row["result_snapshot_schema_version"],
        result_snapshot=json.loads(row["result_snapshot_json"]),
        result_content_digest=row["result_content_digest"],
        validation_report=json.loads(row["validation_report_json"]),
        proposal_id=row["proposal_id"],
        status=row["status"],
        applied_revision_id=row["applied_revision_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_preplan_handoff_run(row: sqlite3.Row) -> PrePlanHandoffRunRecord:
    return PrePlanHandoffRunRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        draft_intent_revision_id=row["draft_intent_revision_id"],
        intent_semantic_digest=row["intent_semantic_digest"],
        intent_lineage_digest=row["intent_lineage_digest"],
        input_snapshot=json.loads(row["input_snapshot_json"]),
        input_digest=row["input_digest"],
        planner_version=row["planner_version"],
        trace_schema_version=row["trace_schema_version"],
        trace_snapshot=json.loads(row["trace_snapshot_json"]),
        trace_digest=row["trace_digest"],
        result_snapshot=json.loads(row["result_snapshot_json"]),
        result_content_digest=row["result_content_digest"],
        validation_report=json.loads(row["validation_report_json"]),
        status=row["status"],
        expires_at=row["expires_at"],
        applied_revision_id=row["applied_revision_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_candidate(row: sqlite3.Row) -> TripCandidateRecord:
    return TripCandidateRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        candidate_type=row["candidate_type"],
        display_name=row["display_name"],
        normalized_name=row["normalized_name"],
        canonical_place_id=row["canonical_place_id"],
        provider_place_id=row["provider_place_id"],
        category=row["category"],
        coordinates=json.loads(row["coordinates_json"]) if row["coordinates_json"] else None,
        address_summary=row["address_summary"],
        estimated_duration_minutes=row["estimated_duration_minutes"],
        preferred_time_block=row["preferred_time_block"],
        explicit_day_reference=row["explicit_day_reference"],
        source_kind=row["source_kind"],
        source_ref=row["source_ref"],
        evidence_refs=json.loads(row["evidence_refs_json"]),
        location_state=row["location_state"],
        route_state=row["route_state"],
        duration_state=row["duration_state"],
        confidence=row["confidence"],
        content_digest=row["content_digest"],
        created_at=row["created_at"],
    )


def row_to_candidate_evidence_link(row: sqlite3.Row) -> CandidateEvidenceLinkRecord:
    return CandidateEvidenceLinkRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        trip_candidate_id=row["trip_candidate_id"],
        source_artifact_id=row["source_artifact_id"],
        import_job_id=row["import_job_id"],
        mention_id=row["mention_id"],
        review_decision_id=row["review_decision_id"],
        resolution_candidate_id=row["resolution_candidate_id"],
        document_generation_id=row["document_generation_id"],
        document_page_number=row["document_page_number"],
        document_span_id=row["document_span_id"],
        bounding_boxes=json.loads(row["bounding_boxes_json"]),
        source_digest=row["source_digest"],
        created_at=row["created_at"],
    )


def row_to_candidate_decision(row: sqlite3.Row) -> TripCandidateDecisionRecord:
    return TripCandidateDecisionRecord(
        id=row["id"],
        trip_id=row["trip_id"],
        candidate_id=row["candidate_id"],
        decision_type=row["decision_type"],
        reason_code=row["reason_code"],
        base_revision_id=row["base_revision_id"],
        related_revision_id=row["related_revision_id"],
        source=row["source"],
        created_at=row["created_at"],
    )
