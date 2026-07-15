from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from app.trips.access import generate_operation_id, generate_revision_id, generate_trip_id
from app.trips.digests import (
    TRIP_SNAPSHOT_SCHEMA_VERSION,
    canonical_json,
    itinerary_content_digest,
    lineage_digest,
)
from app.trips.errors import (
    IdempotencyConflictError,
    ImmutableRevisionViolationError,
    PersistenceSchemaMismatchError,
    PersistenceTemporarilyUnavailableError,
    RevisionNotFoundError,
    StaleBaseRevisionError,
    TripAccessDeniedError,
    TripNotFoundError,
)
from app.trips.models import (
    CreateRevisionResult,
    RevisionSourceType,
    TripAggregate,
    TripLifecycleStatus,
    TripRecord,
    TripRevisionRecord,
)


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
            if "immutable_revision_violation" in str(exc):
                raise ImmutableRevisionViolationError() from exc
            if "schema_migrations" in str(exc):
                raise PersistenceSchemaMismatchError() from exc
            raise
        except sqlite3.OperationalError as exc:
            connection.execute("ROLLBACK")
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise PersistenceTemporarilyUnavailableError() from exc
            if "immutable_revision_violation" in str(exc):
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

    def _insert_operation(self, connection: sqlite3.Connection, **values: Any) -> None:
        connection.execute(
            """
            INSERT INTO revision_operations(
              id, trip_id, revision_id, base_revision_id, source_type, operation_type,
              request_digest, idempotency_key_hash, actor_type, summary, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["operation_id"],
                values["trip_id"],
                values["revision_id"],
                values["base_revision_id"],
                values["source_type"],
                values["operation_type"],
                values["request_digest"],
                values["idempotency_key_hash"],
                "anonymous",
                values["summary"],
                values["created_at"],
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def row_to_trip(row: sqlite3.Row) -> TripRecord:
    return TripRecord(
        id=row["id"],
        current_revision_id=row["current_revision_id"],
        revision_count=row["revision_count"],
        lifecycle_status=row["lifecycle_status"],
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
