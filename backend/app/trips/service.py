from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.api.routes.itinerary import (
    build_itinerary_request_from_parsed_intent,
    build_itinerary_response,
    build_planner_input_snapshot,
    build_planner_result_summary,
    build_replan_request,
    execute_completion_task_action,
    infer_travel_mode_from_text,
    require_trip_intent_envelope,
    resolve_replan_base_intent,
)
from app.planner.trace import PlannerTrace, PlannerTraceCollector, planner_trace_digest
from app.core.runtime_config import get_trip_replan_proposal_ttl_seconds
from app.evaluation.invariants import (
    missing_route_not_zero,
    no_duplicate_scheduled_place,
    no_schedule_overlap,
    within_arrival_departure_boundaries,
    within_day_availability,
)
from app.schemas import (
    CompletionTaskActionRequest,
    CompletionTaskActionResponse,
    ItineraryResponse,
    ReplanItineraryRequest,
    ReplanItineraryResponse,
    TripIntentEnvelopeSource,
)
from app.services.intent_disambiguation import disambiguate_trip_intent
from app.services.nl_parser import normalize_parsed_trip_intent, parse_trip_text
from app.services.planning_state_transformer import build_planning_input_state
from .access import (
    generate_capability,
    generate_proposal_id,
    hash_capability,
    hash_idempotency_key,
    verify_capability,
)
from .candidates import (
    CandidateDecisionReasonCode,
    CandidateDecisionType,
    TripCandidateCreateRequest,
    TripCandidateDecisionRecord,
    TripCandidateDecisionRequest,
    TripCandidateDecisionResponse,
    TripCandidateListResponse,
    TripCandidateRegistrationResponse,
    build_candidate_record,
    candidate_to_response,
    generate_candidate_decision_id,
    infer_workflow_state,
)
from .digests import (
    TRIP_MUTATION_COMMAND_SCHEMA_VERSION,
    TRIP_MUTATION_ENGINE_VERSION,
    TRIP_MUTATION_PROPOSAL_SCHEMA_VERSION,
    TRIP_SNAPSHOT_SCHEMA_VERSION,
    canonical_json,
    itinerary_content_digest,
    mutation_proposal_digest,
    request_digest,
)
from .errors import (
    InvalidRevisionOperationError,
    PreviewApplyMismatchError,
    ProposalDigestMismatchError,
    ProposalIntegrityViolationError,
    RevisionNotUndoableError,
    SnapshotSchemaUnsupportedError,
    StaleBaseRevisionError,
    StaleMutationProposalError,
    TripAccessDeniedError,
    UndoTargetNotCurrentError,
)
from .intent_contracts import (
    AnswerIntentClarificationRequest,
    CompileTripIntentRequest,
    CompileTripIntentResponse,
    EditTripIntentEnvelopeRequest,
    SourceLinkedTripIntentEnvelope,
    TRIP_INTENT_COMPILER_VERSION,
    TRIP_INTENT_ENVELOPE_SCHEMA_VERSION,
    TripIntentRevisionDetailResponse,
    TripIntentRevisionListResponse,
    TripIntentRevisionRecord,
    compile_source_linked_intent,
    intent_revision_metadata,
)
from .intent_llm_adapter import build_untrusted_llm_intent_proposal
from .models import ProposalStatus, RevisionSourceType, TripCandidateRecord, TripMutationProposalRecord
from .mutation_commands import TripMutationCommandEnvelope, TripMutationEngine, ensure_stable_item_ids
from .repository import TripRepository
from .schemas import (
    ApplyPersistedMutationProposalRequest,
    ApplyPersistedReplanProposalRequest,
    MutationProposalMetadata,
    PersistedCompletionTaskActionRequest,
    PersistedCompletionTaskActionResponse,
    PersistedMutationApplyResponse,
    PersistedMutationPreviewRequest,
    PersistedMutationPreviewResponse,
    PersistedReplanRequest,
    PersistedReplanPreviewResponse,
    PersistedReplanResponse,
    RestoreRevisionResponse,
    TripCurrentResponse,
    TripMetadata,
    TripPersistenceInfo,
    TripPlanRequest,
    TripPlanResponse,
    TripRevisionDetailResponse,
    TripRevisionListResponse,
    TripRevisionMetadata,
    UndoPersistedMutationResponse,
)


class CreatedTripResult:
    def __init__(self, *, response: TripPlanResponse, capability: str) -> None:
        self.response = response
        self.capability = capability


