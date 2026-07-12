from __future__ import annotations

import hashlib
import json


def stable_subject_id(subject_type: str, *parts: object) -> str:
    payload = json.dumps(
        [subject_type, *parts],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{subject_type}:{digest}"
