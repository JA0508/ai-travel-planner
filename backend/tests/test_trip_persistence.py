from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.persistence.database import SQLiteConnectionFactory
from app.persistence.sqlite_trip_repository import SQLiteTripRepository
from app.schemas import ItineraryResponse, PlanningAnchorSource
from app.trips.access import generate_capability, hash_capability, hash_idempotency_key
from app.trips.digests import itinerary_content_digest, lineage_digest, request_digest
from app.trips.errors import (
    IdempotencyConflictError,
    ImmutableRevisionViolationError,
    StaleBaseRevisionError,
    TripAccessDeniedError,
)
from app.trips.models import RevisionSourceType


class TripPersistenceTests(unittest.TestCase):
    def test_content_digest_is_stable_and_ignores_key_order(self) -> None:
        snapshot_a = {"trip_days": 1, "days": [], "planning_anchor_source": {"source_name": "上海", "source_type": "city"}}
        snapshot_b = {"planning_anchor_source": {"source_type": "city", "source_name": "上海"}, "days": [], "trip_days": 1}
        snapshot_c = {"planning_anchor_source": {"source_type": "city", "source_name": "上海"}, "days": [], "trip_days": 2}

        self.assertEqual(itinerary_content_digest(snapshot_a), itinerary_content_digest(snapshot_b))
        self.assertNotEqual(itinerary_content_digest(snapshot_a), itinerary_content_digest(snapshot_c))

    def test_lineage_digest_changes_with_parent_and_operation_metadata(self) -> None:
        content_digest = itinerary_content_digest(simple_snapshot(1))
        first = lineage_digest(
            parent_lineage_digest="parent-a",
            source_type="completion_patch",
            operation_metadata={"task_id": "repair_sparse_block"},
            content_digest=content_digest,
        )
        different_parent = lineage_digest(
            parent_lineage_digest="parent-b",
            source_type="completion_patch",
            operation_metadata={"task_id": "repair_sparse_block"},
            content_digest=content_digest,
        )
        different_operation = lineage_digest(
            parent_lineage_digest="parent-a",
            source_type="completion_patch",
            operation_metadata={"task_id": "repair_meal_anchor"},
            content_digest=content_digest,
        )

        self.assertNotEqual(first, different_parent)
        self.assertNotEqual(first, different_operation)

    def test_sqlite_repository_reopens_with_identical_current_revision(self) -> None:
        with temp_repository() as context:
            aggregate = context.repo.create_trip_with_initial_revision(
                itinerary_snapshot=simple_snapshot(1),
                capability_hash=context.capability_hash,
                operation_type="generate_itinerary",
                operation_summary="initial",
                request_digest=request_digest({"request": "initial"}),
                planner_run_id="run-a",
                planner_version="planner-a",
                trace_schema_version="1.0",
                trace_digest="trace-a",
            )
            reopened = SQLiteTripRepository(context.factory.connect)
            current = reopened.get_current_revision(aggregate.trip.id)

            self.assertEqual(current.id, aggregate.current_revision.id)
            self.assertEqual(current.content_digest, aggregate.current_revision.content_digest)
            self.assertEqual(current.lineage_digest, aggregate.current_revision.lineage_digest)
            self.assertEqual(current.planner_run_id, "run-a")

    def test_sqlite_revisions_and_operations_are_append_only(self) -> None:
        with temp_repository() as context:
            aggregate = context.repo.create_trip_with_initial_revision(
                itinerary_snapshot=simple_snapshot(1),
                capability_hash=context.capability_hash,
                operation_type="generate_itinerary",
                operation_summary="initial",
                request_digest=request_digest({"request": "initial"}),
                planner_run_id=None,
                planner_version=None,
                trace_schema_version=None,
                trace_digest=None,
            )

            with closing(context.factory.connect()) as connection:
                with self.assertRaises(Exception):
                    connection.execute(
                        "UPDATE trip_revisions SET source_type = 'restore' WHERE id = ?",
                        (aggregate.current_revision.id,),
                    )
                with self.assertRaises(Exception):
                    connection.execute(
                        "DELETE FROM trip_revisions WHERE id = ?",
                        (aggregate.current_revision.id,),
                    )

    def test_idempotent_retry_is_checked_before_stale_base(self) -> None:
        with temp_repository() as context:
            aggregate = context.repo.create_trip_with_initial_revision(
                itinerary_snapshot=simple_snapshot(1),
                capability_hash=context.capability_hash,
                operation_type="generate_itinerary",
                operation_summary="initial",
                request_digest=request_digest({"request": "initial"}),
                planner_run_id=None,
                planner_version=None,
                trace_schema_version=None,
                trace_digest=None,
            )
            base_revision_id = aggregate.current_revision.id
            idem_hash = hash_idempotency_key("same-click")
            req_digest = request_digest({"task_id": "repair_sparse_block"})

            created = context.repo.create_revision(
                trip_id=aggregate.trip.id,
                capability_hash=context.capability_hash,
                base_revision_id=base_revision_id,
                itinerary_snapshot=simple_snapshot(2),
                source_type=RevisionSourceType.COMPLETION_PATCH.value,
                operation_type="apply_completion_task",
                operation_summary="inserted",
                operation_metadata={"task_id": "repair_sparse_block"},
                request_digest=req_digest,
                idempotency_key_hash=idem_hash,
            )
            retried = context.repo.create_revision(
                trip_id=aggregate.trip.id,
                capability_hash=context.capability_hash,
                base_revision_id=base_revision_id,
                itinerary_snapshot=simple_snapshot(2),
                source_type=RevisionSourceType.COMPLETION_PATCH.value,
                operation_type="apply_completion_task",
                operation_summary="inserted",
                operation_metadata={"task_id": "repair_sparse_block"},
                request_digest=req_digest,
                idempotency_key_hash=idem_hash,
            )

            self.assertEqual(retried.revision.id, created.revision.id)
            self.assertTrue(retried.idempotent_replay)
            self.assertEqual(context.repo.get_trip(aggregate.trip.id).revision_count, 2)

    def test_stale_write_and_idempotency_conflict_are_rejected(self) -> None:
        with temp_repository() as context:
            aggregate = context.repo.create_trip_with_initial_revision(
                itinerary_snapshot=simple_snapshot(1),
                capability_hash=context.capability_hash,
                operation_type="generate_itinerary",
                operation_summary="initial",
                request_digest=request_digest({"request": "initial"}),
                planner_run_id=None,
                planner_version=None,
                trace_schema_version=None,
                trace_digest=None,
            )
            base_revision_id = aggregate.current_revision.id
            context.repo.create_revision(
                trip_id=aggregate.trip.id,
                capability_hash=context.capability_hash,
                base_revision_id=base_revision_id,
                itinerary_snapshot=simple_snapshot(2),
                source_type=RevisionSourceType.COMPLETION_PATCH.value,
                operation_type="apply_completion_task",
                operation_summary="inserted",
                operation_metadata={"task_id": "a"},
                request_digest=request_digest({"task_id": "a"}),
                idempotency_key_hash=hash_idempotency_key("key-a"),
            )

            with self.assertRaises(StaleBaseRevisionError):
                context.repo.create_revision(
                    trip_id=aggregate.trip.id,
                    capability_hash=context.capability_hash,
                    base_revision_id=base_revision_id,
                    itinerary_snapshot=simple_snapshot(3),
                    source_type=RevisionSourceType.COMPLETION_PATCH.value,
                    operation_type="apply_completion_task",
                    operation_summary="inserted",
                    operation_metadata={"task_id": "b"},
                    request_digest=request_digest({"task_id": "b"}),
                    idempotency_key_hash=hash_idempotency_key("key-b"),
                )

            with self.assertRaises(IdempotencyConflictError):
                context.repo.create_revision(
                    trip_id=aggregate.trip.id,
                    capability_hash=context.capability_hash,
                    base_revision_id=base_revision_id,
                    itinerary_snapshot=simple_snapshot(2),
                    source_type=RevisionSourceType.COMPLETION_PATCH.value,
                    operation_type="apply_completion_task",
                    operation_summary="inserted",
                    operation_metadata={"task_id": "changed"},
                    request_digest=request_digest({"task_id": "changed"}),
                    idempotency_key_hash=hash_idempotency_key("key-a"),
                )

    def test_wrong_capability_is_denied_without_serializing_secret(self) -> None:
        with temp_repository() as context:
            aggregate = context.repo.create_trip_with_initial_revision(
                itinerary_snapshot=simple_snapshot(1),
                capability_hash=context.capability_hash,
                operation_type="generate_itinerary",
                operation_summary="initial",
                request_digest=request_digest({"request": "initial"}),
                planner_run_id=None,
                planner_version=None,
                trace_schema_version=None,
                trace_digest=None,
            )

            with self.assertRaises(TripAccessDeniedError):
                context.repo.get_trip_for_access(aggregate.trip.id, hash_capability("wrong"))


class TempRepositoryContext:
    def __init__(self, root: tempfile.TemporaryDirectory[str]) -> None:
        self.root = root
        self.path = Path(root.name) / "trip-store.sqlite3"
        self.factory = SQLiteConnectionFactory(self.path)
        self.factory.initialize()
        self.repo = SQLiteTripRepository(self.factory.connect)
        self.capability = generate_capability()
        self.capability_hash = hash_capability(self.capability)


class temp_repository:
    def __enter__(self) -> TempRepositoryContext:
        self.root = tempfile.TemporaryDirectory()
        self.context = TempRepositoryContext(self.root)
        return self.context

    def __exit__(self, *args) -> None:
        self.root.cleanup()


def simple_snapshot(trip_days: int) -> dict:
    itinerary = ItineraryResponse(
        trip_days=trip_days,
        planning_anchor_source=PlanningAnchorSource(source_type="city", source_name="上海"),
        days=[],
    )
    return itinerary.model_dump(mode="json")


if __name__ == "__main__":
    unittest.main()
