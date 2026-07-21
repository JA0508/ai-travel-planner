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
from app.trips.intent_contracts import CreateIntentRevisionResult, TripIntentRevisionRecord
from app.trips.errors import (
    CandidateNotFoundError,
    IdempotencyConflictError,
    MutationProposalCancelledError,
    MutationProposalExpiredError,
    MutationProposalInvalidatedError,
    MutationProposalNotFoundError,
    ProposalDigestMismatchError,
    ProposalIntegrityViolationError,
    RevisionNotFoundError,
    StaleBaseRevisionError,
    StaleIntentRevisionError,
    StaleMutationProposalError,
    TripAccessDeniedError,
    TripNotFoundError,
)
from app.trips.models import (
    CandidateDecisionResult,
    CandidateRegistrationResult,
    CreateRevisionResult,
    ProposalStatus,
    RevisionOperationRecord,
    RevisionSourceType,
    TripCandidateDecisionRecord,
    TripCandidateRecord,
    TripAggregate,
    TripLifecycleStatus,
    TripMutationProposalRecord,
    TripRecord,
    TripRevisionRecord,
)
from app.trips.candidates import generate_candidate_decision_id


class MemoryTripRepository:
    def __init__(self) -> None:
        self.trips: dict[str, TripRecord] = {}
        self.revisions: dict[str, TripRevisionRecord] = {}
        self.operations: dict[str, RevisionOperationRecord] = {}
        self.idempotency_records: dict[tuple[str, str], tuple[str, str]] = {}
        self.proposals: dict[str, TripMutationProposalRecord] = {}
        self.candidates: dict[str, TripCandidateRecord] = {}
        self.candidate_decisions: dict[str, TripCandidateDecisionRecord] = {}
        self.candidate_idempotency_records: dict[tuple[str, str], tuple[str, str, str | None]] = {}
        self.intent_revisions: dict[str, TripIntentRevisionRecord] = {}
        self.intent_idempotency_records: dict[tuple[str, str], tuple[str, str]] = {}

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

    def create_intent_revision(
        self,
        *,
        revision: TripIntentRevisionRecord,
        request_digest: str,
        idempotency_key_hash: str,
        expected_parent_intent_revision_id: str | None = None,
        require_latest_parent: bool = False,
        expected_base_revision_id: str | None = None,
    ) -> CreateIntentRevisionResult:
        trip = self.get_trip(revision.trip_id)
        if expected_base_revision_id is not None and trip.current_revision_id != expected_base_revision_id:
            raise StaleBaseRevisionError(
                trip_id=revision.trip_id,
                provided_base_revision_id=expected_base_revision_id,
                current_revision_id=trip.current_revision_id,
            )
        self.get_revision(revision.trip_id, revision.base_trip_revision_id)
        key = (revision.trip_id, idempotency_key_hash)
        existing = self.intent_idempotency_records.get(key)
        if existing is not None:
            stored_digest, revision_id = existing
            if stored_digest != request_digest:
                raise IdempotencyConflictError()
            return CreateIntentRevisionResult(
                revision=copy.deepcopy(self.intent_revisions[revision_id]),
                idempotent_replay=True,
            )
        if require_latest_parent:
            latest = self.get_latest_intent_revision(trip_id=revision.trip_id)
            latest_id = latest.id if latest is not None else None
            if latest_id != expected_parent_intent_revision_id:
                raise StaleIntentRevisionError(
                    trip_id=revision.trip_id,
                    provided_intent_revision_id=expected_parent_intent_revision_id or "",
                    current_intent_revision_id=latest_id or "",
                )
            expected_revision_number = 1 if latest is None else latest.revision_number + 1
            if revision.revision_number != expected_revision_number:
                raise StaleIntentRevisionError(
                    trip_id=revision.trip_id,
                    provided_intent_revision_id=expected_parent_intent_revision_id or "",
                    current_intent_revision_id=latest_id or "",
                )
        self.intent_revisions[revision.id] = copy.deepcopy(revision)
        self.intent_idempotency_records[key] = (request_digest, revision.id)
        return CreateIntentRevisionResult(revision=copy.deepcopy(revision))

    def get_intent_revision_by_idempotency(
        self,
        *,
        trip_id: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> CreateIntentRevisionResult | None:
        existing = self.intent_idempotency_records.get((trip_id, idempotency_key_hash))
        if existing is None:
            return None
        stored_digest, revision_id = existing
        if stored_digest != request_digest:
            raise IdempotencyConflictError()
        return CreateIntentRevisionResult(
            revision=copy.deepcopy(self.intent_revisions[revision_id]),
            idempotent_replay=True,
        )

    def list_intent_revisions(self, *, trip_id: str) -> list[TripIntentRevisionRecord]:
        return sorted(
            [
                copy.deepcopy(revision)
                for revision in self.intent_revisions.values()
                if revision.trip_id == trip_id
            ],
            key=lambda revision: revision.revision_number,
            reverse=True,
        )

    def get_latest_intent_revision(self, *, trip_id: str) -> TripIntentRevisionRecord | None:
        revisions = self.list_intent_revisions(trip_id=trip_id)
        return revisions[0] if revisions else None

    def get_intent_revision(self, *, trip_id: str, revision_id: str) -> TripIntentRevisionRecord:
        revision = self.intent_revisions.get(revision_id)
        if revision is None or revision.trip_id != trip_id:
            raise RevisionNotFoundError(revision_id)
        return copy.deepcopy(revision)

    def create_candidate(
        self,
        *,
        candidate: TripCandidateRecord,
        decision: TripCandidateDecisionRecord,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> CandidateRegistrationResult:
        key = (candidate.trip_id, idempotency_key_hash)
        existing_idempotency = self.candidate_idempotency_records.get(key)
        if existing_idempotency is not None:
            stored_digest, candidate_id, decision_id = existing_idempotency
            if stored_digest != request_digest:
                raise IdempotencyConflictError()
            return CandidateRegistrationResult(
                candidate=self.get_candidate(trip_id=candidate.trip_id, candidate_id=candidate_id),
                decision=(
                    copy.deepcopy(self.candidate_decisions[decision_id])
                    if decision_id
                    else None
                ),
                idempotent_replay=True,
            )
        duplicate = next(
            (
                stored
                for stored in self.candidates.values()
                if stored.trip_id == candidate.trip_id
                and stored.content_digest == candidate.content_digest
            ),
            None,
        )
        if duplicate is not None:
            self.candidate_idempotency_records[key] = (request_digest, duplicate.id, None)
            return CandidateRegistrationResult(candidate=copy.deepcopy(duplicate), deduplicated=True)
        self.candidates[candidate.id] = copy.deepcopy(candidate)
        self.candidate_decisions[decision.id] = copy.deepcopy(decision)
        self.candidate_idempotency_records[key] = (request_digest, candidate.id, decision.id)
        return CandidateRegistrationResult(candidate=copy.deepcopy(candidate), decision=copy.deepcopy(decision))

    def get_candidate(self, *, trip_id: str, candidate_id: str) -> TripCandidateRecord:
        candidate = self.candidates.get(candidate_id)
        if candidate is None or candidate.trip_id != trip_id:
            raise CandidateNotFoundError(candidate_id)
        return copy.deepcopy(candidate)

    def list_candidates(self, *, trip_id: str) -> list[TripCandidateRecord]:
        return sorted(
            [copy.deepcopy(candidate) for candidate in self.candidates.values() if candidate.trip_id == trip_id],
            key=lambda candidate: (candidate.created_at, candidate.id),
        )

    def list_candidate_decisions(
        self,
        *,
        trip_id: str,
        candidate_id: str | None = None,
    ) -> list[TripCandidateDecisionRecord]:
        return sorted(
            [
                copy.deepcopy(decision)
                for decision in self.candidate_decisions.values()
                if decision.trip_id == trip_id
                and (candidate_id is None or decision.candidate_id == candidate_id)
            ],
            key=lambda decision: (decision.created_at, decision.id),
        )

    def create_candidate_decision(
        self,
        *,
        decision: TripCandidateDecisionRecord,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> CandidateDecisionResult:
        key = (decision.trip_id, idempotency_key_hash)
        existing = self.candidate_idempotency_records.get(key)
        if existing is not None:
            stored_digest, candidate_id, decision_id = existing
            if stored_digest != request_digest:
                raise IdempotencyConflictError()
            if decision_id is None:
                raise CandidateNotFoundError(candidate_id)
            return CandidateDecisionResult(
                candidate=self.get_candidate(trip_id=decision.trip_id, candidate_id=candidate_id),
                decision=copy.deepcopy(self.candidate_decisions[decision_id]),
                idempotent_replay=True,
            )
        candidate = self.get_candidate(trip_id=decision.trip_id, candidate_id=decision.candidate_id)
        self.candidate_decisions[decision.id] = copy.deepcopy(decision)
        self.candidate_idempotency_records[key] = (request_digest, candidate.id, decision.id)
        return CandidateDecisionResult(candidate=candidate, decision=copy.deepcopy(decision))

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
        candidate_admission = operation_metadata.get("candidate_admission")
        if isinstance(candidate_admission, dict):
            candidate_id = str(candidate_admission.get("candidate_id") or "")
            if candidate_id:
                self.get_candidate(trip_id=trip_id, candidate_id=candidate_id)
                decision = TripCandidateDecisionRecord(
                    id=generate_candidate_decision_id(),
                    trip_id=trip_id,
                    candidate_id=candidate_id,
                    decision_type="scheduled",
                    reason_code="SCHEDULED_IN_REVISION",
                    base_revision_id=base_revision_id,
                    related_revision_id=revision_id,
                    source="mutation_apply",
                    created_at=now,
                )
                self.candidate_decisions[decision.id] = decision
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
