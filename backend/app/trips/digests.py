from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


TRIP_SNAPSHOT_SCHEMA_VERSION = "1.0"
TRIP_MUTATION_PROPOSAL_SCHEMA_VERSION = "1.0"
TRIP_MUTATION_COMMAND_SCHEMA_VERSION = "1.0"
TRIP_MUTATION_ENGINE_VERSION = "current-baseline"


def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    if isinstance(value, tuple):
        return [canonicalize(item) for item in value]
    if isinstance(value, datetime):
        normalized = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value.normalize())
    if isinstance(value, Enum):
        return value.value
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def itinerary_content_digest(snapshot: dict[str, Any]) -> str:
    return sha256_digest(snapshot)


def request_digest(payload: dict[str, Any]) -> str:
    return sha256_digest(payload)


def command_digest(payload: dict[str, Any]) -> str:
    return sha256_digest(payload)


def lineage_digest(
    *,
    parent_lineage_digest: str | None,
    source_type: str,
    operation_metadata: dict[str, Any],
    content_digest: str,
) -> str:
    payload = {
        "parent_lineage_digest": parent_lineage_digest,
        "source_type": source_type,
        "operation_metadata": operation_metadata,
        "content_digest": content_digest,
    }
    return sha256_digest(payload)


def validation_report_digest(validation_report: dict[str, Any]) -> str:
    return sha256_digest(validation_report)


def mutation_proposal_digest(
    *,
    proposal_schema_version: str,
    trip_id: str,
    base_revision_id: str,
    source_type: str,
    operation_type: str,
    request_digest: str,
    preview_snapshot_schema_version: str,
    preview_content_digest: str,
    planner_run_id: str | None,
    planner_version: str | None,
    trace_schema_version: str | None,
    trace_digest: str | None,
    validation_report: dict[str, Any],
    expires_at: str,
    execution_kind: str | None = None,
    command_digest: str | None = None,
    mutation_kind: str | None = None,
    mutation_engine_version: str | None = None,
) -> str:
    payload = {
        "proposal_schema_version": proposal_schema_version,
        "trip_id": trip_id,
        "base_revision_id": base_revision_id,
        "source_type": source_type,
        "operation_type": operation_type,
        "request_digest": request_digest,
        "preview_snapshot_schema_version": preview_snapshot_schema_version,
        "preview_content_digest": preview_content_digest,
        "planner_run_id": planner_run_id,
        "planner_version": planner_version,
        "trace_schema_version": trace_schema_version,
        "trace_digest": trace_digest,
        "validation_report_digest": validation_report_digest(validation_report),
        "expires_at": expires_at,
    }
    if any(
        value is not None
        for value in (execution_kind, command_digest, mutation_kind, mutation_engine_version)
    ):
        payload.update(
            {
                "execution_kind": execution_kind,
                "command_digest": command_digest,
                "mutation_kind": mutation_kind,
                "mutation_engine_version": mutation_engine_version,
            }
        )
    return sha256_digest(payload)
