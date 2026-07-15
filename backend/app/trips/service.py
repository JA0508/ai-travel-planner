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
from .digests import (
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
    StaleMutationProposalError,
    TripAccessDeniedError,
    UndoTargetNotCurrentError,
)
from .models import ProposalStatus, RevisionSourceType, TripMutationProposalRecord
from .repository import TripRepository
from .schemas import (
    ApplyPersistedReplanProposalRequest,
    MutationProposalMetadata,
    PersistedCompletionTaskActionRequest,
    PersistedCompletionTaskActionResponse,
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
        aggregate = self.repository.create_trip_with_initial_revision(
            itinerary_snapshot=serialize_itinerary_snapshot(itinerary),
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
            itinerary=itinerary,
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
        next_itinerary = task_result.itinerary
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
            itinerary_snapshot=serialize_itinerary_snapshot(next_itinerary),
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
            task_response = task_result
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
        snapshot = sanitize_replan_preview_snapshot(
            serialize_itinerary_snapshot(replan_result.itinerary)
        )
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
        if target_revision.source_type != RevisionSourceType.REPLAN_PATCH.value:
            raise RevisionNotUndoableError(target_revision_id)
        if target_revision.parent_revision_id is None:
            from .errors import InvalidRevisionOperationError

            raise InvalidRevisionOperationError("Initial revision cannot be undone.")
        parent_revision = self.repository.get_revision(trip_id, target_revision.parent_revision_id)
        result = self.repository.create_revision(
            trip_id=trip_id,
            capability_hash=trip.capability_hash,
            base_revision_id=base_revision_id,
            itinerary_snapshot=parent_revision.itinerary_snapshot,
            source_type=RevisionSourceType.REPLAN_UNDO.value,
            operation_type="undo_revision",
            operation_summary=f"Undid revision {target_revision.revision_number} as a compensating revision.",
            operation_metadata={
                "operation_type": "undo_revision",
                "undone_revision_id": target_revision_id,
                "undone_revision_number": target_revision.revision_number,
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