class TripPersistenceService:
    def __init__(self, repository: TripRepository, *, clock=None) -> None:
        self.repository = repository
        self.clock = clock or utc_now_datetime

    def create_persisted_plan(self, payload: TripPlanRequest) -> CreatedTripResult:
        capability = generate_capability()
        capability_hash = hash_capability(capability)
        if payload.text:
            planned = self._plan_from_text(payload)
            itinerary = planned["itinerary"]
            operation_type = "plan_trip_from_text"
            operation_summary = "Created initial trip revision from natural-language planning."
        else:
            planned = self._plan_from_itinerary_request(payload)
            itinerary = planned["itinerary"]
            operation_type = "generate_itinerary"
            operation_summary = "Created initial trip revision from structured itinerary request."

        trace = planned["trace"]
        stored_snapshot = ensure_stable_item_ids(serialize_itinerary_snapshot(itinerary))
        stored_itinerary = deserialize_itinerary_snapshot(stored_snapshot)
        aggregate = self.repository.create_trip_with_initial_revision(
            itinerary_snapshot=stored_snapshot,
            capability_hash=capability_hash,
            operation_type=operation_type,
            operation_summary=operation_summary,
            request_digest=request_digest(redacted_plan_request_payload(payload)),
            planner_run_id=trace.planner_run_id,
            planner_version=trace.planner_version,
            trace_schema_version=trace.schema_version,
            trace_digest=trace.trace_digest,
        )
        response = TripPlanResponse(
            trip=TripMetadata.from_record(aggregate.trip),
            current_revision=TripRevisionMetadata.from_record(aggregate.current_revision),
            itinerary=stored_itinerary,
            trip_intent=planned.get("trip_intent"),
            parsed_intent=planned.get("parsed_intent"),
            planning_state=planned.get("planning_state"),
            persistence=TripPersistenceInfo(),
        )
        return CreatedTripResult(response=response, capability=capability)

    def get_current_trip(self, trip_id: str, capability: str | None) -> TripCurrentResponse:
        trip = self._require_trip_access(trip_id, capability)
        revision = self.repository.get_revision(trip_id, trip.current_revision_id)
        return TripCurrentResponse(
            trip=TripMetadata.from_record(trip),
            current_revision=TripRevisionMetadata.from_record(revision),
            itinerary=deserialize_itinerary_snapshot(revision.itinerary_snapshot),
            persistence=TripPersistenceInfo(),
        )

    def list_revisions(self, trip_id: str, capability: str | None) -> TripRevisionListResponse:
        trip = self._require_trip_access(trip_id, capability)
        return TripRevisionListResponse(
            trip=TripMetadata.from_record(trip),
            revisions=[
                TripRevisionMetadata.from_record(revision)
                for revision in self.repository.list_revisions(trip_id)
            ],
        )

    def get_revision_detail(
        self,
        trip_id: str,
        revision_id: str,
        capability: str | None,
    ) -> TripRevisionDetailResponse:
        trip = self._require_trip_access(trip_id, capability)
        revision = self.repository.get_revision(trip_id, revision_id)
        return TripRevisionDetailResponse(
            trip=TripMetadata.from_record(trip),
            revision=TripRevisionMetadata.from_record(revision),
            itinerary=deserialize_itinerary_snapshot(revision.itinerary_snapshot),
        )

    def register_candidate(
        self,
        *,
        trip_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: TripCandidateCreateRequest,
    ) -> TripCandidateRegistrationResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        now = format_utc(self.clock())
        candidate = build_candidate_record(trip_id=trip_id, payload=payload, now=now)
        decision = TripCandidateDecisionRecord(
            id=generate_candidate_decision_id(),
            trip_id=trip_id,
            candidate_id=candidate.id,
            decision_type=CandidateDecisionType.PENDING.value,
            reason_code=CandidateDecisionReasonCode.CANDIDATE_REGISTERED.value,
            base_revision_id=trip.current_revision_id,
            related_revision_id=None,
            source="candidate_registration",
            created_at=now,
        )
        req_digest = request_digest(
            {
                "operation": "register_candidate",
                "trip_id": trip_id,
                "candidate_content_digest": candidate.content_digest,
                "source_kind": candidate.source_kind,
            }
        )
        result = self.repository.create_candidate(
            candidate=candidate,
            decision=decision,
            request_digest=req_digest,
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
        )
        decisions = self.repository.list_candidate_decisions(
            trip_id=trip_id,
            candidate_id=result.candidate.id,
        )
        state, latest_id = infer_workflow_state(decisions)
        return TripCandidateRegistrationResponse(
            candidate=candidate_to_response(result.candidate, workflow_state=state, latest_decision_id=latest_id),
            deduplicated=result.deduplicated,
            idempotent_replay=result.idempotent_replay,
        )

    def list_candidates(
        self,
        *,
        trip_id: str,
        capability: str | None,
        state: str | None = None,
    ) -> TripCandidateListResponse:
        self._require_trip_access(trip_id, capability)
        decisions_by_candidate: dict[str, list[TripCandidateDecisionRecord]] = {}
        for decision in self.repository.list_candidate_decisions(trip_id=trip_id):
            decisions_by_candidate.setdefault(decision.candidate_id, []).append(decision)
        candidates = []
        for candidate in self.repository.list_candidates(trip_id=trip_id):
            workflow_state, latest_id = infer_workflow_state(decisions_by_candidate.get(candidate.id, []))
            if state and workflow_state != state:
                continue
            candidates.append(candidate_to_response(candidate, workflow_state=workflow_state, latest_decision_id=latest_id))
        return TripCandidateListResponse(candidates=candidates)

    def compile_intent_envelope(
        self,
        *,
        trip_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: CompileTripIntentRequest,
    ) -> CompileTripIntentResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        current_revision = self.repository.get_revision(trip_id, trip.current_revision_id)
        if current_revision.id != payload.base_revision_id:
            raise StaleBaseRevisionError(
                trip_id=trip_id,
                provided_base_revision_id=payload.base_revision_id,
                current_revision_id=current_revision.id,
            )
        if payload.use_llm_proposal_adapter and payload.llm_proposal is None and payload.direct_user_text:
            payload = payload.model_copy(
                update={
                    "llm_proposal": build_untrusted_llm_intent_proposal(payload.direct_user_text)
                }
            )
        return self._create_intent_revision_from_request(
            trip_id=trip_id,
            current_revision=current_revision,
            parent_intent_revision=None,
            parent_intent_snapshot=None,
            payload=payload,
            idempotency_key=idempotency_key,
            operation="compile_trip_intent_envelope",
        )

    def get_intent_envelope_detail(
        self,
        *,
        trip_id: str,
        capability: str | None,
        revision_id: str,
    ) -> TripIntentRevisionDetailResponse:
        self._require_trip_access(trip_id, capability)
        revision = self.repository.get_intent_revision(trip_id=trip_id, revision_id=revision_id)
        return TripIntentRevisionDetailResponse(
            envelope=SourceLinkedTripIntentEnvelope.model_validate(revision.envelope),
            revision=intent_revision_metadata(revision),
        )

    def edit_intent_envelope(
        self,
        *,
        trip_id: str,
        capability: str | None,
        revision_id: str,
        idempotency_key: str | None,
        payload: EditTripIntentEnvelopeRequest,
    ) -> CompileTripIntentResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        current_revision = self.repository.get_revision(trip_id, trip.current_revision_id)
        if current_revision.id != payload.base_revision_id:
            raise StaleBaseRevisionError(
                trip_id=trip_id,
                provided_base_revision_id=payload.base_revision_id,
                current_revision_id=current_revision.id,
            )
        parent = self.repository.get_intent_revision(trip_id=trip_id, revision_id=revision_id)
        request = CompileTripIntentRequest(
            base_revision_id=payload.base_revision_id,
            structured_overrides=payload.field_updates,
        )
        return self._create_intent_revision_from_request(
            trip_id=trip_id,
            current_revision=current_revision,
            parent_intent_revision=parent,
            parent_intent_snapshot=parent.envelope,
            payload=request,
            idempotency_key=idempotency_key,
            operation="edit_trip_intent_envelope",
        )

    def answer_intent_clarification(
        self,
        *,
        trip_id: str,
        capability: str | None,
        revision_id: str,
        question_id: str,
        idempotency_key: str | None,
        payload: AnswerIntentClarificationRequest,
    ) -> CompileTripIntentResponse:
        if question_id != "clarify_trip_city":
            raise InvalidRevisionOperationError("Unsupported clarification question.")
        answer = str(payload.answer).strip() if payload.answer is not None else ""
        if not answer:
            raise InvalidRevisionOperationError("Clarification answer is required.")
        return self.edit_intent_envelope(
            trip_id=trip_id,
            capability=capability,
            revision_id=revision_id,
            idempotency_key=idempotency_key,
            payload=EditTripIntentEnvelopeRequest(
                base_revision_id=payload.base_revision_id,
                field_updates={"city": answer},  # type: ignore[arg-type]
            ),
        )

    def _create_intent_revision_from_request(
        self,
        *,
        trip_id: str,
        current_revision,
        parent_intent_revision: TripIntentRevisionRecord | None,
        parent_intent_snapshot: dict[str, Any] | None,
        payload: CompileTripIntentRequest,
        idempotency_key: str,
        operation: str,
    ) -> CompileTripIntentResponse:
        candidates, candidate_workflow_states = self._intent_candidate_context(trip_id, payload)
        latest_for_number = parent_intent_revision or self.repository.get_latest_intent_revision(trip_id=trip_id)
        next_revision_number = 1 if latest_for_number is None else latest_for_number.revision_number + 1
        now = format_utc(self.clock())
        envelope = compile_source_linked_intent(
            trip_id=trip_id,
            base_revision_id=current_revision.id,
            parent_intent_revision_id=parent_intent_revision.id if parent_intent_revision else None,
            next_revision_number=next_revision_number,
            created_at=now,
            request=payload,
            existing_trip_snapshot=current_revision.itinerary_snapshot,
            parent_intent_snapshot=parent_intent_snapshot,
            candidates=candidates,
            candidate_workflow_states=candidate_workflow_states,
        )
        req_digest = request_digest(
            {
                "operation": operation,
                "trip_id": trip_id,
                "base_revision_id": current_revision.id,
                "parent_intent_revision_id": parent_intent_revision.id if parent_intent_revision else None,
                "payload": payload.model_dump(mode="json"),
            }
        )
        record = TripIntentRevisionRecord(
            id=envelope.id,
            trip_id=trip_id,
            revision_number=envelope.revision_number,
            parent_intent_revision_id=envelope.parent_intent_revision_id,
            base_trip_revision_id=current_revision.id,
            envelope_schema_version=TRIP_INTENT_ENVELOPE_SCHEMA_VERSION,
            envelope=envelope.model_dump(mode="json"),
            content_digest=envelope.content_digest,
            compiler_version=TRIP_INTENT_COMPILER_VERSION,
            source_digest=envelope.source_digest,
            validation_report=envelope.validation_report,
            created_at=now,
        )
        result = self.repository.create_intent_revision(
            revision=record,
            request_digest=req_digest,
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
        )
        stored_envelope = SourceLinkedTripIntentEnvelope.model_validate(result.revision.envelope)
        return CompileTripIntentResponse(
            envelope=stored_envelope,
            revision=intent_revision_metadata(result.revision),
            idempotent_replay=result.idempotent_replay,
        )

    def list_intent_envelopes(
        self,
        *,
        trip_id: str,
        capability: str | None,
    ) -> TripIntentRevisionListResponse:
        self._require_trip_access(trip_id, capability)
        return TripIntentRevisionListResponse(
            revisions=[
                intent_revision_metadata(revision)
                for revision in self.repository.list_intent_revisions(trip_id=trip_id)
            ]
        )

    def record_candidate_decision(
        self,
        *,
        trip_id: str,
        candidate_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: TripCandidateDecisionRequest,
    ) -> TripCandidateDecisionResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        self._require_trip_access(trip_id, capability)
        if payload.decision == CandidateDecisionType.SCHEDULED:
            raise InvalidRevisionOperationError("scheduled decisions are created by mutation apply.")
        candidate = self.repository.get_candidate(trip_id=trip_id, candidate_id=candidate_id)
        now = format_utc(self.clock())
        decision = TripCandidateDecisionRecord(
            id=generate_candidate_decision_id(),
            trip_id=trip_id,
            candidate_id=candidate_id,
            decision_type=payload.decision.value,
            reason_code=payload.reason_code.value,
            base_revision_id=payload.base_revision_id,
            related_revision_id=None,
            source="user_decision",
            created_at=now,
        )
        req_digest = request_digest(
            {
                "operation": "candidate_decision",
                "candidate_id": candidate_id,
                "decision": payload.decision.value,
                "reason_code": payload.reason_code.value,
                "base_revision_id": payload.base_revision_id,
            }
        )
        result = self.repository.create_candidate_decision(
            decision=decision,
            request_digest=req_digest,
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
        )
        decisions = self.repository.list_candidate_decisions(trip_id=trip_id, candidate_id=candidate.id)
        state, latest_id = infer_workflow_state(decisions)
        return TripCandidateDecisionResponse(
            decision={
                "id": result.decision.id,
                "candidate_id": result.decision.candidate_id,
                "decision_type": result.decision.decision_type,
                "reason_code": result.decision.reason_code,
                "base_revision_id": result.decision.base_revision_id,
                "related_revision_id": result.decision.related_revision_id,
                "source": result.decision.source,
                "created_at": result.decision.created_at,
            },
            candidate=candidate_to_response(result.candidate, workflow_state=state, latest_decision_id=latest_id),
            idempotent_replay=result.idempotent_replay,
        )

    def apply_completion_task(
        self,
        *,
        trip_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: PersistedCompletionTaskActionRequest,
    ) -> PersistedCompletionTaskActionResponse:
        if not idempotency_key or not idempotency_key.strip():
            from .errors import InvalidRevisionOperationError

            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        base_revision = self.repository.get_revision(trip_id, payload.base_revision_id)
        base_itinerary = deserialize_itinerary_snapshot(base_revision.itinerary_snapshot)
        action_request = CompletionTaskActionRequest.model_validate(
            {
                "itinerary": base_itinerary.model_dump(mode="json"),
                "task_id": payload.task_id,
                "task_instance_key": payload.task_instance_key,
                "day": payload.day,
                "block_type": payload.block_type,
                "selected_candidate": payload.selected_candidate,
                "completion_candidate_history": payload.completion_candidate_history,
            }
        )
        task_result = execute_completion_task_action(action_request)
        next_snapshot = ensure_stable_item_ids(serialize_itinerary_snapshot(task_result.itinerary))
        next_itinerary = deserialize_itinerary_snapshot(next_snapshot)
        req_digest = request_digest(
            {
                "operation": "completion_task",
                "base_revision_id": payload.base_revision_id,
                "task_id": payload.task_id,
                "task_instance_key": payload.task_instance_key,
                "day": payload.day,
                "block_type": payload.block_type,
                "selected_candidate": payload.selected_candidate,
                "completion_candidate_history": payload.completion_candidate_history,
            }
        )
        result = self.repository.create_revision(
            trip_id=trip_id,
            capability_hash=trip.capability_hash,
            base_revision_id=payload.base_revision_id,
            itinerary_snapshot=next_snapshot,
            source_type=RevisionSourceType.COMPLETION_PATCH.value,
            operation_type="apply_completion_task",
            operation_summary=task_result.summary,
            operation_metadata={
                "operation_type": "apply_completion_task",
                "task_id": payload.task_id,
                "task_instance_key": payload.task_instance_key,
                "applied": task_result.applied,
                "inserted_item_name": task_result.inserted_item.name if task_result.inserted_item else None,
            },
            request_digest=req_digest,
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
        )
        current_trip = self.repository.get_trip(trip_id)
        revision = result.revision
        if result.idempotent_replay:
            task_response = CompletionTaskActionResponse(
                task_id=payload.task_id,
                applied=True,
                summary="Idempotent retry returned the previously created revision.",
                inserted_item=None,
                itinerary=deserialize_itinerary_snapshot(revision.itinerary_snapshot),
            )
        else:
            task_response = CompletionTaskActionResponse(
                task_id=task_result.task_id,
                applied=task_result.applied,
                summary=task_result.summary,
                inserted_item=task_result.inserted_item,
                itinerary=next_itinerary,
            )
        return PersistedCompletionTaskActionResponse(
            trip=TripMetadata.from_record(current_trip),
            current_revision=TripRevisionMetadata.from_record(revision),
            task_result=task_response,
            persistence=TripPersistenceInfo(idempotent_replay=result.idempotent_replay),
        )

    def preview_replan(
        self,
        *,
        trip_id: str,
        capability: str | None,
        payload: PersistedReplanRequest,
    ) -> PersistedReplanPreviewResponse:
        trip = self._require_trip_access(trip_id, capability)
        base_revision = self.repository.get_revision(trip_id, payload.base_revision_id)
        if trip.current_revision_id != payload.base_revision_id:
            raise StaleMutationProposalError(
                trip_id=trip_id,
                proposal_id="pending",
                base_revision_id=payload.base_revision_id,
                current_revision_id=trip.current_revision_id,
            )
        base_itinerary = deserialize_itinerary_snapshot(base_revision.itinerary_snapshot)
        replan_result, trace = execute_replan_from_itinerary(
            base_itinerary=base_itinerary,
            follow_up_text=payload.follow_up_text,
            auto_fill_sparse_days=payload.auto_fill_sparse_days,
        )
        req_digest = request_digest(build_replan_request_digest_payload(payload))
        snapshot = ensure_stable_item_ids(sanitize_replan_preview_snapshot(
            serialize_itinerary_snapshot(replan_result.itinerary)
        ))
        stored_itinerary = deserialize_itinerary_snapshot(snapshot)
        preview_content_digest = itinerary_content_digest(snapshot)
        validation_report = build_mutation_validation_report(
            itinerary=stored_itinerary,
            trace=trace,
        )
        assert_mutation_validation_passed(validation_report)
        now = self.clock()
        expires_at = format_utc(now + timedelta(seconds=get_trip_replan_proposal_ttl_seconds()))
        proposal_digest = mutation_proposal_digest(
            proposal_schema_version=TRIP_MUTATION_PROPOSAL_SCHEMA_VERSION,
            trip_id=trip_id,
            base_revision_id=payload.base_revision_id,
            source_type=RevisionSourceType.REPLAN_PATCH.value,
            operation_type="apply_replan_follow_up",
            request_digest=req_digest,
            preview_snapshot_schema_version=TRIP_SNAPSHOT_SCHEMA_VERSION,
            preview_content_digest=preview_content_digest,
            planner_run_id=trace.planner_run_id,
            planner_version=trace.planner_version,
            trace_schema_version=trace.schema_version,
            trace_digest=trace.trace_digest,
            validation_report=validation_report,
            expires_at=expires_at,
            execution_kind="replan_snapshot",
        )
        proposal = self.repository.create_mutation_proposal(
            proposal=TripMutationProposalRecord(
                id=generate_proposal_id(),
                trip_id=trip_id,
                base_revision_id=payload.base_revision_id,
                proposal_schema_version=TRIP_MUTATION_PROPOSAL_SCHEMA_VERSION,
                source_type=RevisionSourceType.REPLAN_PATCH.value,
                operation_type="apply_replan_follow_up",
                request_digest=req_digest,
                instruction_digest=hashlib.sha256(payload.follow_up_text.encode("utf-8")).hexdigest(),
                preview_snapshot_schema_version=TRIP_SNAPSHOT_SCHEMA_VERSION,
                preview_snapshot=snapshot,
                preview_content_digest=preview_content_digest,
                proposal_digest=proposal_digest,
                planner_run_id=trace.planner_run_id,
                planner_version=trace.planner_version,
                trace_schema_version=trace.schema_version,
                trace_digest=trace.trace_digest,
                validation_report=validation_report,
                execution_kind="replan_snapshot",
                command_schema_version=None,
                mutation_engine_version=None,
                mutation_kind=None,
                commands=None,
                command_digest=None,
                impact_summary=None,
                invalidated_surfaces=None,
                status=ProposalStatus.PENDING.value,
                expires_at=expires_at,
                applied_revision_id=None,
                created_at=format_utc(now),
                updated_at=format_utc(now),
            )
        )
        return PersistedReplanPreviewResponse(
            trip=TripMetadata.from_record(trip),
            current_revision=TripRevisionMetadata.from_record(base_revision),
            proposal=MutationProposalMetadata.from_record(proposal),
            replan_result=ReplanItineraryResponse(
                trip_intent=require_trip_intent_envelope(stored_itinerary),
                itinerary=stored_itinerary,
            ),
        )

    def preview_typed_mutation(
        self,
        *,
        trip_id: str,
        capability: str | None,
        payload: PersistedMutationPreviewRequest,
    ) -> PersistedMutationPreviewResponse:
        trip = self._require_trip_access(trip_id, capability)
        base_revision = self.repository.get_revision(trip_id, payload.base_revision_id)
        if trip.current_revision_id != payload.base_revision_id:
            raise StaleMutationProposalError(
                trip_id=trip_id,
                proposal_id="pending",
                base_revision_id=payload.base_revision_id,
                current_revision_id=trip.current_revision_id,
            )
        envelope = TripMutationCommandEnvelope.model_validate(payload.model_dump(mode="json"))
        candidates_by_id = self._candidate_context_for_envelope(trip_id, envelope)
        preview = TripMutationEngine().preview(
            base_snapshot=base_revision.itinerary_snapshot,
            envelope=envelope,
            candidates_by_id=candidates_by_id,
        )
        now = self.clock()
        expires_at = format_utc(now + timedelta(seconds=get_trip_replan_proposal_ttl_seconds()))
        commands = [command.model_dump(mode="json") for command in envelope.commands]
        source_type = (
            RevisionSourceType.SWAP.value
            if envelope.mutation_kind == "swap"
            else RevisionSourceType.CANDIDATE_ADMISSION.value
            if envelope.mutation_kind == "candidate_admission"
            else RevisionSourceType.ROUTE_EDIT.value
        )
        operation_type = (
            "apply_swap_commands"
            if envelope.mutation_kind == "swap"
            else "apply_candidate_admission_commands"
            if envelope.mutation_kind == "candidate_admission"
            else "apply_route_edit_commands"
        )
        req_digest = request_digest(
            {
                "operation": "typed_trip_mutation_preview",
                "base_revision_id": envelope.base_revision_id,
                "schema_version": envelope.schema_version,
                "mutation_kind": envelope.mutation_kind,
                "command_digest": preview.command_digest,
            }
        )
        proposal_digest = mutation_proposal_digest(
            proposal_schema_version=TRIP_MUTATION_PROPOSAL_SCHEMA_VERSION,
            trip_id=trip_id,
            base_revision_id=envelope.base_revision_id,
            source_type=source_type,
            operation_type=operation_type,
            request_digest=req_digest,
            preview_snapshot_schema_version=TRIP_SNAPSHOT_SCHEMA_VERSION,
            preview_content_digest=preview.content_digest,
            planner_run_id=None,
            planner_version=None,
            trace_schema_version=None,
            trace_digest=None,
            validation_report=preview.validation_report,
            expires_at=expires_at,
            execution_kind="typed_command",
            command_digest=preview.command_digest,
            mutation_kind=envelope.mutation_kind,
            mutation_engine_version=TRIP_MUTATION_ENGINE_VERSION,
        )
        proposal = self.repository.create_mutation_proposal(
            proposal=TripMutationProposalRecord(
                id=generate_proposal_id(),
                trip_id=trip_id,
                base_revision_id=envelope.base_revision_id,
                proposal_schema_version=TRIP_MUTATION_PROPOSAL_SCHEMA_VERSION,
                source_type=source_type,
                operation_type=operation_type,
                request_digest=req_digest,
                instruction_digest=None,
                preview_snapshot_schema_version=TRIP_SNAPSHOT_SCHEMA_VERSION,
                preview_snapshot=preview.resulting_snapshot,
                preview_content_digest=preview.content_digest,
                proposal_digest=proposal_digest,
                planner_run_id=None,
                planner_version=None,
                trace_schema_version=None,
                trace_digest=None,
                validation_report=preview.validation_report,
                execution_kind="typed_command",
                command_schema_version=TRIP_MUTATION_COMMAND_SCHEMA_VERSION,
                mutation_engine_version=TRIP_MUTATION_ENGINE_VERSION,
                mutation_kind=envelope.mutation_kind,
                commands=commands,
                command_digest=preview.command_digest,
                impact_summary=preview.impact_summary,
                invalidated_surfaces=preview.invalidated_surfaces,
                status=ProposalStatus.PENDING.value,
                expires_at=expires_at,
                applied_revision_id=None,
                created_at=format_utc(now),
                updated_at=format_utc(now),
            )
        )
        return PersistedMutationPreviewResponse(
            trip=TripMetadata.from_record(trip),
            current_revision=TripRevisionMetadata.from_record(base_revision),
            proposal=MutationProposalMetadata.from_record(proposal),
            itinerary=deserialize_itinerary_snapshot(proposal.preview_snapshot),
            impact_summary=preview.impact_summary,
            invalidated_surfaces=preview.invalidated_surfaces,
            refresh_targets=preview.refresh_targets,
        )

    def apply_replan_proposal(
        self,
        *,
        trip_id: str,
        proposal_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: ApplyPersistedReplanProposalRequest,
    ) -> PersistedReplanResponse:
        if not idempotency_key or not idempotency_key.strip():
            from .errors import InvalidRevisionOperationError

            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        idempotency_key_hash = hash_idempotency_key(idempotency_key.strip())
        proposal = self.repository.get_mutation_proposal(trip_id=trip_id, proposal_id=proposal_id)
        if payload.base_revision_id != proposal.base_revision_id:
            raise ProposalDigestMismatchError()
        if payload.proposal_digest != proposal.proposal_digest:
            raise ProposalDigestMismatchError()
        stored_itinerary = deserialize_itinerary_snapshot(proposal.preview_snapshot)
        if itinerary_content_digest(proposal.preview_snapshot) != proposal.preview_content_digest:
            raise ProposalIntegrityViolationError()
        if proposal.preview_content_digest != itinerary_content_digest(
            serialize_itinerary_snapshot(stored_itinerary)
        ):
            raise PreviewApplyMismatchError()

        req_digest = request_digest(
            {
                "operation": "apply_replan_proposal",
                "proposal_id": proposal_id,
                "base_revision_id": payload.base_revision_id,
                "proposal_digest": payload.proposal_digest,
            }
        )
        operation_metadata = {
            "operation_type": "apply_replan_follow_up",
            "proposal_id": proposal.id,
            "proposal_schema_version": proposal.proposal_schema_version,
            "proposal_digest": proposal.proposal_digest,
            "preview_content_digest": proposal.preview_content_digest,
            "base_revision_id": proposal.base_revision_id,
            "source_type": proposal.source_type,
            "request_digest": proposal.request_digest,
            "instruction_digest": proposal.instruction_digest,
            "planner_run_id": proposal.planner_run_id,
            "planner_version": proposal.planner_version,
            "trace_schema_version": proposal.trace_schema_version,
            "trace_digest": proposal.trace_digest,
            "validation_report_digest": hashlib.sha256(
                canonical_json(proposal.validation_report).encode("utf-8")
            ).hexdigest(),
        }
        result = self.repository.apply_mutation_proposal(
            trip_id=trip_id,
            capability_hash=trip.capability_hash,
            proposal_id=proposal_id,
            base_revision_id=payload.base_revision_id,
            proposal_digest=payload.proposal_digest,
            now=format_utc(self.clock()),
            operation_summary="Applied a persisted conversational replan proposal.",
            operation_metadata=operation_metadata,
            request_digest=req_digest,
            idempotency_key_hash=idempotency_key_hash,
        )
        current_trip = self.repository.get_trip(trip_id)
        revision = result.revision
        if revision.content_digest != proposal.preview_content_digest:
            raise PreviewApplyMismatchError()
        itinerary = deserialize_itinerary_snapshot(revision.itinerary_snapshot)
        return PersistedReplanResponse(
            trip=TripMetadata.from_record(current_trip),
            current_revision=TripRevisionMetadata.from_record(revision),
            replan_result=ReplanItineraryResponse(
                trip_intent=require_trip_intent_envelope(itinerary),
                itinerary=itinerary,
            ),
            persistence=TripPersistenceInfo(idempotent_replay=result.idempotent_replay),
        )

    def apply_mutation_proposal(
        self,
        *,
        trip_id: str,
        proposal_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: ApplyPersistedMutationProposalRequest,
    ) -> PersistedMutationApplyResponse:
        if not idempotency_key or not idempotency_key.strip():
            from .errors import InvalidRevisionOperationError

            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        proposal = self.repository.get_mutation_proposal(trip_id=trip_id, proposal_id=proposal_id)
        if proposal.execution_kind != "typed_command":
            raise InvalidRevisionOperationError("Mutation proposal is not a typed command proposal.")
        if payload.base_revision_id != proposal.base_revision_id:
            raise ProposalDigestMismatchError()
        if payload.proposal_digest != proposal.proposal_digest:
            raise ProposalDigestMismatchError()
        stored_itinerary = deserialize_itinerary_snapshot(proposal.preview_snapshot)
        if itinerary_content_digest(proposal.preview_snapshot) != proposal.preview_content_digest:
            raise ProposalIntegrityViolationError()
        if proposal.preview_content_digest != itinerary_content_digest(
            serialize_itinerary_snapshot(stored_itinerary)
        ):
            raise PreviewApplyMismatchError()
        req_digest = request_digest(
            {
                "operation": "apply_typed_mutation_proposal",
                "proposal_id": proposal_id,
                "base_revision_id": payload.base_revision_id,
                "proposal_digest": payload.proposal_digest,
                "command_digest": proposal.command_digest,
                "mutation_kind": proposal.mutation_kind,
            }
        )
        operation_metadata = {
            "operation_type": proposal.operation_type,
            "proposal_id": proposal.id,
            "proposal_schema_version": proposal.proposal_schema_version,
            "proposal_digest": proposal.proposal_digest,
            "preview_content_digest": proposal.preview_content_digest,
            "base_revision_id": proposal.base_revision_id,
            "source_type": proposal.source_type,
            "execution_kind": proposal.execution_kind,
            "command_schema_version": proposal.command_schema_version,
            "mutation_engine_version": proposal.mutation_engine_version,
            "mutation_kind": proposal.mutation_kind,
            "command_digest": proposal.command_digest,
            "command_count": len(proposal.commands or []),
            "command_types": [
                str(command.get("type"))
                for command in (proposal.commands or [])
                if isinstance(command, dict) and command.get("type")
            ],
            "impact_summary": proposal.impact_summary,
            "validation_report_digest": hashlib.sha256(
                canonical_json(proposal.validation_report).encode("utf-8")
            ).hexdigest(),
            "invalidated_surfaces": proposal.invalidated_surfaces,
        }
        if proposal.mutation_kind == "candidate_admission":
            candidate_id = first_candidate_id_from_commands(proposal.commands or [])
            if candidate_id:
                candidate = self.repository.get_candidate(trip_id=trip_id, candidate_id=candidate_id)
                operation_metadata["candidate_admission"] = {
                    "candidate_id": candidate.id,
                    "candidate_content_digest": candidate.content_digest,
                    "candidate_source_kind": candidate.source_kind,
                    "candidate_source_ref": candidate.source_ref,
                    "scheduled_item_id": first_value_from_impact(proposal.impact_summary, "scheduled_item_ids"),
                    "assumption_codes": candidate_assumption_codes(candidate),
                }
        result = self.repository.apply_mutation_proposal(
            trip_id=trip_id,
            capability_hash=trip.capability_hash,
            proposal_id=proposal_id,
            base_revision_id=payload.base_revision_id,
            proposal_digest=payload.proposal_digest,
            now=format_utc(self.clock()),
            operation_summary=f"Applied {proposal.mutation_kind} typed mutation proposal.",
            operation_metadata=operation_metadata,
            request_digest=req_digest,
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
        )
        current_trip = self.repository.get_trip(trip_id)
        revision = result.revision
        if revision.content_digest != proposal.preview_content_digest:
            raise PreviewApplyMismatchError()
        return PersistedMutationApplyResponse(
            trip=TripMetadata.from_record(current_trip),
            current_revision=TripRevisionMetadata.from_record(revision),
            itinerary=deserialize_itinerary_snapshot(revision.itinerary_snapshot),
            impact_summary=proposal.impact_summary,
            invalidated_surfaces=proposal.invalidated_surfaces,
            refresh_targets=proposal.invalidated_surfaces,
            persistence=TripPersistenceInfo(idempotent_replay=result.idempotent_replay),
        )

    def undo_revision(
        self,
        *,
        trip_id: str,
        target_revision_id: str,
        capability: str | None,
        idempotency_key: str | None,
        base_revision_id: str,
    ) -> UndoPersistedMutationResponse:
        if not idempotency_key or not idempotency_key.strip():
            from .errors import InvalidRevisionOperationError

            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        req_digest = request_digest(
            {
                "operation": "undo_revision",
                "base_revision_id": base_revision_id,
                "target_revision_id": target_revision_id,
            }
        )
        idempotency_key_hash = hash_idempotency_key(idempotency_key.strip())
        idempotent_revision = self.repository.get_idempotent_revision(
            trip_id=trip_id,
            capability_hash=trip.capability_hash,
            request_digest=req_digest,
            idempotency_key_hash=idempotency_key_hash,
        )
        if idempotent_revision is not None:
            revision = idempotent_revision.revision
            return UndoPersistedMutationResponse(
                trip=TripMetadata.from_record(self.repository.get_trip(trip_id)),
                current_revision=TripRevisionMetadata.from_record(revision),
                itinerary=deserialize_itinerary_snapshot(revision.itinerary_snapshot),
                persistence=TripPersistenceInfo(idempotent_replay=True),
            )
        target_revision = self.repository.get_revision(trip_id, target_revision_id)
        if target_revision.id != trip.current_revision_id:
            raise UndoTargetNotCurrentError(
                target_revision_id=target_revision_id,
                current_revision_id=trip.current_revision_id,
            )
        if base_revision_id != trip.current_revision_id:
            raise UndoTargetNotCurrentError(
                target_revision_id=target_revision_id,
                current_revision_id=trip.current_revision_id,
            )
        undoable_source_types = {
            RevisionSourceType.REPLAN_PATCH.value,
            RevisionSourceType.ROUTE_EDIT.value,
            RevisionSourceType.SWAP.value,
            RevisionSourceType.COMPLETION_PATCH.value,
        }
        if target_revision.source_type not in undoable_source_types:
            raise RevisionNotUndoableError(target_revision_id)
        if target_revision.parent_revision_id is None:
            from .errors import InvalidRevisionOperationError

            raise InvalidRevisionOperationError("Initial revision cannot be undone.")
        parent_revision = self.repository.get_revision(trip_id, target_revision.parent_revision_id)
        undo_source_type = (
            RevisionSourceType.REPLAN_UNDO.value
            if target_revision.source_type == RevisionSourceType.REPLAN_PATCH.value
            else RevisionSourceType.COMPLETION_UNDO.value
            if target_revision.source_type == RevisionSourceType.COMPLETION_PATCH.value
            else RevisionSourceType.MUTATION_UNDO.value
        )
        result = self.repository.create_revision(
            trip_id=trip_id,
            capability_hash=trip.capability_hash,
            base_revision_id=base_revision_id,
            itinerary_snapshot=parent_revision.itinerary_snapshot,
            source_type=undo_source_type,
            operation_type="undo_revision",
            operation_summary=f"Undid revision {target_revision.revision_number} as a compensating revision.",
            operation_metadata={
                "operation_type": "undo_revision",
                "undone_revision_id": target_revision_id,
                "undone_revision_number": target_revision.revision_number,
                "undone_source_type": target_revision.source_type,
                "restored_parent_revision_id": parent_revision.id,
                "restored_parent_revision_number": parent_revision.revision_number,
            },
            request_digest=req_digest,
            idempotency_key_hash=idempotency_key_hash,
            restored_from_revision_id=parent_revision.id,
        )
        current_trip = self.repository.get_trip(trip_id)
        return UndoPersistedMutationResponse(
            trip=TripMetadata.from_record(current_trip),
            current_revision=TripRevisionMetadata.from_record(result.revision),
            itinerary=deserialize_itinerary_snapshot(result.revision.itinerary_snapshot),
            persistence=TripPersistenceInfo(idempotent_replay=result.idempotent_replay),
        )

    def restore_revision(
        self,
        *,
        trip_id: str,
        target_revision_id: str,
        capability: str | None,
        idempotency_key: str | None,
        base_revision_id: str,
    ) -> RestoreRevisionResponse:
        if not idempotency_key or not idempotency_key.strip():
            from .errors import InvalidRevisionOperationError

            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        target_revision = self.repository.get_revision(trip_id, target_revision_id)
        req_digest = request_digest(
            {
                "operation": "restore_revision",
                "base_revision_id": base_revision_id,
                "target_revision_id": target_revision_id,
            }
        )
        result = self.repository.create_revision(
            trip_id=trip_id,
            capability_hash=trip.capability_hash,
            base_revision_id=base_revision_id,
            itinerary_snapshot=target_revision.itinerary_snapshot,
            source_type=RevisionSourceType.RESTORE.value,
            operation_type="restore_revision",
            operation_summary=f"Restored revision {target_revision.revision_number}.",
            operation_metadata={
                "operation_type": "restore_revision",
                "target_revision_id": target_revision_id,
                "target_revision_number": target_revision.revision_number,
            },
            request_digest=req_digest,
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
            restored_from_revision_id=target_revision_id,
        )
        current_trip = self.repository.get_trip(trip_id)
        return RestoreRevisionResponse(
            trip=TripMetadata.from_record(current_trip),
            current_revision=TripRevisionMetadata.from_record(result.revision),
            itinerary=deserialize_itinerary_snapshot(result.revision.itinerary_snapshot),
            persistence=TripPersistenceInfo(idempotent_replay=result.idempotent_replay),
        )

    def _plan_from_text(self, payload: TripPlanRequest) -> dict[str, Any]:
        raw_text = payload.text or ""
        parsed_intent = disambiguate_trip_intent(parse_trip_text(raw_text), raw_text=raw_text)
        if payload.extra_preferences:
            parsed_intent = normalize_parsed_trip_intent(
                parsed_intent.model_copy(
                    update={
                        "preferences": unique_preserve_order(
                            [*parsed_intent.preferences, *payload.extra_preferences]
                        )
                    }
                )
            )
        planning_state = build_planning_input_state(parsed_intent)
        travel_mode = payload.travel_mode or infer_travel_mode_from_text(raw_text)
        itinerary_payload = build_itinerary_request_from_parsed_intent(
            parsed_intent=parsed_intent,
            planning_state=planning_state,
            travel_mode=travel_mode,
            auto_fill_sparse_days=payload.auto_fill_sparse_days,
        )
        collector = build_trace_collector(
            itinerary_payload,
            raw_text=raw_text,
        )
        itinerary = build_itinerary_response(
            itinerary_payload,
            intent_source=TripIntentEnvelopeSource.INITIAL_TEXT,
            raw_text=raw_text,
            parsed_intent=parsed_intent,
            planning_state=planning_state,
            trace_collector=collector,
        )
        trace = collector.build_trace(build_planner_result_summary(itinerary))
        trace.trace_digest = planner_trace_digest(trace)
        return {
            "itinerary": itinerary,
            "trip_intent": itinerary.trip_intent,
            "parsed_intent": parsed_intent,
            "planning_state": planning_state,
            "trace": trace,
        }

    def _plan_from_itinerary_request(self, payload: TripPlanRequest) -> dict[str, Any]:
        itinerary_payload = payload.itinerary_request
        if itinerary_payload is None:
            raise ValueError("itinerary_request is required.")
        collector = build_trace_collector(itinerary_payload)
        itinerary = build_itinerary_response(
            itinerary_payload,
            trace_collector=collector,
        )
        trace = collector.build_trace(build_planner_result_summary(itinerary))
        trace.trace_digest = planner_trace_digest(trace)
        return {
            "itinerary": itinerary,
            "trip_intent": itinerary.trip_intent,
            "trace": trace,
        }

    def _require_trip_access(self, trip_id: str, capability: str | None):
        trip = self.repository.get_trip(trip_id)
        if not verify_capability(capability, trip.capability_hash):
            raise TripAccessDeniedError()
        return trip

    def _intent_candidate_context(
        self,
        trip_id: str,
        payload: CompileTripIntentRequest,
    ) -> tuple[list[TripCandidateRecord], dict[str, str]]:
        candidate_ids = list(payload.candidate_ids)
        if payload.structured_overrides is not None:
            candidate_ids.extend(payload.structured_overrides.must_candidate_ids)
        if payload.llm_proposal is not None:
            candidate_ids.extend(payload.llm_proposal.must_candidate_ids)

        ordered_ids: list[str] = []
        seen: set[str] = set()
        for candidate_id in candidate_ids:
            normalized = str(candidate_id).strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                ordered_ids.append(normalized)

        if not ordered_ids:
            return [], {}

        decisions_by_candidate: dict[str, list[TripCandidateDecisionRecord]] = {}
        for decision in self.repository.list_candidate_decisions(trip_id=trip_id):
            decisions_by_candidate.setdefault(decision.candidate_id, []).append(decision)

        candidates: list[TripCandidateRecord] = []
        states: dict[str, str] = {}
        for candidate_id in ordered_ids:
            candidate = self.repository.get_candidate(trip_id=trip_id, candidate_id=candidate_id)
            workflow_state, _latest_id = infer_workflow_state(decisions_by_candidate.get(candidate_id, []))
            candidates.append(candidate)
            states[candidate_id] = workflow_state
        return candidates, states

    def _candidate_context_for_envelope(
        self,
        trip_id: str,
        envelope: TripMutationCommandEnvelope,
    ) -> dict[str, dict[str, Any]]:
        candidate_ids = [
            str(command.candidate_id)
            for command in envelope.commands
            if getattr(command, "type", None) == "add_candidate_stop"
        ]
        if not candidate_ids:
            return {}
        decisions_by_candidate: dict[str, list[TripCandidateDecisionRecord]] = {}
        for decision in self.repository.list_candidate_decisions(trip_id=trip_id):
            decisions_by_candidate.setdefault(decision.candidate_id, []).append(decision)
        result: dict[str, dict[str, Any]] = {}
        for candidate_id in candidate_ids:
            candidate = self.repository.get_candidate(trip_id=trip_id, candidate_id=candidate_id)
            workflow_state, latest_id = infer_workflow_state(decisions_by_candidate.get(candidate_id, []))
            result[candidate_id] = candidate_to_response(
                candidate,
                workflow_state=workflow_state,
                latest_decision_id=latest_id,
            ).model_dump(mode="json")
        return result


