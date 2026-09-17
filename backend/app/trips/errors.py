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


class StaleIntentRevisionError(TripError):
    def __init__(
        self,
        *,
        trip_id: str,
        provided_intent_revision_id: str,
        current_intent_revision_id: str,
    ) -> None:
        super().__init__(
            code="stale_intent_revision",
            message="The intent edit was based on a stale intent revision.",
            status_code=409,
            context={
                "trip_id": trip_id,
                "provided_intent_revision_id": provided_intent_revision_id,
                "current_intent_revision_id": current_intent_revision_id,
            },
        )


class StaleDraftRevisionError(TripError):
    def __init__(self, *, trip_id: str, provided_draft_version: int, current_draft_version: int) -> None:
        super().__init__(
            code="stale_draft_revision",
            message="The draft was updated before this edit could be applied.",
            status_code=409,
            context={"trip_id": trip_id, "provided_draft_version": provided_draft_version, "current_draft_version": current_draft_version},
        )


class DraftIntentEditError(TripError):
    def __init__(self, code: str) -> None:
        super().__init__(code=code, message="The draft intent edit is not valid for the current draft.", status_code=422)


class PlaceIdentityProviderUnavailableError(TripError):
    """A provider-backed identity operation can be retried without changing a draft."""

    def __init__(self) -> None:
        super().__init__(
            code="place_identity_provider_unavailable",
            message="Place identity provider is temporarily unavailable.",
            status_code=503,
        )


class ClarificationAlreadyResolvedError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="clarification_already_resolved",
            message="This clarification has already been resolved in a newer draft revision.",
            status_code=409,
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


class PlannerHandoffBlockedError(TripError):
    def __init__(
        self,
        reason_code: str,
        *,
        candidate_id: str | None = None,
        field_id: str | None = None,
        place_stable_id: str | None = None,
    ) -> None:
        context = {"reason_code": reason_code}
        if candidate_id:
            context["candidate_id"] = candidate_id
        if field_id:
            context["field_id"] = field_id
        if place_stable_id:
            context["place_stable_id"] = place_stable_id
        super().__init__(
            code="planner_handoff_blocked",
            message="The confirmed intent cannot safely enter the planner.",
            status_code=422,
            context=context,
        )


class UnsupportedMutationCommandSchemaError(TripError):
    def __init__(self, schema_version: str) -> None:
        super().__init__(
            code="unsupported_mutation_command_schema",
            message="Mutation command schema is not supported.",
            status_code=422,
            context={"schema_version": schema_version},
        )


class MutationCommandFailedError(TripError):
    def __init__(self, *, command_index: int, reason_code: str) -> None:
        super().__init__(
            code="mutation_command_failed",
            message="Mutation command failed deterministic validation.",
            status_code=422,
            context={"command_index": command_index, "reason_code": reason_code},
        )


class MutationCommandNoEffectError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="mutation_command_no_effect",
            message="Mutation command batch has no effective itinerary change.",
            status_code=422,
            context={"reason_code": "no_effective_mutation"},
        )


class CommandDigestMismatchError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="command_digest_mismatch",
            message="Mutation command digest does not match.",
            status_code=409,
        )


class MutationProposalNotFoundError(TripError):
    def __init__(self, proposal_id: str) -> None:
        super().__init__(
            code="mutation_proposal_not_found",
            message="Mutation proposal was not found.",
            status_code=404,
            context={"proposal_id": proposal_id},
        )


class MutationProposalExpiredError(TripError):
    def __init__(self, proposal_id: str) -> None:
        super().__init__(
            code="mutation_proposal_expired",
            message="Mutation proposal has expired.",
            status_code=409,
            context={"proposal_id": proposal_id},
        )


class MutationProposalInvalidatedError(TripError):
    def __init__(self, proposal_id: str) -> None:
        super().__init__(
            code="mutation_proposal_invalidated",
            message="Mutation proposal is no longer valid.",
            status_code=409,
            context={"proposal_id": proposal_id},
        )


