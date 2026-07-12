from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import PlannerTrace


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def planner_trace_digest(trace: PlannerTrace) -> str:
    return hashlib.sha256(
        canonical_json(trace.deterministic_payload()).encode("utf-8")
    ).hexdigest()
