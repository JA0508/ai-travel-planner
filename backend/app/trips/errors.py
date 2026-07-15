from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TripError(Exception):
    code: str
    message: str
    status_code: int = 400
    context: dict[str, Any] | None = None

    def to_error_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "recoverable": self.status_code in {409, 503},
        }
        if self.context:
            payload.update(self.context)
        return {"error": payload}


class TripNotFoundError(TripError):
    def __init__(self, trip_id: str) -> None:
        super().__init__(
            code="trip_not_found",
            message="Trip was not found.",
            status_code=404,
            context={"trip_id": trip_id},
        )


class TripAccessDeniedError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="trip_access_denied",
            message="Trip access denied.",
            status_code=403,
        )


class RevisionNotFoundError(TripError):
    def __init__(self, revision_id: str) -> None:
        super().__init__(
            code="revision_not_found",
            message="Revision was not found.",
            status_code=404,
            context={"revision_id": revision_id},
        )


class RevisionNotInTripError(TripError):
    def __init__(self, trip_id: str, revision_id: str) -> None:
        super().__init__(
            code="revision_not_in_trip",
            message="Revision does not belong to this trip.",
            status_code=404,
            context={"trip_id": trip_id, "revision_id": revision_id},
        )


class StaleBaseRevisionError(TripError):
    def __init__(
        self,
        *,
        trip_id: str,
        provided_base_revision_id: str,
        current_revision_id: str,
    ) -> None:
        super().__init__(
            code="stale_base_revision",
            message="The mutation was based on a stale revision.",
            status_code=409,
            context={
                "trip_id": trip_id,
                "provided_base_revision_id": provided_base_revision_id,
                "current_revision_id": current_revision_id,
            },
        )


class IdempotencyConflictError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="idempotency_conflict",
            message="The idempotency key was already used for a different request.",
            status_code=409,
        )


class InvalidRevisionOperationError(TripError):
    def __init__(self, message: str = "Invalid revision operation.") -> None:
        super().__init__(
            code="invalid_revision_operation",
            message=message,
            status_code=422,
        )


class MutationProposalMismatchError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="mutation_proposal_mismatch",
            message="The applied mutation no longer matches the previewed proposal.",
            status_code=409,
        )


class ImmutableRevisionViolationError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="immutable_revision_violation",
            message="Trip revisions and revision operations are immutable.",
            status_code=409,
        )


class PersistenceTemporarilyUnavailableError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="persistence_temporarily_unavailable",
            message="Trip persistence is temporarily unavailable.",
            status_code=503,
        )


class PersistenceSchemaMismatchError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="persistence_schema_mismatch",
            message="Trip persistence schema is not compatible with this application.",
            status_code=503,
        )


class SnapshotSchemaUnsupportedError(TripError):
    def __init__(self, schema_version: str) -> None:
        super().__init__(
            code="snapshot_schema_unsupported",
            message="Trip snapshot schema is not supported.",
            status_code=409,
            context={"snapshot_schema_version": schema_version},
        )
