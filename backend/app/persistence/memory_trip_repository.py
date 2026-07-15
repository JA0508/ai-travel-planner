from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from app.trips.access import generate_operation_id, generate_revision_id, generate_trip_id
from app.trips.digests import (
    TRIP_SNAPSHOT_SCHEMA_VERSION,
    itinerary_content_digest,
    lineage_digest,
    mutation_proposal_digest,
)
from app.trips.errors import (
    IdempotencyConflictError,
    MutationProposalCancelledError,
    MutationProposalExpiredError,
    MutationProposalInvalidatedError,
    MutationProposalNotFoundError,
    ProposalDigestMismatchError,
    ProposalIntegrityViolationError,
    RevisionNotFoundError,
    StaleBaseRevisionError,
    StaleMutationProposalError,
    TripAccessDeniedError,
    TripNotFoundError,
)
from app.trips.models import (
    CreateRevisionResult,
    ProposalStatus,
    RevisionOperationRecord,
    RevisionSourceType,
    TripAggregate,
    TripLifecycleStatus,
    TripMutationProposalRecord,
    TripRecord,
    TripRevisionRecord,
)


class MemoryTripRepository:
    def __init__(self) -> None:
        self.trips: dict[str, TripRecord] = {}
        self.revisions: dict[str, TripRevisionRecord] = {}
        self.operations: dict[str, RevisionOperationRecord] = {}
        self.idempotency_records: dict[tuple[str, str], tuple[str, str]] = {}
        self.proposals: dict[str, TripMutationProposalRecord] = {}

    def health_check(self) -> dict[str, Any]:
        return {
            "mode": "memory",
            "schema_version": "memory",
            "status": "healthy",
        }

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
        now = utc_now()
        content_digest = itinerary_content_digest(itinerary_snapshot)
        line_digest = lineage_digest(
            parent_lineage_digest=None,
            source_type=RevisionSourceType.PLANNER_GENERATION.value,
            operation_metadata={"operation_type": operation_type},
            content_digest=content_digest,
        )
        trip = TripRecord(
            id=trip_id,
            current_revision_id=revision_id,
            revision_count=1,
            lifecycle_status=TripLifecycleStatus.ACTIVE.value,
            capability_hash=capability_hash,
            created_at=now,
            updated_at=now,
        )
        revision = TripRevisionRecord(
            id=revision_id,
            trip_id=trip_id,
            revision_number=1,
            parent_revision_id=None,
            base_revision_id=None,
            source_type=RevisionSourceType.PLANNER_GENERATION.value,
            snapshot_schema_version=TRIP_SNAPSHOT_SCHEMA_VERSION,
            itinerary_snapshot=copy.deepcopy(itinerary_snapshot),
            content_digest=content_digest,
            parent_lineage_digest=None,
            lineage_digest=line_digest,
            planner_run_id=planner_run_id,
            planner_version=planner_version,
            trace_schema_version=trace_schema_version,
            trace_digest=trace_digest,
            restored_from_revision_id=None,
            created_at=now,
        )
        operation = RevisionOperationRecord(
            id=generate_operation_id(),
            trip_id=trip_id,
            revision_id=revision_id,
            base_revision_id=None,
            source_type=RevisionSourceType.PLANNER_GENERATION.value,
            operation_type=operation_type,
            operation_metadata={"operation_type": operation_type},
            request_digest=request_digest,
            idempotency_key_hash=None,
            actor_type="anonymous",
            summary=operation_summary,
            created_at=now,
        )
        self.trips[trip_id] = trip
        self.revisions[revision_id] = revision
        self.operations[operation.id] = operation
        return TripAggregate(trip=copy.deepcopy(trip), current_revision=copy.deepcopy(revision))

    def get_trip(self, trip_id: str) -> TripRecord:
        trip = self.trips.get(trip_id)
        if trip is None:
            raise TripNotFoundError(trip_id)
        return copy.deepcopy(trip)

    def get_trip_for_access(self, trip_id: str, capability_hash: str) -> TripRecord:
        trip = self.get_trip(trip_id)
        if trip.capability_hash != capability_hash:
            raise TripAccessDeniedError()
        return trip

    def get_current_revision(self, trip_id: str) -> TripRevisionRecord:
        trip = self.get_trip(trip_id)
        return self.get_revision(trip_id, trip.current_revision_id)

    def get_revision(self, trip_id: str, revision_id: str) -> TripRevisionRecord:
        revision = self.revisions.get(revision_id)
        if revision is None or revision.trip_id != trip_id:
            raise RevisionNotFoundError(revision_id)
        return copy.deepcopy(revision)

    def list_revisions(self, trip_id: str) -> list[TripRevisionRecord]:
        return sorted(
            [copy.deepcopy(rev) for rev in self.revisions.values() if rev.trip_id == trip_id],
            key=lambda revision: revision.revision_number,
            reverse=True,
        )

    def get_idempotent_revision(
        self,
        *,
        trip_id: str,
        capability_hash: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> CreateRevisionResult | None:
        self.get_trip_for_access(trip_id, capability_hash)
        idempotency_record = self.idempotency_records.get((trip_id, idempotency_key_hash))
        if idempotency_record is None:
            return None
        stored_request_digest, result_revision_id = idempotency_record
        if stored_request_digest != request_digest:
            raise IdempotencyConflictError()
        return CreateRevisionResult(
            revision=self.get_revision(trip_id, result_revision_id),
            idempotent_replay=True,
        )

    def create_mutation_proposal(
        self,
        *,
        proposal: TripMutationProposalRecord,
    ) -> TripMutationProposalRecord:
        self.get_revision(proposal.trip_id, proposal.base_revision_id)
        self.proposals[proposal.id] = copy.deepcopy(proposal)
        return copy.deepcopy(proposal)

    def get_mutation_proposal(
        self,
        *,
        trip_id: str,
        proposal_id: str,
    ) -> TripMutationProposalRecord:
        proposal = self.proposals.get(proposal_id)
        if proposal is None or proposal.trip_id != trip_id:
            raise MutationProposalNotFoundError(proposal_id)
        return copy.deepcopy(proposal)

    def apply_mutation_proposal(
        self,
        *,
        trip_id: str,
        capability_hash: str,
        proposal_id: str,
        base_revision_id: str,
        proposal_digest: str,
        now: str,
        operation_summary: str,
        operation_metadata: dict[str, Any],
        request_digest: str,
        idempotency_key_hash: str,
    ) -> CreateRevisionResult:
        trip = self.get_trip_for_access(trip_id, capability_hash)
        idempotency_record = self.idempotency_records.get((trip_id, idempotency_key_hash))
        if idempotency_record is not None:
            stored_request_digest, result_revision_id = idempotency_record
            if stored_request_digest != request_digest:
                raise IdempotencyConflictError()
            return CreateRevisionResult(
                revision=self.get_revision(trip_id, result_revision_id),
                idempotent_replay=True,
            )

        proposal = self.get_mutation_proposal(trip_id=trip_id, proposal_id=proposal_id)
        if proposal.applied_revision_id is not None:
            return CreateRevisionResult(
                revision=self.get_revision(trip_id, proposal.applied_revision_id),
                idempotent_replay=True,
            )
        if proposal.status == ProposalStatus.EXPIRED.value:
            raise MutationProposalExpiredError(proposal_id)
        if proposal.status == ProposalStatus.CANCELLED.value:
            raise MutationProposalCancelledError(proposal_id)
        if proposal.status == ProposalStatus.INVALIDATED.value:
            raise MutationProposalInvalidatedError(proposal_id)
        if proposal.status != ProposalStatus.PENDING.value:
            raise ProposalIntegrityViolationError()
        if now >= proposal.expires_at:
            proposal.status = ProposalStatus.EXPIRED.value
            proposal.updated_at = now
            self.proposals[proposal_id] = copy.deepcopy(proposal)
            raise MutationProposalExpiredError(proposal_id)
        if proposal.base_revision_id != base_revision_id or proposal.proposal_digest != proposal_digest:
            raise ProposalDigestMismatchError()
        self._assert_proposal_integrity(proposal)
        current_revision = self.get_revision(trip_id, trip.current_revision_id)
        if current_revision.id != proposal.base_revision_id:
            raise StaleMutationProposalError(
                trip_id=trip_id,
                proposal_id=proposal_id,
                base_revision_id=proposal.base_revision_id,
                current_revision_id=current_revision.id,
            )
        content_digest = itinerary_content_digest(proposal.preview_snapshot)
        if content_digest != proposal.preview_content_digest:
            raise ProposalIntegrityViolationError()

        revision_id = generate_revision_id()
        line_digest = lineage_digest(
            parent_lineage_digest=current_revision.lineage_digest,
            source_type=proposal.source_type,
            operation_metadata=operation_metadata,
            content_digest=content_digest,
        )
        revision = TripRevisionRecord(
            id=revision_id,
            trip_id=trip_id,
            revision_number=trip.revision_count + 1,
            parent_revision_id=current_revision.id,
            base_revision_id=proposal.base_revision_id,
            source_type=proposal.source_type,
            snapshot_schema_version=TRIP_SNAPSHOT_SCHEMA_VERSION,
            itinerary_snapshot=copy.deepcopy(proposal.preview_snapshot),
            content_digest=content_digest,
            parent_lineage_digest=current_revision.lineage_digest,
            lineage_digest=line_digest,
            planner_run_id=proposal.planner_run_id,
            planner_version=proposal.planner_version,
            trace_schema_version=proposal.trace_schema_version,
            trace_digest=proposal.trace_digest,
            restored_from_revision_id=None,
            created_at=now,
        )
        operation = RevisionOperationRecord(
            id=generate_operation_id(),
            trip_id=trip_id,
            revision_id=revision_id,
            base_revision_id=proposal.base_revision_id,
            source_type=proposal.source_type,
            operation_type=proposal.operation_type,
            operation_metadata=copy.deepcopy(operation_metadata),
            request_digest=request_digest,
            idempotency_key_hash=idempotency_key_hash,
            actor_type="anonymous",
            summary=operation_summary,
            created_at=now,
        )
        self.revisions[revision_id] = revision
        self.operations[operation.id] = operation
        self.idempotency_records[(trip_id, idempotency_key_hash)] = (request_digest, revision_id)
        proposal.status = ProposalStatus.APPLIED.value
        proposal.applied_revision_id = revision_id
        proposal.updated_at = now
        self.proposals[proposal_id] = copy.deepcopy(proposal)
        self.trips[trip_id] = TripRecord(
            id=trip.id,
            current_revision_id=revision_id,
            revision_count=revision.revision_number,
            lifecycle_status=trip.lifecycle_status,
            capability_hash=trip.capability_hash,
            created_at=trip.created_at,
            updated_at=now,
        )
        return CreateRevisionResult(revision=copy.deepcopy(revision))

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
        trip = self.get_trip_for_access(trip_id, capability_hash)
        idempotency_record = self.idempotency_records.get((trip_id, idempotency_key_hash))
        if idempotency_record is not None:
            stored_request_digest, result_revision_id = idempotency_record
            if stored_request_digest != request_digest:
                raise IdempotencyConflictError()
            return CreateRevisionResult(
                revision=self.get_revision(trip_id, result_revision_id),
                idempotent_replay=True,
            )

        current_revision = self.get_revision(trip_id, trip.current_revision_id)
        if current_revision.id != base_revision_id:
            raise StaleBaseRevisionError(
                trip_id=trip_id,
                provided_base_revision_id=base_revision_id,
                current_revision_id=current_revision.id,
            )

        now = utc_now()
        revision_id = generate_revision_id()
        content_digest = itinerary_content_digest(itinerary_snapshot)
        line_digest = lineage_digest(
            parent_lineage_digest=current_revision.lineage_digest,
            source_type=source_type,
            operation_metadata=operation_metadata,
            content_digest=content_digest,
        )
        revision = TripRevisionRecord(
            id=revision_id,
            trip_id=trip_id,
            revision_number=trip.revision_count + 1,
            parent_revision_id=current_revision.id,
            base_revision_id=base_revision_id,
            source_type=source_type,
            snapshot_schema_version=TRIP_SNAPSHOT_SCHEMA_VERSION,
            itinerary_snapshot=copy.deepcopy(itinerary_snapshot),
            content_digest=content_digest,
            parent_lineage_digest=current_revision.lineage_digest,
            lineage_digest=line_digest,
            planner_run_id=planner_run_id,
            planner_version=planner_version,
            trace_schema_version=trace_schema_version,
            trace_digest=trace_digest,
            restored_from_revision_id=restored_from_revision_id,
            created_at=now,
        )
        operation = RevisionOperationRecord(
            id=generate_operation_id(),
            trip_id=trip_id,
            revision_id=revision_id,
            base_revision_id=base_revision_id,
            source_type=source_type,
            operation_type=operation_type,
            operation_metadata=copy.deepcopy(operation_metadata),
            request_digest=request_digest,
            idempotency_key_hash=idempotency_key_hash,
            actor_type="anonymous",
            summary=operation_summary,
            created_at=now,
        )
        self.revisions[revision_id] = revision
        self.operations[operation.id] = operation
        self.idempotency_records[(trip_id, idempotency_key_hash)] = (
            request_digest,
            revision_id,
        )
        self.trips[trip_id] = TripRecord(
            id=trip.id,
            current_revision_id=revision_id,
            revision_count=revision.revision_number,
            lifecycle_status=trip.lifecycle_status,
            capability_hash=trip.capability_hash,
            created_at=trip.created_at,
            updated_at=now,
        )
        return CreateRevisionResult(revision=copy.deepcopy(revision))

    def _assert_proposal_integrity(self, proposal: TripMutationProposalRecord) -> None:
        expected = mutation_proposal_digest(
            proposal_schema_version=proposal.proposal_schema_version,
            trip_id=proposal.trip_id,
            base_revision_id=proposal.base_revision_id,
            source_type=proposal.source_type,
            operation_type=proposal.operation_type,
            request_digest=proposal.request_digest,
            preview_snapshot_schema_version=proposal.preview_snapshot_schema_version,
            preview_content_digest=proposal.preview_content_digest,
            planner_run_id=proposal.planner_run_id,
            planner_version=proposal.planner_version,
            trace_schema_version=proposal.trace_schema_version,
            trace_digest=proposal.trace_digest,
            validation_report=proposal.validation_report,
            expires_at=proposal.expires_at,
            execution_kind=proposal.execution_kind,
            command_digest=proposal.command_digest,
            mutation_kind=proposal.mutation_kind,
            mutation_engine_version=proposal.mutation_engine_version,
        )
        if expected != proposal.proposal_digest:
            raise ProposalIntegrityViolationError()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