def build_trace_collector(payload, *, raw_text: str | None = None) -> PlannerTraceCollector:
    return PlannerTraceCollector(
        planner_run_id=f"run_{uuid4().hex}",
        input_summary=build_planner_input_snapshot(
            payload,
            raw_text_ref=hashlib.sha256(raw_text.encode("utf-8")).hexdigest() if raw_text else None,
        ),
        volatile_metadata={},
    )


def execute_replan_from_itinerary(
    *,
    base_itinerary: ItineraryResponse,
    follow_up_text: str,
    auto_fill_sparse_days: bool,
) -> tuple[ReplanItineraryResponse, PlannerTrace]:
    trip_intent = base_itinerary.trip_intent
    replan_payload = ReplanItineraryRequest(
        trip_intent=trip_intent,
        base_intent=(
            None
            if trip_intent is not None
            else base_itinerary.planning_assumptions.regeneration_intent
            if base_itinerary.planning_assumptions is not None
            else None
        ),
        follow_up_text=follow_up_text,
        auto_fill_sparse_days=auto_fill_sparse_days,
    )
    base_intent = resolve_replan_base_intent(replan_payload)
    follow_up_intent = disambiguate_trip_intent(
        parse_trip_text(follow_up_text),
        raw_text=follow_up_text,
        city_hint=base_intent.city,
    )
    merged_payload, merge_notes, interpretation_summary = build_replan_request(
        base_intent=base_intent,
        follow_up_text=follow_up_text,
        follow_up_intent=follow_up_intent,
        auto_fill_sparse_days=auto_fill_sparse_days,
    )
    collector = build_trace_collector(merged_payload, raw_text=follow_up_text)
    itinerary = build_itinerary_response(
        merged_payload,
        replan_notes=merge_notes,
        follow_up_interpretation=interpretation_summary,
        intent_source=TripIntentEnvelopeSource.FOLLOW_UP,
        raw_text=trip_intent.raw_text if trip_intent is not None else follow_up_text,
        latest_follow_up_text=follow_up_text,
        base_intent=base_intent,
        parsed_intent=trip_intent.parsed_intent if trip_intent is not None else follow_up_intent,
        planning_state=trip_intent.planning_state if trip_intent is not None else None,
        completion_candidate_history=(
            trip_intent.completion_candidate_history if trip_intent is not None else None
        ),
        trace_collector=collector,
    )
    trace = collector.build_trace(build_planner_result_summary(itinerary))
    trace.trace_digest = planner_trace_digest(trace)
    return (
        ReplanItineraryResponse(
            trip_intent=require_trip_intent_envelope(itinerary),
            itinerary=itinerary,
        ),
        trace,
    )


