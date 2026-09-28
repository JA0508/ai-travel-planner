from __future__ import annotations

from typing import Any, Protocol

from .models import (
    CandidateEvidenceLinkRecord,
    CandidateDecisionResult,
    CandidateRegistrationResult,
    CreateRevisionResult,
    DraftIntentRevisionRecord,
    DraftIntentEditResult,
    PrePlanHandoffRunRecord,
    TripAggregate,
    TripCandidateDecisionRecord,
    TripCandidateRecord,
    TripMutationProposalRecord,
    PlannerHandoffRunRecord,
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
        direct_user_text: str,
        source_digest: str,
        operation_type: str,
        operation_summary: str,
        request_digest: str,
        planner_run_id: str | None,
        planner_version: str | None,
        trace_schema_version: str | None,
        trace_digest: str | None,
    ) -> TripAggregate:
        ...

    def create_draft_trip(
        self,
        *,
        capability_hash: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> tuple[TripRecord, bool]:
        ...

    def get_draft_trip_by_creation_idempotency(self, *, idempotency_key_hash: str) -> TripRecord | None:
        ...

    def get_draft_source_text(self, *, trip_id: str) -> str:
        ...

    def create_draft_intent_revision(
        self,
        *,
        revision: DraftIntentRevisionRecord,
        request_digest: str,
        idempotency_key_hash: str,
        expected_parent_draft_intent_revision_id: str | None,
    ) -> tuple[DraftIntentRevisionRecord, bool]:
        ...

    def get_draft_intent_revision_by_idempotency(
        self,
        *,
        trip_id: str,
        request_digest: str,
        idempotency_key_hash: str,
    ) -> DraftIntentRevisionRecord | None:
        ...

    def edit_draft_intent_revision(
        self,
        *,
        revision: DraftIntentRevisionRecord,
        request_digest: str,
        idempotency_key_hash: str,
        expected_parent_draft_intent_revision_id: str,
        expected_draft_version: int,
        operation: str,
    ) -> DraftIntentEditResult:
        ...

    def get_draft_intent_revision(self, *, trip_id: str, revision_id: str) -> DraftIntentRevisionRecord:
        ...

    def get_latest_draft_intent_revision(self, *, trip_id: str) -> DraftIntentRevisionRecord | None:
        ...

    def list_draft_intent_revisions(self, *, trip_id: str) -> list[DraftIntentRevisionRecord]:
        ...

    def create_preplan_handoff_run(self, *, run: PrePlanHandoffRunRecord) -> PrePlanHandoffRunRecord:
        ...

    def get_preplan_handoff_run(self, *, trip_id: str, run_id: str) -> PrePlanHandoffRunRecord:
        ...

    def activate_preplan_handoff(
        self,
        *,
        trip_id: str,
        capability_hash: str,
        run_id: str,
        draft_intent_revision_id: str,
        handoff_digest: str,
        now: str,
        request_digest: str,
        idempotency_key_hash: str,
        operation_metadata: dict[str, Any],
    ) -> CreateRevisionResult:
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
        evidence_links: list[CandidateEvidenceLinkRecord] | None = None,
    ) -> CandidateRegistrationResult:
        ...

    def list_candidate_evidence_links(
        self,
        *,
        trip_id: str,
        candidate_id: str,
    ) -> list[CandidateEvidenceLinkRecord]:
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

    def create_planner_handoff_preview(
        self,
        *,
        run: PlannerHandoffRunRecord,
        proposal: TripMutationProposalRecord,
    ) -> tuple[PlannerHandoffRunRecord, TripMutationProposalRecord]:
        ...

    def get_planner_handoff_run(
        self,
        *,
        trip_id: str,
        run_id: str,
    ) -> PlannerHandoffRunRecord:
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
        expected_intent_revision_id: str | None = None,
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
