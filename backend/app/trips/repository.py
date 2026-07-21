from __future__ import annotations

from typing import Any, Protocol

from .models import (
    CandidateDecisionResult,
    CandidateRegistrationResult,
    CreateRevisionResult,
    TripAggregate,
    TripCandidateDecisionRecord,
    TripCandidateRecord,
    TripMutationProposalRecord,
    TripRecord,
    TripRevisionRecord,
)
from .intent_contracts import CreateIntentRevisionResult, IntentCompileRunDraft, TripIntentRevisionRecord


class TripRepository(Protocol):
    def health_check(self) -> dict[str, Any]:
        ...

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
        ...

    def get_trip(self, trip_id: str) -> TripRecord:
        ...

    def get_trip_for_access(self, trip_id: str, capability_hash: str) -> TripRecord:
        ...

    def get_current_revision(self, trip_id: str) -> TripRevisionRecord:
        ...

    def get_revision(self, trip_id: str, revision_id: str) -> TripRevisionRecord:
        ...

    def list_revisions(self, trip_id: str) -> list[TripRevisionRecord]:
        ...

    def create_intent_revision(
        self,
        *,
        revision: TripIntentRevisionRecord,
        compile_run: IntentCompileRunDraft | None = None,
        operation: str = "compile_trip_intent_envelope",
        restore_source_revision_id: str | None = None,
        request_digest: str,
        idempotency_key_hash: str,
        expected_parent_intent_revision_id: str | None = None,
        require_latest_parent: bool = False,
        expected_base_revision_id: str | None = None,
    ) -> CreateIntentRevisionResult:
        ...

    def get_intent_revision_by_idempotency(
        self,
        *,
        trip_id: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> CreateIntentRevisionResult | None:
        ...

    def list_intent_revisions(self, *, trip_id: str) -> list[TripIntentRevisionRecord]:
        ...

    def get_latest_intent_revision(self, *, trip_id: str) -> TripIntentRevisionRecord | None:
        ...

    def get_intent_revision(self, *, trip_id: str, revision_id: str) -> TripIntentRevisionRecord:
        ...

    def create_candidate(
        self,
        *,
        candidate: TripCandidateRecord,
        decision: TripCandidateDecisionRecord,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> CandidateRegistrationResult:
        ...

    def get_candidate(self, *, trip_id: str, candidate_id: str) -> TripCandidateRecord:
        ...

    def list_candidates(self, *, trip_id: str) -> list[TripCandidateRecord]:
        ...

    def list_candidate_decisions(
        self,
        *,
        trip_id: str,
        candidate_id: str | None = None,
    ) -> list[TripCandidateDecisionRecord]:
        ...

    def create_candidate_decision(
        self,
        *,
        decision: TripCandidateDecisionRecord,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> CandidateDecisionResult:
        ...

    def get_idempotent_revision(
        self,
        *,
        trip_id: str,
        capability_hash: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> CreateRevisionResult | None:
        ...

    def create_mutation_proposal(
        self,
        *,
        proposal: TripMutationProposalRecord,
    ) -> TripMutationProposalRecord:
        ...

    def get_mutation_proposal(
        self,
        *,
        trip_id: str,
        proposal_id: str,
    ) -> TripMutationProposalRecord:
        ...

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
        ...

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
        ...
