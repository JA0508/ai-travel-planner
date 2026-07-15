from __future__ import annotations

import hashlib
import hmac
import secrets


CAPABILITY_COOKIE_PREFIX = "trip_capability_"


def generate_trip_id() -> str:
    return f"trip_{secrets.token_hex(16)}"


def generate_revision_id() -> str:
    return f"rev_{secrets.token_hex(16)}"


def generate_proposal_id() -> str:
    return f"prop_{secrets.token_hex(16)}"


def generate_operation_id() -> str:
    return f"op_{secrets.token_hex(16)}"


def generate_capability() -> str:
    return secrets.token_urlsafe(32)


def hash_capability(capability: str) -> str:
    return hashlib.sha256(capability.encode("utf-8")).hexdigest()


def verify_capability(raw_capability: str | None, stored_hash: str) -> bool:
    if not raw_capability:
        return False
    return hmac.compare_digest(hash_capability(raw_capability), stored_hash)


def hash_idempotency_key(idempotency_key: str) -> str:
    return hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()


def capability_cookie_name(trip_id: str) -> str:
    safe_trip_id = trip_id.replace("-", "_")
    return f"{CAPABILITY_COOKIE_PREFIX}{safe_trip_id}"
