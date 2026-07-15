from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


TRIP_SNAPSHOT_SCHEMA_VERSION = "1.0"


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