def build_replan_request_digest_payload(payload: PersistedReplanRequest) -> dict[str, Any]:
    return {
        "operation": "replan_follow_up",
        "base_revision_id": payload.base_revision_id,
        "follow_up_text_digest": hashlib.sha256(payload.follow_up_text.encode("utf-8")).hexdigest(),
        "auto_fill_sparse_days": payload.auto_fill_sparse_days,
    }


def utc_now_datetime() -> datetime:
    return datetime.now(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def sanitize_replan_preview_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    sanitized = copy.deepcopy(snapshot)
    trip_intent = sanitized.get("trip_intent")
    if isinstance(trip_intent, dict):
        if trip_intent.get("latest_follow_up_text") is not None:
            trip_intent["latest_follow_up_text"] = "[redacted]"
        interpretation = trip_intent.get("follow_up_interpretation")
        if isinstance(interpretation, dict):
            interpretation["raw_text"] = "[redacted]"
    assumptions = sanitized.get("planning_assumptions")
    if isinstance(assumptions, dict):
        interpretation = assumptions.get("follow_up_interpretation")
        if isinstance(interpretation, dict):
            interpretation["raw_text"] = "[redacted]"
    return sanitized


def build_mutation_validation_report(
    *,
    itinerary: ItineraryResponse,
    trace: PlannerTrace,
) -> dict[str, Any]:
    schema_valid = {"code": "RESULT_SCHEMA_VALID", "status": "pass", "evidence": {}}
    fixed_events = {
        "code": "FIXED_EVENTS_PRESERVED",
        "status": "not_applicable",
        "evidence": {"reason": "Preview is validated from the compiled itinerary snapshot."},
    }
    lineage_present = {
        "code": "PLANNER_LINEAGE_PRESENT",
        "status": "pass"
        if trace.planner_run_id
        and trace.planner_version
        and trace.schema_version
        and trace.trace_digest
        else "fail",
        "evidence": {
            "planner_run_id": trace.planner_run_id,
            "planner_version": trace.planner_version,
            "trace_schema_version": trace.schema_version,
            "trace_digest": trace.trace_digest,
        },
    }
    invariant_results = [
        schema_valid,
        fixed_events,
        no_schedule_overlap(itinerary).model_dump(mode="json"),
        within_day_availability(itinerary).model_dump(mode="json"),
        within_arrival_departure_boundaries(itinerary).model_dump(mode="json"),
        no_duplicate_scheduled_place(itinerary).model_dump(mode="json"),
        missing_route_not_zero(trace).model_dump(mode="json"),
        lineage_present,
    ]
    return {
        "schema_version": "1.0",
        "critical_passed": all(item["status"] != "fail" for item in invariant_results),
        "invariants": invariant_results,
    }


def assert_mutation_validation_passed(validation_report: dict[str, Any]) -> None:
    if not validation_report.get("critical_passed"):
        raise InvalidRevisionOperationError("Mutation proposal failed deterministic validation.")


def serialize_itinerary_snapshot(itinerary: ItineraryResponse) -> dict[str, Any]:
    return itinerary.model_dump(mode="json")


def deserialize_itinerary_snapshot(snapshot: dict[str, Any]) -> ItineraryResponse:
    version = TRIP_SNAPSHOT_SCHEMA_VERSION
    if not version.startswith("1."):
        raise SnapshotSchemaUnsupportedError(version)
    return ItineraryResponse.model_validate(snapshot)


def redacted_plan_request_payload(payload: TripPlanRequest) -> dict[str, Any]:
    if payload.text:
        return {
            "text_digest": hashlib.sha256(payload.text.encode("utf-8")).hexdigest(),
            "travel_mode": payload.travel_mode,
            "auto_fill_sparse_days": payload.auto_fill_sparse_days,
            "extra_preferences": payload.extra_preferences,
        }
    return {
        "itinerary_request": payload.itinerary_request.model_dump(mode="json")
        if payload.itinerary_request is not None
        else None,
        "auto_fill_sparse_days": payload.auto_fill_sparse_days,
    }


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def first_candidate_id_from_commands(commands: list[dict[str, Any]]) -> str | None:
    for command in commands:
        if command.get("type") == "add_candidate_stop" and command.get("candidate_id"):
            return str(command["candidate_id"])
    return None


def first_value_from_impact(impact: dict[str, Any] | None, key: str) -> Any:
    if not isinstance(impact, dict):
        return None
    values = impact.get(key)
    if isinstance(values, list) and values:
        return values[0]
    return None


def candidate_assumption_codes(candidate) -> list[str]:
    codes: list[str] = []
    if candidate.location_state == "assumed":
        codes.append("LOCATION_ASSUMED")
    if candidate.duration_state == "assumed":
        codes.append("DURATION_ASSUMED")
    return codes
