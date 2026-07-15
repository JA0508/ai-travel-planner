from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TripLifecycleStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class RevisionSourceType(str, Enum):
    PLANNER_GENERATION = "planner_generation"
    PLANNER_REGENERATION = "planner_regeneration"
    REPLAN_PATCH = "replan_patch"
    COMPLETION_PATCH = "completion_patch"
    ROUTE_EDIT = "route_edit"
    RESTORE = "restore"
    SYSTEM_MIGRATION = "system_migration"


@dataclass(slots=True)
class TripRecord:
    id: str
    current_revision_id: str
    revision_count: int
    lifecycle_status: str
    capability_hash: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class TripRevisionRecord:
    id: str
    trip_id: str
    revision_number: int
    parent_revision_id: str | None
    base_revision_id: str | None
    source_type: str
    snapshot_schema_version: str
    itinerary_snapshot: dict[str, Any]
    content_digest: str
    parent_lineage_digest: str | None
    lineage_digest: str
    planner_run_id: str | None
    planner_version: str | None
    trace_schema_version: str | None
    trace_digest: str | None
    restored_from_revision_id: str | None
    created_at: str


@dataclass(slots=True)
class RevisionOperationRecord:
    id: str
    trip_id: str
    revision_id: str
    base_revision_id: str | None
    source_type: str
    operation_type: str
    request_digest: str
    idempotency_key_hash: str | None
    actor_type: str
    summary: str
    created_at: str


@dataclass(slots=True)
class TripAggregate:
    trip: TripRecord
    current_revision: TripRevisionRecord


@dataclass(slots=True)
class CreateRevisionResult:
    revision: TripRevisionRecord
    idempotent_replay: bool = False