class MutationProposalCancelledError(TripError):
    def __init__(self, proposal_id: str) -> None:
        super().__init__(
            code="mutation_proposal_cancelled",
            message="Mutation proposal was cancelled.",
            status_code=409,
            context={"proposal_id": proposal_id},
        )


class StaleMutationProposalError(TripError):
    def __init__(
        self,
        *,
        trip_id: str,
        proposal_id: str,
        base_revision_id: str,
        current_revision_id: str,
    ) -> None:
        super().__init__(
            code="stale_mutation_proposal",
            message="The mutation proposal is based on a stale revision.",
            status_code=409,
            context={
                "trip_id": trip_id,
                "proposal_id": proposal_id,
                "base_revision_id": base_revision_id,
                "current_revision_id": current_revision_id,
            },
        )


class ProposalDigestMismatchError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="proposal_digest_mismatch",
            message="Mutation proposal digest does not match.",
            status_code=409,
        )


class ProposalIntegrityViolationError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="proposal_integrity_violation",
            message="Mutation proposal integrity check failed.",
            status_code=409,
        )


class PreviewApplyMismatchError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="preview_apply_mismatch",
            message="Applied revision content does not match preview content.",
            status_code=409,
        )


class RevisionNotUndoableError(TripError):
    def __init__(self, revision_id: str) -> None:
        super().__init__(
            code="revision_not_undoable",
            message="Revision is not undoable.",
            status_code=409,
            context={"revision_id": revision_id},
        )


class RestoreWouldDropFixedItemsError(TripError):
    def __init__(self, *, protected_item_count: int) -> None:
        super().__init__(
            code="restore_would_drop_fixed_items",
            message="Restoring this revision would remove or change a fixed arrangement.",
            status_code=409,
            context={"protected_item_count": protected_item_count},
        )


class RestoreWouldDropMustVisitPlacesError(TripError):
    def __init__(self, *, protected_item_count: int) -> None:
        super().__init__(
            code="restore_would_drop_must_visit_places",
            message="Restoring this revision would remove a current must-visit place.",
            status_code=409,
            context={"protected_item_count": protected_item_count},
        )


class CandidateNotFoundError(TripError):
    def __init__(self, candidate_id: str) -> None:
        super().__init__(
            code="candidate_not_found",
            message="Trip candidate was not found.",
            status_code=404,
            context={"candidate_id": candidate_id},
        )


class CandidateWrongTripError(TripError):
    def __init__(self, candidate_id: str) -> None:
        super().__init__(
            code="candidate_wrong_trip",
            message="Trip candidate does not belong to this trip.",
            status_code=404,
            context={"candidate_id": candidate_id},
        )


class CandidateDecisionConflictError(TripError):
    def __init__(self) -> None:
        super().__init__(
            code="candidate_decision_conflict",
            message="Candidate decision conflicts with the current workflow state.",
            status_code=409,
        )


class CandidateAdmissionRepairRequiredError(TripError):
    def __init__(self, *, candidate_id: str, repair: dict[str, Any]) -> None:
        super().__init__(
            code="candidate_admission_repair_required",
            message="Candidate admission requires an explicit repair before it can be scheduled.",
            status_code=409,
            context={"candidate_id": candidate_id, "repair": repair},
        )


class CandidateRejectedError(TripError):
    def __init__(self, candidate_id: str) -> None:
        super().__init__(
            code="candidate_rejected",
            message="Rejected candidates cannot be admitted without restoring them to pending.",
            status_code=409,
            context={"candidate_id": candidate_id},
        )


class CandidateAlreadyScheduledError(TripError):
    def __init__(self, candidate_id: str) -> None:
        super().__init__(
            code="candidate_already_scheduled",
            message="Candidate has already been scheduled.",
            status_code=409,
            context={"candidate_id": candidate_id},
        )


class UndoTargetNotCurrentError(TripError):
    def __init__(self, *, target_revision_id: str, current_revision_id: str) -> None:
        super().__init__(
            code="undo_target_not_current",
            message="Only the current undoable revision can be undone.",
            status_code=409,
            context={
                "target_revision_id": target_revision_id,
                "current_revision_id": current_revision_id,
            },
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
