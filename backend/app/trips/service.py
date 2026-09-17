from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
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
from app.imports.repository import ImportRepository
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
    VerifiedPlaceRef,
)
from app.services.itinerary_completion_recommendation import (
    find_scheduled_stop,
    replacement_candidate_category_compatible,
    replacement_route_impact,
    replacement_route_is_actionable,
)
from app.services.intent_disambiguation import disambiguate_trip_intent
from app.services.nl_parser import normalize_parsed_trip_intent, parse_trip_text
from app.services.planning_state_transformer import build_planning_input_state
from app.services.draft_intent_projection import DraftIntentProjectionError, project_confirmed_draft_intent
from app.services.planning_run_creation import (
    CreatedPlanningRun,
    PlanningRunCreationError,
    create_planning_run_from_confirmed_intent,
)
from app.services.place_identity_resolution import (
    PlaceIdentityResolutionError,
    confirm_place_identity,
    discover_fixed_event_identity,
    discover_place_identities,
    search_place_identity_suggestions,
)
from app.services.poi_discovery_provider import (
    PoiDiscoveryUnavailable,
    default_poi_discovery_provider,
)
from .access import (
    generate_capability,
    generate_proposal_id,
    hash_capability,
    hash_idempotency_key,
    verify_capability,
)
from .candidates import (
    CandidateEvidenceLinkRecord,
    CandidateDecisionReasonCode,
    CandidateDecisionType,
    CandidateSourceKind,
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
    MutationCommandFailedError,
    PreviewApplyMismatchError,
    ProposalDigestMismatchError,
    ProposalIntegrityViolationError,
    RestoreWouldDropAvailabilityWindowsError,
    RestoreWouldDropFixedItemsError,
    RestoreWouldDropMustVisitPlacesError,
    RevisionNotUndoableError,
    SnapshotSchemaUnsupportedError,
    StaleBaseRevisionError,
    ClarificationAlreadyResolvedError,
    DraftIntentEditError,
    PlaceIdentityProviderUnavailableError,
    StaleDraftRevisionError,
    StaleIntentRevisionError,
    StaleMutationProposalError,
    TripAccessDeniedError,
    UndoTargetNotCurrentError,
)
from .intent_contracts import (
    AnswerIntentClarificationRequest,
    ClarificationQuestion,
    CompileTripIntentRequest,
    CompileTripIntentResponse,
    EditTripIntentEnvelopeRequest,
    IntentClarificationResolutionKind,
    IntentCompileRunDraft,
    IntentProposalParseResult,
    IntentStructuredOverrides,
    INTENT_DATE_POLICY_VERSION,
    INTENT_PRECEDENCE_VERSION,
    INTENT_READINESS_POLICY_VERSION,
    RestoreTripIntentEnvelopeRequest,
    SourceLinkedTripIntentEnvelope,
    TRIP_INTENT_COMPILER_VERSION,
    TRIP_INTENT_ENVELOPE_SCHEMA_VERSION,
    TripIntentRevisionDetailResponse,
    TripIntentRevisionListResponse,
    TripIntentRevisionRecord,
    compile_source_linked_intent,
    finalize_intent_envelope_for_revision,
    intent_revision_metadata,
)
from .draft_intent_edits import (
    ConfirmPlaceIdentityOperation,
    DraftClarificationResolveRequest,
    DraftIntentEditRequest,
    DraftIntentEditValidationError,
    UpdateDestinationOperation,
    UpdateFixedEventOperation,
    apply_operations_to_overrides,
    clarification_answer_to_operation,
)
from .intent_llm_adapter import build_untrusted_llm_intent_proposal
from .models import (
    DraftIntentRevisionRecord,
    PlannerHandoffRunRecord,
    PrePlanHandoffRunRecord,
    ProposalStatus,
    RevisionSourceType,
    TripCandidateRecord,
    TripMutationProposalRecord,
    TripPlanningPhase,
)
from .planner_handoff import (
    PLANNER_HANDOFF_INPUT_SCHEMA_VERSION,
    attach_handoff_source_links,
    build_planner_handoff_input,
    record_handoff_trace_context,
)
from .mutation_commands import (
    ReplaceStopCommand,
    TripMutationCommandEnvelope,
    TripMutationEngine,
    ensure_stable_item_ids,
)
from .repository import TripRepository
from .schemas import (
    ApplyPersistedMutationProposalRequest,
    ApplyPersistedReplanProposalRequest,
    MutationProposalMetadata,
    PersistedCompletionTaskActionRequest,
    PersistedCompletionTaskActionResponse,
    PersistedMutationApplyResponse,
    LocalRepairPreviewRequest,
    PersistedMutationPreviewRequest,
    PersistedMutationPreviewResponse,
    ApplyPlannerHandoffProposalRequest,
    DraftTripCreateResponse,
    DraftIntentPlanningRunRequest,
    DraftTripDetailResponse,
    DraftIntentRevisionMetadata,
    DraftIntentEditResponse,
    PrePlanPlaceIdentitySuggestionsResponse,
    PrePlanIntentLatestResponse,
    PrePlanHandoffApplyRequest,
    PrePlanHandoffApplyResponse,
    PrePlanHandoffPreviewRequest,
    PrePlanHandoffPreviewResponse,
    PrePlanHandoffRunMetadata,
    PrePlanIntentCompileResponse,
    PlannerHandoffApplyResponse,
    PlannerHandoffPreviewRequest,
    PlannerHandoffPreviewResponse,
    PlannerHandoffRunMetadata,
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
    def __init__(self, repository: TripRepository, *, import_repository: ImportRepository | None = None, clock=None) -> None:
        self.repository = repository
        self.import_repository = import_repository
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

    def create_draft_trip(self, *, direct_user_text: str, idempotency_key: str | None) -> CreatedTripResult:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        # A Draft Trip has no cookie capability before its first response. Deriving the
        # one-time anonymous capability from the caller's high-entropy idempotency key
        # makes a lost-response retry recover the same private draft without duplicating it.
        capability = f"draft-capability:{idempotency_key.strip()}"
        trip, replay = self.repository.create_draft_trip(
            capability_hash=hash_capability(capability),
            direct_user_text=direct_user_text,
            source_digest=request_digest({"direct_user_text": direct_user_text}),
            request_digest=request_digest({"operation": "create_draft_trip", "source_digest": request_digest({"direct_user_text": direct_user_text}), "schema": "f001c-v1"}),
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
        )
        return CreatedTripResult(
            response=DraftTripCreateResponse(
                trip=TripMetadata.from_record(trip),
                persistence=TripPersistenceInfo(idempotent_replay=replay),
            ),
            capability=capability,
        )

    def get_draft_trip(self, *, trip_id: str, capability: str | None) -> DraftTripDetailResponse:
        trip = self._require_trip_access(trip_id, capability)
        if trip.planning_phase != TripPlanningPhase.DRAFT.value or trip.current_revision_id is not None:
            raise InvalidRevisionOperationError("Trip is no longer a draft.")
        return DraftTripDetailResponse(
            trip=TripMetadata.from_record(trip),
            direct_user_text=self.repository.get_draft_source_text(trip_id=trip_id),
        )

    def compile_draft_intent_envelope(
        self,
        *,
        trip_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: CompileTripIntentRequest,
    ) -> PrePlanIntentCompileResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        if trip.planning_phase != TripPlanningPhase.DRAFT.value or trip.current_revision_id is not None:
            raise InvalidRevisionOperationError("Pre-plan intent is only available while the trip is a draft.")
        if payload.base_revision_id is not None:
            raise StaleBaseRevisionError(trip_id=trip_id, provided_base_revision_id=payload.base_revision_id, current_revision_id="")
        parent = self.repository.get_latest_draft_intent_revision(trip_id=trip_id)
        parent_id = parent.id if parent else None
        if payload.base_intent_revision_id != parent_id:
            raise StaleIntentRevisionError(trip_id=trip_id, provided_intent_revision_id=payload.base_intent_revision_id or "", current_intent_revision_id=parent_id or "")
        # The persisted Draft source is the only direct-language authority. A
        # caller cannot compile a different browser string into this Draft Trip.
        direct_user_text = self.repository.get_draft_source_text(trip_id=trip_id)
        compiler_payload = payload.model_copy(update={"direct_user_text": direct_user_text})
        candidates, states, preferences = self._intent_candidate_context(trip_id, compiler_payload)
        refs, verification = self._verified_candidate_source_refs(trip_id, candidates)
        now = format_utc(self.clock())
        parser_result = self._build_intent_proposal_parse_result(compiler_payload)
        discovery_city = (
            compiler_payload.structured_overrides.city
            if compiler_payload.structured_overrides and compiler_payload.structured_overrides.city
            else None
        )
        place_identities = discover_place_identities(
            direct_user_text=direct_user_text,
            city=discovery_city,
        )
        envelope = compile_source_linked_intent(
            trip_id=trip_id,
            base_revision_id=None,
            parent_intent_revision_id=parent_id,
            next_revision_number=0,
            created_at=now,
            request=compiler_payload,
            parser_result=parser_result,
            existing_trip_snapshot={},
            parent_intent_snapshot=parent.envelope if parent else None,
            candidates=candidates,
            candidate_workflow_states=states,
            candidate_preferences=preferences,
            verified_candidate_source_refs=refs,
            candidate_verification_states=verification,
            place_identities=place_identities,
            require_fixed_place_identity=True,
        )
        envelope.validation_report.update({"preplan_contract": True, "base_trip_revision_absent": True})
        record = DraftIntentRevisionRecord(
            id=envelope.id,
            trip_id=trip_id,
            revision_number=0,
            parent_draft_intent_revision_id=parent_id,
            envelope_schema_version=TRIP_INTENT_ENVELOPE_SCHEMA_VERSION,
            envelope=envelope.model_dump(mode="json"),
            content_digest=envelope.content_digest,
            compiler_version=TRIP_INTENT_COMPILER_VERSION,
            source_digest=envelope.source_digest,
            validation_report=envelope.validation_report,
            created_at=now,
        )
        req_digest = request_digest({"operation": "compile_draft_trip_intent_envelope", "trip_id": trip_id, "parent": parent_id, "payload": compiler_payload.model_dump(mode="json")})
        stored, replay = self.repository.create_draft_intent_revision(
            revision=record,
            request_digest=req_digest,
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
            expected_parent_draft_intent_revision_id=parent_id,
        )
        return PrePlanIntentCompileResponse(envelope=stored.envelope, revision=DraftIntentRevisionMetadata.from_record(stored), idempotent_replay=replay)

    def edit_draft_intent(
        self,
        *,
        trip_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: DraftIntentEditRequest,
    ) -> DraftIntentEditResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        if trip.planning_phase != TripPlanningPhase.DRAFT.value or trip.current_revision_id is not None:
            raise InvalidRevisionOperationError("Draft intent edits are only available while the trip is a draft.")
        parent = self.repository.get_latest_draft_intent_revision(trip_id=trip_id)
        if parent is None:
            raise DraftIntentEditError("intent_edit_no_longer_applicable")
        try:
            parent_envelope = SourceLinkedTripIntentEnvelope.model_validate(parent.envelope)
            overrides = apply_operations_to_overrides(parent_envelope, payload.operations)
        except DraftIntentEditValidationError as exc:
            raise DraftIntentEditError(exc.code) from exc
        place_identities = list(parent_envelope.formal_contract.place_identities)
        try:
            for operation in payload.operations:
                if isinstance(operation, ConfirmPlaceIdentityOperation):
                    index = next(
                        (
                            item_index
                            for item_index, identity in enumerate(place_identities)
                            if identity.stable_id == operation.place_stable_id
                        ),
                        None,
                    )
                    if index is None:
                        raise DraftIntentEditError("place_identity_not_found")
                    place_identities[index] = confirm_place_identity(
                        identity=place_identities[index],
                        provider_place_id=operation.provider_place_id,
                        search_query=operation.search_query,
                    )
                elif isinstance(operation, UpdateDestinationOperation):
                    # Destination changes invalidate old provider scope. Re-read
                    # the persisted source rather than carrying a stale identity.
                    place_identities = discover_place_identities(
                        direct_user_text=self.repository.get_draft_source_text(trip_id=trip_id),
                        city=operation.city,
                    )
                elif isinstance(operation, UpdateFixedEventOperation):
                    # A manually supplied booking location is new user authority.
                    # Replace only this event's provider choices; unrelated
                    # confirmations remain attached to the next Draft revision.
                    event = next(
                        (item for item in overrides.fixed_events if item.event_id == operation.fixed_event_id),
                        None,
                    )
                    place_identities = [
                        identity
                        for identity in place_identities
                        if identity.fixed_event_id != operation.fixed_event_id
                        and identity.stable_id != operation.fixed_event_id
                    ]
                    if event is not None and event.location_text and event.location_text.strip():
                        previous = next(
                            (
                                identity
                                for identity in parent_envelope.formal_contract.place_identities
                                if identity.fixed_event_id == operation.fixed_event_id
                                or identity.stable_id == operation.fixed_event_id
                            ),
                            None,
                        )
                        city = (
                            overrides.city
                            or (
                                parent_envelope.formal_contract.destinations[0].city_name
                                if parent_envelope.formal_contract.destinations
                                else None
                            )
                        )
                        place_identities.append(
                            discover_fixed_event_identity(
                                event_id=operation.fixed_event_id,
                                location_text=event.location_text.strip(),
                                city=city,
                                source_fragment_ids=(
                                    previous.source_fragment_ids
                                    if previous is not None
                                    else [f"draft_intent:{parent.id}:fixed_event:{operation.fixed_event_id}"]
                                ),
                            )
                        )
        except PlaceIdentityResolutionError as exc:
            if exc.code == "place_identity_provider_unavailable":
                raise PlaceIdentityProviderUnavailableError() from exc
            raise DraftIntentEditError(exc.code) from exc
        candidate_ids = sorted({
            *overrides.must_candidate_ids,
            *overrides.optional_candidate_ids,
            *overrides.avoid_candidate_ids,
            *(event.place_candidate_id for event in overrides.fixed_events if event.place_candidate_id),
        })
        candidates, states, preferences = self._intent_candidate_context(
            trip_id,
            CompileTripIntentRequest(base_intent_revision_id=parent.id, candidate_ids=candidate_ids, structured_overrides=overrides),
        )
        refs, verification = self._verified_candidate_source_refs(trip_id, candidates)
        self._validate_draft_edit_candidates(candidate_ids, states, verification)
        now = format_utc(self.clock())
        compiler_request = CompileTripIntentRequest(
            base_intent_revision_id=parent.id,
            candidate_ids=candidate_ids,
            structured_overrides=overrides,
        )
        parser_result = IntentProposalParseResult(
            status="success",
            proposal=None,
            parser_name="draft_intent_typed_editor",
            parser_version=TRIP_INTENT_COMPILER_VERSION,
            warning_codes=[],
        )
        envelope = compile_source_linked_intent(
            trip_id=trip_id,
            base_revision_id=None,
            parent_intent_revision_id=parent.id,
            next_revision_number=0,
            created_at=now,
            request=compiler_request,
            parser_result=parser_result,
            existing_trip_snapshot={},
            parent_intent_snapshot=parent.envelope,
            candidates=candidates,
            candidate_workflow_states=states,
            candidate_preferences=preferences,
            verified_candidate_source_refs=refs,
            candidate_verification_states=verification,
            place_identities=place_identities,
            require_fixed_place_identity=True,
        )
        operation_names = [operation.operation for operation in payload.operations]
        envelope.validation_report.update({
            "preplan_contract": True,
            "draft_intent_edit": True,
            "draft_intent_edit_operations": operation_names,
            "parser_calls": 0,
            "llm_calls": 0,
            "planner_calls": 0,
            "preview_created": 0,
            "trip_revision_created": 0,
            "itinerary_mutations": 0,
        })
        if payload.clarification_resolution_id:
            envelope.validation_report["clarification_resolution"] = {
                "question_id": payload.clarification_resolution_id,
                "resolved_from_draft_intent_revision_id": parent.id,
            }
        record = DraftIntentRevisionRecord(
            id=envelope.id,
            trip_id=trip_id,
            revision_number=0,
            parent_draft_intent_revision_id=parent.id,
            envelope_schema_version=TRIP_INTENT_ENVELOPE_SCHEMA_VERSION,
            envelope=envelope.model_dump(mode="json"),
            content_digest=envelope.content_digest,
            compiler_version=TRIP_INTENT_COMPILER_VERSION,
            source_digest=envelope.source_digest,
            validation_report=envelope.validation_report,
            created_at=now,
        )
        result = self.repository.edit_draft_intent_revision(
            revision=record,
            request_digest=request_digest({
                "operation": "draft_intent_edit",
                "trip_id": trip_id,
                "base_intent_revision_id": payload.base_intent_revision_id,
                "base_draft_version": payload.base_draft_version,
                "operations": [operation.model_dump(mode="json") for operation in payload.operations],
                "clarification_resolution_id": payload.clarification_resolution_id,
            }),
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
            expected_parent_draft_intent_revision_id=payload.base_intent_revision_id,
            expected_draft_version=payload.base_draft_version,
            operation=(
                f"draft_intent_clarification:{payload.clarification_resolution_id}:"
                if payload.clarification_resolution_id
                else "draft_intent_edit:"
            ) + ",".join(operation_names),
        )
        stored_envelope = SourceLinkedTripIntentEnvelope.model_validate(result.revision.envelope)
        issue_summary = list(stored_envelope.readiness_policy.blocking_reason_codes) if stored_envelope.readiness_policy else []
        return DraftIntentEditResponse(
            draft_trip_id=trip_id,
            draft_version=result.draft_version,
            previous_intent_revision_id=result.previous_intent_revision_id,
            latest_intent_revision_id=result.revision.id,
            intent_revision_number=result.revision.revision_number,
            changed=result.changed,
            idempotent_replay=result.idempotent_replay,
            readiness=stored_envelope.planner_ready_status.value,
            issue_summary=issue_summary,
            envelope=result.revision.envelope,
            revision=DraftIntentRevisionMetadata.from_record(result.revision),
        )

    def get_latest_preplan_intent(self, *, trip_id: str, capability: str | None) -> PrePlanIntentLatestResponse:
        trip = self._require_trip_access(trip_id, capability)
        if trip.planning_phase != TripPlanningPhase.DRAFT.value or trip.current_revision_id is not None:
            raise InvalidRevisionOperationError("Pre-plan intent is only available while the trip is a draft.")
        revision = self.repository.get_latest_draft_intent_revision(trip_id=trip_id)
        if revision is None:
            raise DraftIntentEditError("intent_edit_no_longer_applicable")
        return PrePlanIntentLatestResponse(
            trip=TripMetadata.from_record(trip),
            envelope=revision.envelope,
            revision=DraftIntentRevisionMetadata.from_record(revision),
        )

    def get_draft_place_identity_suggestions(
        self,
        *,
        trip_id: str,
        capability: str | None,
        place_stable_id: str,
        query: str | None,
    ) -> PrePlanPlaceIdentitySuggestionsResponse:
        """Return provider-backed choices without changing the current Draft revision."""

        trip = self._require_trip_access(trip_id, capability)
        if trip.planning_phase != TripPlanningPhase.DRAFT.value or trip.current_revision_id is not None:
            raise InvalidRevisionOperationError("Place suggestions are only available while the trip is a draft.")
        revision = self.repository.get_latest_draft_intent_revision(trip_id=trip_id)
        if revision is None:
            raise DraftIntentEditError("intent_edit_no_longer_applicable")
        envelope = SourceLinkedTripIntentEnvelope.model_validate(revision.envelope)
        identity = next(
            (item for item in envelope.formal_contract.place_identities if item.stable_id == place_stable_id),
            None,
        )
        if identity is None:
            raise DraftIntentEditError("place_identity_not_found")
        try:
            suggestions = search_place_identity_suggestions(identity=identity, query=query)
        except PlaceIdentityResolutionError as exc:
            if exc.code == "place_identity_provider_unavailable":
                raise PlaceIdentityProviderUnavailableError() from exc
            raise DraftIntentEditError(exc.code) from exc
        return PrePlanPlaceIdentitySuggestionsResponse(
            place_stable_id=identity.stable_id,
            query=suggestions.query,
            options=suggestions.options,
            recommended_provider_place_id=suggestions.recommended_provider_place_id,
            recommendation_reason=(
                "基于地点名称和本次目的地的提供商检索排序。"
                if suggestions.recommended_provider_place_id
                else None
            ),
        )

    def create_draft_intent_planning_run(
        self,
        *,
        trip_id: str,
        capability: str | None,
        payload: DraftIntentPlanningRunRequest,
    ) -> CreatedPlanningRun:
        """Create the existing Planning Run from the latest confirmed Draft Intent."""

        trip = self._require_trip_access(trip_id, capability)
        if trip.planning_phase != TripPlanningPhase.DRAFT.value or trip.current_revision_id is not None:
            raise InvalidRevisionOperationError("Route generation is only available while this trip is a draft.")
        latest = self.repository.get_latest_draft_intent_revision(trip_id=trip_id)
        if latest is None or latest.id != payload.draft_intent_revision_id:
            raise StaleIntentRevisionError(
                trip_id=trip_id,
                provided_intent_revision_id=payload.draft_intent_revision_id,
                current_intent_revision_id=latest.id if latest else "",
            )
        envelope = SourceLinkedTripIntentEnvelope.model_validate(latest.envelope)
        try:
            intent = project_confirmed_draft_intent(envelope)
            return create_planning_run_from_confirmed_intent(
                intent=intent,
                source_context={
                    "source": "draft_intent_revision",
                    "draft_trip_id": trip_id,
                    "draft_intent_revision_id": latest.id,
                    "intent_semantic_digest": envelope.semantic_digest or "",
                    "intent_lineage_digest": envelope.lineage_digest or "",
                },
            )
        except (DraftIntentProjectionError, PlanningRunCreationError) as exc:
            raise DraftIntentEditError(exc.code) from exc

    def resolve_draft_intent_clarification(
        self,
        *,
        trip_id: str,
        capability: str | None,
        question_id: str,
        idempotency_key: str | None,
        payload: DraftClarificationResolveRequest,
    ) -> DraftIntentEditResponse:
        self._require_trip_access(trip_id, capability)
        # Resolve against the requested immutable revision. The shared edit
        # transaction checks idempotency before stale state, preserving safe retries.
        parent = self.repository.get_draft_intent_revision(
            trip_id=trip_id,
            revision_id=payload.base_intent_revision_id,
        )
        envelope = SourceLinkedTripIntentEnvelope.model_validate(parent.envelope)
        question = next((item for item in envelope.clarification_queue if item.question_id == question_id), None)
        if question is None:
            raise ClarificationAlreadyResolvedError()
        if not question.blocking or question.resolution_kind.value not in {"inline_answer", "edit_contract"}:
            raise DraftIntentEditError("clarification_not_editable")
        operation = clarification_answer_to_operation(payload.answer)
        try:
            return self.edit_draft_intent(
                trip_id=trip_id,
                capability=capability,
                idempotency_key=idempotency_key,
                payload=DraftIntentEditRequest(
                    base_intent_revision_id=payload.base_intent_revision_id,
                    base_draft_version=payload.base_draft_version,
                    operations=[operation],
                    clarification_resolution_id=question_id,
                ),
            )
        except (StaleIntentRevisionError, StaleDraftRevisionError):
            latest = self.repository.get_latest_draft_intent_revision(trip_id=trip_id)
            if latest is not None:
                latest_envelope = SourceLinkedTripIntentEnvelope.model_validate(latest.envelope)
                if not any(item.question_id == question_id for item in latest_envelope.clarification_queue):
                    raise ClarificationAlreadyResolvedError() from None
            raise

    def _validate_draft_edit_candidates(self, candidate_ids: list[str], states: dict[str, str], verification: dict[str, str]) -> None:
        for candidate_id in candidate_ids:
            if states.get(candidate_id) in {"rejected", "deferred"}:
                raise DraftIntentEditError("candidate_not_eligible")
            if verification.get(candidate_id) == "legacy_unverified":
                raise DraftIntentEditError("candidate_provenance_invalid")

    def preview_preplan_handoff(self, *, trip_id: str, capability: str | None, payload: PrePlanHandoffPreviewRequest) -> PrePlanHandoffPreviewResponse:
        trip = self._require_trip_access(trip_id, capability)
        if trip.planning_phase != TripPlanningPhase.DRAFT.value or trip.current_revision_id is not None:
            raise InvalidRevisionOperationError("Pre-plan handoff is only available for a Draft Trip.")
        draft = self.repository.get_draft_intent_revision(trip_id=trip_id, revision_id=payload.draft_intent_revision_id)
        latest = self.repository.get_latest_draft_intent_revision(trip_id=trip_id)
        if latest is None or latest.id != draft.id:
            raise StaleIntentRevisionError(trip_id=trip_id, provided_intent_revision_id=draft.id, current_intent_revision_id=latest.id if latest else "")
        envelope = SourceLinkedTripIntentEnvelope.model_validate(draft.envelope)
        handoff = build_planner_handoff_input(envelope=envelope, candidates=self.repository.list_candidates(trip_id=trip_id))
        run_id = f"preplan_handoff_{uuid4().hex}"
        collector = PlannerTraceCollector(planner_run_id=run_id, input_summary=build_planner_input_snapshot(handoff.handoff.itinerary_request), strict=True, volatile_metadata={"draft_intent_revision_id": draft.id, "handoff_input_digest": handoff.handoff.digest})
        record_handoff_trace_context(collector, handoff=handoff.handoff, candidate_links=handoff.field_links_by_candidate_id)
        itinerary = attach_handoff_source_links(build_itinerary_response(handoff.handoff.itinerary_request, intent_source=TripIntentEnvelopeSource.REGENERATE, trace_collector=collector), candidate_links=handoff.field_links_by_candidate_id, collector=collector)
        snapshot = ensure_stable_item_ids(serialize_itinerary_snapshot(itinerary))
        stored_itinerary = deserialize_itinerary_snapshot(snapshot)
        trace = collector.build_trace(build_planner_result_summary(stored_itinerary))
        trace = trace.model_copy(update={"trace_digest": planner_trace_digest(trace)})
        validation = build_mutation_validation_report(itinerary=stored_itinerary, trace=trace)
        assert_mutation_validation_passed(validation)
        now = self.clock()
        run = PrePlanHandoffRunRecord(
            id=run_id, trip_id=trip_id, draft_intent_revision_id=draft.id,
            intent_semantic_digest=handoff.handoff.intent_semantic_digest, intent_lineage_digest=handoff.handoff.intent_lineage_digest,
            input_snapshot=handoff.handoff.model_dump(mode="json"), input_digest=handoff.handoff.digest,
            planner_version=trace.planner_version, trace_schema_version=trace.schema_version,
            trace_snapshot=trace.model_dump(mode="json"), trace_digest=trace.trace_digest or "",
            result_snapshot=snapshot, result_content_digest=itinerary_content_digest(snapshot), validation_report=validation,
            status="pending", expires_at=format_utc(now + timedelta(seconds=get_trip_replan_proposal_ttl_seconds())),
            applied_revision_id=None, created_at=format_utc(now), updated_at=format_utc(now),
        )
        run = self.repository.create_preplan_handoff_run(run=run)
        return PrePlanHandoffPreviewResponse(trip=TripMetadata.from_record(trip), draft_intent_revision_id=draft.id, handoff=PrePlanHandoffRunMetadata.from_record(run), itinerary=stored_itinerary, source_links=[item.model_dump(mode="json") for item in handoff.handoff.source_links])

    def apply_preplan_handoff(self, *, trip_id: str, run_id: str, capability: str | None, idempotency_key: str | None, payload: PrePlanHandoffApplyRequest) -> PrePlanHandoffApplyResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        run = self.repository.get_preplan_handoff_run(trip_id=trip_id, run_id=run_id)
        preview_itinerary = deserialize_itinerary_snapshot(run.result_snapshot)
        if preview_itinerary.planner_realism and preview_itinerary.planner_realism.status == "unstable":
            raise InvalidRevisionOperationError(
                "The route preview has unresolved execution conflicts and cannot be saved yet."
            )
        result = self.repository.activate_preplan_handoff(
            trip_id=trip_id, capability_hash=trip.capability_hash, run_id=run_id,
            draft_intent_revision_id=payload.draft_intent_revision_id, handoff_digest=payload.handoff_digest,
            now=format_utc(self.clock()),
            request_digest=request_digest({"operation": "apply_preplan_handoff", "trip_id": trip_id, "run_id": run_id, "draft_intent_revision_id": payload.draft_intent_revision_id, "handoff_digest": payload.handoff_digest}),
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
            operation_metadata={"operation_type": "apply_preplan_intent_handoff", "preplan_handoff_run_id": run.id, "draft_intent_revision_id": run.draft_intent_revision_id, "intent_semantic_digest": run.intent_semantic_digest, "intent_lineage_digest": run.intent_lineage_digest, "trace_digest": run.trace_digest},
        )
        current_trip = self.repository.get_trip(trip_id)
        applied = self.repository.get_preplan_handoff_run(trip_id=trip_id, run_id=run_id)
        return PrePlanHandoffApplyResponse(trip=TripMetadata.from_record(current_trip), current_revision=TripRevisionMetadata.from_record(result.revision), draft_intent_revision_id=run.draft_intent_revision_id, handoff=PrePlanHandoffRunMetadata.from_record(applied), itinerary=deserialize_itinerary_snapshot(result.revision.itinerary_snapshot), persistence=TripPersistenceInfo(idempotent_replay=result.idempotent_replay))

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
        evidence_links = [
            CandidateEvidenceLinkRecord(
                id=f"candidate_evidence_{uuid4().hex}",
                trip_id=trip_id,
                trip_candidate_id=candidate.id,
                source_artifact_id=item.source_artifact_id,
                import_job_id=item.import_job_id,
                mention_id=item.mention_id,
                review_decision_id=item.review_decision_id,
                resolution_candidate_id=item.resolution_candidate_id,
                document_generation_id=item.document_generation_id,
                document_page_number=item.document_page_number,
                document_span_id=item.document_span_id,
                bounding_boxes=list(item.bounding_boxes),
                source_digest=item.source_digest,
                created_at=now,
            )
            for item in payload.evidence_links
        ]
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
            evidence_links=evidence_links,
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
        replay = self._intent_idempotent_replay(
            trip_id=trip_id,
            payload=payload,
            idempotency_key=idempotency_key,
            operation="compile_trip_intent_envelope",
            parent_intent_revision_id=payload.base_intent_revision_id,
        )
        if replay is not None:
            return replay
        latest_intent_revision = self.repository.get_latest_intent_revision(trip_id=trip_id)
        latest_id = latest_intent_revision.id if latest_intent_revision else None
        if latest_id != payload.base_intent_revision_id:
            raise StaleIntentRevisionError(
                trip_id=trip_id,
                provided_intent_revision_id=payload.base_intent_revision_id or "",
                current_intent_revision_id=latest_id or "",
            )
        current_revision = self.repository.get_revision(trip_id, trip.current_revision_id)
        if current_revision.id != payload.base_revision_id:
            raise StaleBaseRevisionError(
                trip_id=trip_id,
                provided_base_revision_id=payload.base_revision_id,
                current_revision_id=current_revision.id,
            )
        parser_result = self._build_intent_proposal_parse_result(payload)
        return self._create_intent_revision_from_request(
            trip_id=trip_id,
            current_revision=current_revision,
            parent_intent_revision=latest_intent_revision,
            parent_intent_snapshot=latest_intent_revision.envelope if latest_intent_revision else None,
            payload=payload,
            parser_result=parser_result,
            idempotency_key=idempotency_key,
            operation="compile_trip_intent_envelope",
            require_latest_parent=True,
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
        replay = self._intent_idempotent_replay(
            trip_id=trip_id,
            payload=payload,
            idempotency_key=idempotency_key,
            operation="edit_trip_intent_envelope",
            parent_intent_revision_id=payload.base_intent_revision_id,
        )
        if replay is not None:
            return replay
        current_revision = self.repository.get_revision(trip_id, trip.current_revision_id)
        if current_revision.id != payload.base_revision_id:
            raise StaleBaseRevisionError(
                trip_id=trip_id,
                provided_base_revision_id=payload.base_revision_id,
                current_revision_id=current_revision.id,
            )
        parent = self.repository.get_intent_revision(trip_id=trip_id, revision_id=revision_id)
        if parent.id != payload.base_intent_revision_id:
            raise StaleIntentRevisionError(
                trip_id=trip_id,
                provided_intent_revision_id=payload.base_intent_revision_id,
                current_intent_revision_id=parent.id,
            )
        request = CompileTripIntentRequest(
            base_trip_revision_id=payload.base_revision_id,
            base_intent_revision_id=payload.base_intent_revision_id,
            structured_overrides=payload.field_updates,
        )
        return self._create_intent_revision_from_request(
            trip_id=trip_id,
            current_revision=current_revision,
            parent_intent_revision=parent,
            parent_intent_snapshot=parent.envelope,
            payload=request,
            parser_result=self._build_intent_proposal_parse_result(request),
            idempotency_key=idempotency_key,
            operation="edit_trip_intent_envelope",
            require_latest_parent=True,
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
        parent = self.repository.get_intent_revision(trip_id=trip_id, revision_id=revision_id)
        parent_envelope = SourceLinkedTripIntentEnvelope.model_validate(parent.envelope)
        question = next(
            (item for item in parent_envelope.clarification_queue if item.question_id == question_id),
            None,
        )
        if question is None:
            raise InvalidRevisionOperationError("Unsupported clarification question.")
        if question.resolution_kind != IntentClarificationResolutionKind.INLINE_ANSWER:
            raise InvalidRevisionOperationError(
                "This clarification must be resolved through its typed contract or evidence-review workflow."
            )
        field_updates = _field_updates_from_clarification(question, payload.answer)
        return self.edit_intent_envelope(
            trip_id=trip_id,
            capability=capability,
            revision_id=revision_id,
            idempotency_key=idempotency_key,
            payload=EditTripIntentEnvelopeRequest(
                base_trip_revision_id=payload.base_revision_id,
                base_intent_revision_id=payload.base_intent_revision_id,
                field_updates=field_updates,
            ),
        )

    def restore_intent_envelope(
        self,
        *,
        trip_id: str,
        capability: str | None,
        revision_id: str,
        idempotency_key: str | None,
        payload: RestoreTripIntentEnvelopeRequest,
    ) -> CompileTripIntentResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        replay = self._intent_idempotent_replay(
            trip_id=trip_id,
            payload=payload,
            idempotency_key=idempotency_key,
            operation="restore_trip_intent_envelope",
            parent_intent_revision_id=payload.base_intent_revision_id,
        )
        if replay is not None:
            return replay
        current_revision = self.repository.get_revision(trip_id, trip.current_revision_id)
        if current_revision.id != payload.base_revision_id:
            raise StaleBaseRevisionError(
                trip_id=trip_id,
                provided_base_revision_id=payload.base_revision_id,
                current_revision_id=current_revision.id,
            )
        target = self.repository.get_intent_revision(trip_id=trip_id, revision_id=revision_id)
        latest = self.repository.get_latest_intent_revision(trip_id=trip_id)
        latest_id = latest.id if latest else None
        if latest_id != payload.base_intent_revision_id:
            raise StaleIntentRevisionError(
                trip_id=trip_id,
                provided_intent_revision_id=payload.base_intent_revision_id,
                current_intent_revision_id=latest_id or "",
            )
        request = CompileTripIntentRequest(
            base_trip_revision_id=payload.base_revision_id,
            base_intent_revision_id=payload.base_intent_revision_id,
        )
        return self._create_intent_revision_from_request(
            trip_id=trip_id,
            current_revision=current_revision,
            parent_intent_revision=latest,
            parent_intent_snapshot=target.envelope,
            payload=request,
            parser_result=self._build_intent_proposal_parse_result(request),
            idempotency_key=idempotency_key,
            operation="restore_trip_intent_envelope",
            require_latest_parent=latest is not None,
            validation_report_updates={
                "restored_from_intent_revision_id": target.id,
                "restore_target_revision_number": target.revision_number,
            },
        )

    def _intent_idempotent_replay(
        self,
        *,
        trip_id: str,
        payload,
        idempotency_key: str,
        operation: str,
        parent_intent_revision_id: str | None,
    ) -> CompileTripIntentResponse | None:
        req_digest = request_digest(
            {
                "operation": operation,
                "trip_id": trip_id,
                "base_revision_id": payload.base_revision_id,
                "parent_intent_revision_id": parent_intent_revision_id,
                "payload": self._intent_digest_payload_for_operation(payload, operation),
            }
        )
        replay = self.repository.get_intent_revision_by_idempotency(
            trip_id=trip_id,
            request_digest=req_digest,
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
        )
        if replay is None:
            return None
        return CompileTripIntentResponse(
            envelope=SourceLinkedTripIntentEnvelope.model_validate(replay.revision.envelope),
            revision=intent_revision_metadata(replay.revision),
            idempotent_replay=True,
        )

    def _build_intent_proposal_parse_result(
        self,
        payload: CompileTripIntentRequest,
    ) -> IntentProposalParseResult:
        if not payload.direct_user_text and payload.llm_proposal is None and not payload.use_llm_proposal_adapter:
            return IntentProposalParseResult(
                status="empty_input",
                proposal=None,
                parser_name="intent_contract_compiler",
                parser_version=TRIP_INTENT_COMPILER_VERSION,
                model_name=None,
                warning_codes=[],
            )
        if payload.use_llm_proposal_adapter and payload.llm_proposal is None and payload.direct_user_text:
            try:
                return IntentProposalParseResult(
                    status="success",
                    proposal=build_untrusted_llm_intent_proposal(payload.direct_user_text),
                    parser_name="llm_intent_proposal_adapter",
                    parser_version=TRIP_INTENT_COMPILER_VERSION,
                    model_name=None,
                    warning_codes=[
                        "llm_proposal_adapter_output_was_untrusted_and_deterministically_recompiled"
                    ],
                )
            except TimeoutError:
                return IntentProposalParseResult(
                    status="timeout",
                    proposal=None,
                    parser_name="llm_intent_proposal_adapter",
                    parser_version=TRIP_INTENT_COMPILER_VERSION,
                    model_name=None,
                    warning_codes=["llm_adapter_timeout"],
                )
            except ValueError:
                return IntentProposalParseResult(
                    status="invalid_output",
                    proposal=None,
                    parser_name="llm_intent_proposal_adapter",
                    parser_version=TRIP_INTENT_COMPILER_VERSION,
                    model_name=None,
                    warning_codes=["llm_adapter_invalid_output"],
                )
            except RuntimeError:
                return IntentProposalParseResult(
                    status="provider_error",
                    proposal=None,
                    parser_name="llm_intent_proposal_adapter",
                    parser_version=TRIP_INTENT_COMPILER_VERSION,
                    model_name=None,
                    warning_codes=["llm_adapter_provider_error"],
                )
        return IntentProposalParseResult(
            status="success",
            proposal=payload.llm_proposal,
            parser_name="deterministic_text_fallback",
            parser_version=TRIP_INTENT_COMPILER_VERSION,
            model_name=None,
            warning_codes=[],
        )

    def _intent_digest_payload_for_operation(self, payload, operation: str) -> dict[str, Any]:
        if operation == "edit_trip_intent_envelope" and hasattr(payload, "field_updates"):
            return CompileTripIntentRequest(
                base_trip_revision_id=payload.base_revision_id,
                base_intent_revision_id=payload.base_intent_revision_id,
                structured_overrides=payload.field_updates,
            ).model_dump(mode="json")
        if operation == "restore_trip_intent_envelope":
            return CompileTripIntentRequest(
                base_trip_revision_id=payload.base_revision_id,
                base_intent_revision_id=payload.base_intent_revision_id,
            ).model_dump(mode="json")
        return payload.model_dump(mode="json")

    def _verified_candidate_source_refs(
        self,
        trip_id: str,
        candidates: list[TripCandidateRecord],
    ) -> tuple[dict[str, list], dict[str, str]]:
        from .intent_provenance import VerifiedIntentEvidenceAssembler

        result: dict[str, list] = {}
        verification_states: dict[str, str] = {}
        if self.import_repository is not None:
            assembler = VerifiedIntentEvidenceAssembler(
                trip_repository=self.repository,
                import_repository=self.import_repository,
            )
            for candidate in candidates:
                if candidate.source_kind not in {
                    CandidateSourceKind.TEXT_IMPORT,
                    CandidateSourceKind.URL_IMPORT,
                    CandidateSourceKind.DOCUMENT_IMPORT,
                }:
                    result[candidate.id] = []
                    verification_states[candidate.id] = "not_applicable"
                    continue
                assembly = assembler.assemble_candidate_evidence(
                    trip_id=trip_id,
                    trip_candidate_id=candidate.id,
                )
                result[candidate.id] = assembly.refs
                verification_states[candidate.id] = assembly.verification_state
            return result, verification_states
        for candidate in candidates:
            result[candidate.id] = []
            verification_states[candidate.id] = (
                "legacy_unverified"
                if candidate.source_kind
                in {
                    CandidateSourceKind.TEXT_IMPORT,
                    CandidateSourceKind.URL_IMPORT,
                    CandidateSourceKind.DOCUMENT_IMPORT,
                }
                else "not_applicable"
            )
        return result, verification_states

    def _create_intent_revision_from_request(
        self,
        *,
        trip_id: str,
        current_revision,
        parent_intent_revision: TripIntentRevisionRecord | None,
        parent_intent_snapshot: dict[str, Any] | None,
        payload: CompileTripIntentRequest,
        parser_result: IntentProposalParseResult,
        idempotency_key: str,
        operation: str,
        require_latest_parent: bool = False,
        validation_report_updates: dict[str, Any] | None = None,
    ) -> CompileTripIntentResponse:
        candidates, candidate_workflow_states, candidate_preferences = self._intent_candidate_context(trip_id, payload)
        verified_source_refs, candidate_verification_states = self._verified_candidate_source_refs(trip_id, candidates)
        now = format_utc(self.clock())
        req_digest = request_digest(
            {
                "operation": operation,
                "trip_id": trip_id,
                "base_revision_id": current_revision.id,
                "parent_intent_revision_id": parent_intent_revision.id if parent_intent_revision else None,
                "payload": payload.model_dump(mode="json"),
            }
        )
        idempotency_key_hash = hash_idempotency_key(idempotency_key.strip())
        if require_latest_parent and parent_intent_revision is not None:
            latest = self.repository.get_latest_intent_revision(trip_id=trip_id)
            if latest is not None and latest.id != parent_intent_revision.id:
                raise StaleIntentRevisionError(
                    trip_id=trip_id,
                    provided_intent_revision_id=parent_intent_revision.id,
                    current_intent_revision_id=latest.id,
                )
        envelope = compile_source_linked_intent(
            trip_id=trip_id,
            base_revision_id=current_revision.id,
            parent_intent_revision_id=parent_intent_revision.id if parent_intent_revision else None,
            next_revision_number=0,
            created_at=now,
            request=payload,
            parser_result=parser_result,
            existing_trip_snapshot=current_revision.itinerary_snapshot,
            parent_intent_snapshot=parent_intent_snapshot,
            candidates=candidates,
            candidate_workflow_states=candidate_workflow_states,
            candidate_preferences=candidate_preferences,
            verified_candidate_source_refs=verified_source_refs,
            candidate_verification_states=candidate_verification_states,
        )
        if validation_report_updates:
            envelope.validation_report.update(validation_report_updates)
            envelope.content_digest = request_digest(
                envelope.model_dump(mode="json", exclude={"content_digest"})
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
        compile_run = IntentCompileRunDraft(
            id=f"intent_run_{uuid4().hex}",
            trip_id=trip_id,
            operation=operation,
            base_trip_revision_id=current_revision.id,
            base_intent_revision_id=parent_intent_revision.id if parent_intent_revision else None,
            parser_status=parser_result.status,
            parser_name=parser_result.parser_name,
            parser_version=parser_result.parser_version,
            model_name=parser_result.model_name,
            compiler_version=TRIP_INTENT_COMPILER_VERSION,
            precedence_version=INTENT_PRECEDENCE_VERSION,
            readiness_policy_version=INTENT_READINESS_POLICY_VERSION,
            date_policy_version=INTENT_DATE_POLICY_VERSION,
            input_digest=req_digest,
            proposal_digest=(
                request_digest(parser_result.proposal.model_dump(mode="json"))
                if parser_result.proposal is not None
                else None
            ),
            status="completed"
            if parser_result.status in {"success", "empty_input"}
            else "parser_degraded",
            warning_codes=list(parser_result.warning_codes),
            error_code=None if parser_result.status in {"success", "empty_input"} else parser_result.status,
            created_at=now,
        )
        result = self.repository.create_intent_revision(
            revision=record,
            compile_run=compile_run,
            operation=operation,
            restore_source_revision_id=validation_report_updates.get("restored_from_intent_revision_id") if validation_report_updates else None,
            request_digest=req_digest,
            idempotency_key_hash=idempotency_key_hash,
            expected_parent_intent_revision_id=parent_intent_revision.id if parent_intent_revision else None,
            require_latest_parent=require_latest_parent,
            expected_base_revision_id=current_revision.id,
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
        envelope = authoritative_safe_replace_envelope(
            base_snapshot=base_revision.itinerary_snapshot,
            envelope=envelope,
        )
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
        # A controlled patch is derived from an existing revision, not a new
        # planner run. Preserve the original planning lineage on its proposal
        # and resulting revision so a later repair remains traceable to the
        # candidate selection that created Revision 1.
        root_planner_run_id = base_revision.planner_run_id
        root_planner_version = base_revision.planner_version
        root_trace_schema_version = base_revision.trace_schema_version
        root_trace_digest = base_revision.trace_digest
        proposal_digest = mutation_proposal_digest(
            proposal_schema_version=TRIP_MUTATION_PROPOSAL_SCHEMA_VERSION,
            trip_id=trip_id,
            base_revision_id=envelope.base_revision_id,
            source_type=source_type,
            operation_type=operation_type,
            request_digest=req_digest,
            preview_snapshot_schema_version=TRIP_SNAPSHOT_SCHEMA_VERSION,
            preview_content_digest=preview.content_digest,
            planner_run_id=root_planner_run_id,
            planner_version=root_planner_version,
            trace_schema_version=root_trace_schema_version,
            trace_digest=root_trace_digest,
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
                planner_run_id=root_planner_run_id,
                planner_version=root_planner_version,
                trace_schema_version=root_trace_schema_version,
                trace_digest=root_trace_digest,
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

    def preview_local_repair(
        self,
        *,
        trip_id: str,
        capability: str | None,
        payload: LocalRepairPreviewRequest,
    ) -> PersistedMutationPreviewResponse:
        """Turn a user goal into one constrained typed command on the server."""

        trip = self._require_trip_access(trip_id, capability)
        base_revision = self.repository.get_revision(trip_id, payload.base_revision_id)
        if trip.current_revision_id != payload.base_revision_id:
            raise StaleMutationProposalError(
                trip_id=trip_id,
                proposal_id="pending",
                base_revision_id=payload.base_revision_id,
                current_revision_id=trip.current_revision_id,
            )
        # The golden-path selector is the canonical safe local repair policy. It
        # chooses a movable system suggestion and lets the typed command engine
        # re-slot it in the receiving day; do not retain a second time-slot policy.
        from .golden_path_repair import build_relax_day_envelope as build_safe_relax_day_envelope

        envelope, repair_selection = build_safe_relax_day_envelope(
            snapshot=base_revision.itinerary_snapshot,
            base_revision_id=payload.base_revision_id,
            target_day=payload.target_day,
        )
        result = self.preview_typed_mutation(

            trip_id=trip_id,
            capability=capability,
            payload=PersistedMutationPreviewRequest.model_validate(envelope.model_dump(mode="json")),
        )
        result.impact_summary["local_repair"] = {
            "action": "move",
            "stop_name": repair_selection.stop_name,
            "from_day": repair_selection.from_day,
            "to_day": repair_selection.to_day,
            "ownership": "system_suggested",
            "protected": {
                "fixed_mutations": 0,
                "must_moves": 0,
                "must_deletions": 0,
                "full_planner_calls": 0,
            },
        }
        return result

    def preview_golden_path_repair(self, *, trip_id: str, capability: str | None, payload):
        """Create a server-authored, bounded relaxation proposal."""
        from .golden_path_repair import build_relax_day_envelope
        from .schemas import GoldenPathRepairPreviewResponse, GoldenPathRepairProposal

        trip = self._require_trip_access(trip_id, capability)
        if trip.current_revision_id != payload.base_revision:
            raise StaleMutationProposalError(
                trip_id=trip_id, proposal_id="pending", base_revision_id=payload.base_revision,
                current_revision_id=trip.current_revision_id or "",
            )
        base = self.repository.get_revision(trip_id, payload.base_revision)
        envelope, selection = build_relax_day_envelope(
            snapshot=base.itinerary_snapshot, base_revision_id=base.id, target_day=payload.target_day,
        )
        # Reuse the standard persistence logic after the server, not the browser, authored the command.
        preview = self.preview_typed_mutation(
            trip_id=trip_id,
            capability=capability,
            payload=PersistedMutationPreviewRequest.model_validate(envelope.model_dump(mode="json")),
        )
        proposal = GoldenPathRepairProposal(
            proposal_id=preview.proposal.id,
            proposal_digest=preview.proposal.proposal_digest,
            base_revision=base.id,
            target_day=payload.target_day,
            moved_activity_id=selection.stop_id,
            moved_activity_name=selection.stop_name,
            from_day=selection.from_day,
            to_day=selection.to_day,
            before=deserialize_itinerary_snapshot(base.itinerary_snapshot),
            after=preview.itinerary,
            protection_summary="固定安排和你明确想去的地点没有移动；没有重新生成全部行程。",
            execution_evidence={"parser_calls": 0, "llm_calls": 0, "full_planner_calls": 0, "route_provider_calls": 0},
        )
        return GoldenPathRepairPreviewResponse(
            trip=preview.trip, current_revision=preview.current_revision, proposal=proposal,
        )

    def apply_golden_path_repair(self, *, trip_id: str, proposal_id: str, capability: str | None, idempotency_key: str | None, payload):
        from .schemas import ApplyPersistedMutationProposalRequest, GoldenPathRepairApplyResponse

        applied = self.apply_mutation_proposal(
            trip_id=trip_id, proposal_id=proposal_id, capability=capability, idempotency_key=idempotency_key,
            payload=ApplyPersistedMutationProposalRequest(
                base_revision_id=payload.base_revision, proposal_digest=payload.proposal_digest,
            ),
        )
        return GoldenPathRepairApplyResponse(
            trip=applied.trip, current_revision=applied.current_revision,
            itinerary=applied.itinerary, persistence=applied.persistence,
        )

    def preview_planner_handoff(
        self,
        *,
        trip_id: str,
        capability: str | None,
        payload: PlannerHandoffPreviewRequest,
    ) -> PlannerHandoffPreviewResponse:
        trip = self._require_trip_access(trip_id, capability)
        if trip.current_revision_id != payload.base_revision_id:
            raise StaleBaseRevisionError(
                trip_id=trip_id,
                provided_base_revision_id=payload.base_revision_id,
                current_revision_id=trip.current_revision_id,
            )
        intent_revision = self.repository.get_intent_revision(
            trip_id=trip_id,
            revision_id=payload.intent_revision_id,
        )
        latest_intent_revision = self.repository.get_latest_intent_revision(trip_id=trip_id)
        if latest_intent_revision is None or latest_intent_revision.id != intent_revision.id:
            raise StaleIntentRevisionError(
                trip_id=trip_id,
                provided_intent_revision_id=payload.intent_revision_id,
                current_intent_revision_id=latest_intent_revision.id if latest_intent_revision else "",
            )
        envelope = SourceLinkedTripIntentEnvelope.model_validate(intent_revision.envelope)
        if envelope.base_trip_revision_id != payload.base_revision_id:
            raise StaleBaseRevisionError(
                trip_id=trip_id,
                provided_base_revision_id=envelope.base_trip_revision_id,
                current_revision_id=payload.base_revision_id,
            )
        handoff_result = build_planner_handoff_input(
            envelope=envelope,
            candidates=self.repository.list_candidates(trip_id=trip_id),
        )
        run_id = f"planner_handoff_{uuid4().hex}"
        trace_collector = PlannerTraceCollector(
            planner_run_id=run_id,
            input_summary=build_planner_input_snapshot(handoff_result.handoff.itinerary_request),
            strict=True,
            volatile_metadata={
                "handoff_input_digest": handoff_result.handoff.digest,
                "intent_revision_id": envelope.id,
                "intent_semantic_digest": handoff_result.handoff.intent_semantic_digest,
            },
        )
        record_handoff_trace_context(
            trace_collector,
            handoff=handoff_result.handoff,
            candidate_links=handoff_result.field_links_by_candidate_id,
        )
        itinerary = build_itinerary_response(
            handoff_result.handoff.itinerary_request,
            intent_source=TripIntentEnvelopeSource.REGENERATE,
            trace_collector=trace_collector,
        )
        itinerary = attach_handoff_source_links(
            itinerary,
            candidate_links=handoff_result.field_links_by_candidate_id,
            collector=trace_collector,
        )
        snapshot = ensure_stable_item_ids(serialize_itinerary_snapshot(itinerary))
        stored_itinerary = deserialize_itinerary_snapshot(snapshot)
        trace = trace_collector.build_trace(build_planner_result_summary(stored_itinerary))
        trace = trace.model_copy(update={"trace_digest": planner_trace_digest(trace)})
        validation_report = build_mutation_validation_report(itinerary=stored_itinerary, trace=trace)
        assert_mutation_validation_passed(validation_report)
        now = self.clock()
        expires_at = format_utc(now + timedelta(seconds=get_trip_replan_proposal_ttl_seconds()))
        req_digest = request_digest(
            {
                "operation": "planner_intent_handoff_preview",
                "base_revision_id": payload.base_revision_id,
                "intent_revision_id": payload.intent_revision_id,
                "handoff_input_digest": handoff_result.handoff.digest,
            }
        )
        proposal_digest = mutation_proposal_digest(
            proposal_schema_version=TRIP_MUTATION_PROPOSAL_SCHEMA_VERSION,
            trip_id=trip_id,
            base_revision_id=payload.base_revision_id,
            source_type=RevisionSourceType.PLANNER_INTENT_HANDOFF.value,
            operation_type="apply_planner_intent_handoff",
            request_digest=req_digest,
            preview_snapshot_schema_version=TRIP_SNAPSHOT_SCHEMA_VERSION,
            preview_content_digest=itinerary_content_digest(snapshot),
            planner_run_id=run_id,
            planner_version=trace.planner_version,
            trace_schema_version=trace.schema_version,
            trace_digest=trace.trace_digest,
            validation_report=validation_report,
            expires_at=expires_at,
            execution_kind="planner_handoff_snapshot",
        )
        proposal = TripMutationProposalRecord(
            id=generate_proposal_id(),
            trip_id=trip_id,
            base_revision_id=payload.base_revision_id,
            proposal_schema_version=TRIP_MUTATION_PROPOSAL_SCHEMA_VERSION,
            source_type=RevisionSourceType.PLANNER_INTENT_HANDOFF.value,
            operation_type="apply_planner_intent_handoff",
            request_digest=req_digest,
            instruction_digest=None,
            preview_snapshot_schema_version=TRIP_SNAPSHOT_SCHEMA_VERSION,
            preview_snapshot=snapshot,
            preview_content_digest=itinerary_content_digest(snapshot),
            proposal_digest=proposal_digest,
            planner_run_id=run_id,
            planner_version=trace.planner_version,
            trace_schema_version=trace.schema_version,
            trace_digest=trace.trace_digest,
            validation_report=validation_report,
            execution_kind="planner_handoff_snapshot",
            command_schema_version=None,
            mutation_engine_version=None,
            mutation_kind=None,
            commands=None,
            command_digest=None,
            impact_summary={"intent_revision_id": envelope.id, "source_link_count": len(handoff_result.handoff.source_links)},
            invalidated_surfaces=["route_workspace", "trip_readiness", "planner_trace"],
            status=ProposalStatus.PENDING.value,
            expires_at=expires_at,
            applied_revision_id=None,
            created_at=format_utc(now),
            updated_at=format_utc(now),
        )
        run = PlannerHandoffRunRecord(
            id=run_id,
            trip_id=trip_id,
            base_trip_revision_id=payload.base_revision_id,
            intent_revision_id=envelope.id,
            intent_semantic_digest=handoff_result.handoff.intent_semantic_digest,
            intent_lineage_digest=handoff_result.handoff.intent_lineage_digest,
            input_schema_version=PLANNER_HANDOFF_INPUT_SCHEMA_VERSION,
            input_snapshot=handoff_result.handoff.model_dump(mode="json"),
            input_digest=handoff_result.handoff.digest,
            planner_version=trace.planner_version,
            trace_schema_version=trace.schema_version,
            trace_snapshot=trace.model_dump(mode="json"),
            trace_digest=trace.trace_digest or "",
            result_snapshot_schema_version=TRIP_SNAPSHOT_SCHEMA_VERSION,
            result_snapshot=snapshot,
            result_content_digest=itinerary_content_digest(snapshot),
            validation_report=validation_report,
            proposal_id=proposal.id,
            status=ProposalStatus.PENDING.value,
            applied_revision_id=None,
            created_at=format_utc(now),
            updated_at=format_utc(now),
        )
        run, proposal = self.repository.create_planner_handoff_preview(run=run, proposal=proposal)
        return PlannerHandoffPreviewResponse(
            trip=TripMetadata.from_record(trip),
            current_revision=TripRevisionMetadata.from_record(self.repository.get_revision(trip_id, payload.base_revision_id)),
            intent_revision_id=envelope.id,
            planner_run=PlannerHandoffRunMetadata.from_record(run),
            proposal=MutationProposalMetadata.from_record(proposal),
            itinerary=stored_itinerary,
            source_links=[link.model_dump(mode="json") for link in handoff_result.handoff.source_links],
        )

    def apply_planner_handoff_proposal(
        self,
        *,
        trip_id: str,
        proposal_id: str,
        capability: str | None,
        idempotency_key: str | None,
        payload: ApplyPlannerHandoffProposalRequest,
    ) -> PlannerHandoffApplyResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRevisionOperationError("X-Idempotency-Key is required.")
        trip = self._require_trip_access(trip_id, capability)
        proposal = self.repository.get_mutation_proposal(trip_id=trip_id, proposal_id=proposal_id)
        if proposal.execution_kind != "planner_handoff_snapshot":
            raise InvalidRevisionOperationError("Mutation proposal is not a planner handoff proposal.")
        if payload.base_revision_id != proposal.base_revision_id or payload.proposal_digest != proposal.proposal_digest:
            raise ProposalDigestMismatchError()
        run = self.repository.get_planner_handoff_run(trip_id=trip_id, run_id=proposal.planner_run_id or "")
        if run.intent_revision_id != payload.intent_revision_id:
            raise ProposalDigestMismatchError()
        req_digest = request_digest(
            {
                "operation": "apply_planner_intent_handoff",
                "proposal_id": proposal_id,
                "base_revision_id": payload.base_revision_id,
                "intent_revision_id": payload.intent_revision_id,
                "proposal_digest": payload.proposal_digest,
            }
        )
        result = self.repository.apply_mutation_proposal(
            trip_id=trip_id,
            capability_hash=trip.capability_hash,
            proposal_id=proposal_id,
            base_revision_id=payload.base_revision_id,
            proposal_digest=payload.proposal_digest,
            now=format_utc(self.clock()),
            operation_summary="Applied a deterministic planner run from a confirmed intent contract.",
            operation_metadata={
                "operation_type": "apply_planner_intent_handoff",
                "planner_handoff_run_id": run.id,
                "intent_revision_id": run.intent_revision_id,
                "intent_semantic_digest": run.intent_semantic_digest,
                "intent_lineage_digest": run.intent_lineage_digest,
                "planner_input_digest": run.input_digest,
                "trace_digest": run.trace_digest,
                "proposal_digest": proposal.proposal_digest,
            },
            request_digest=req_digest,
            idempotency_key_hash=hash_idempotency_key(idempotency_key.strip()),
            expected_intent_revision_id=payload.intent_revision_id,
        )
        if result.revision.content_digest != run.result_content_digest:
            raise PreviewApplyMismatchError()
        current_trip = self.repository.get_trip(trip_id)
        applied_run = self.repository.get_planner_handoff_run(trip_id=trip_id, run_id=run.id)
        return PlannerHandoffApplyResponse(
            trip=TripMetadata.from_record(current_trip),
            current_revision=TripRevisionMetadata.from_record(result.revision),
            intent_revision_id=run.intent_revision_id,
            planner_run=PlannerHandoffRunMetadata.from_record(applied_run),
            itinerary=deserialize_itinerary_snapshot(result.revision.itinerary_snapshot),
            persistence=TripPersistenceInfo(idempotent_replay=result.idempotent_replay),
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
        if proposal.planner_run_id is not None:
            operation_metadata["root_planning_run_id"] = proposal.planner_run_id
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
        current_revision = self.repository.get_current_revision(trip_id)
        validate_restore_preserves_fixed_items(
            current_snapshot=current_revision.itinerary_snapshot,
            target_snapshot=target_revision.itinerary_snapshot,
        )
        validate_restore_preserves_must_visit_places(
            current_snapshot=current_revision.itinerary_snapshot,
            target_snapshot=target_revision.itinerary_snapshot,
        )
        validate_restore_preserves_availability_windows(
            current_snapshot=current_revision.itinerary_snapshot,
            target_snapshot=target_revision.itinerary_snapshot,
        )
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
    ) -> tuple[list[TripCandidateRecord], dict[str, str], dict[str, str]]:
        candidate_ids: list[str] = []
        candidate_preferences: dict[str, tuple[str, int]] = {}

        def collect(ids: list[str], field_path: str, authority_rank: int) -> None:
            for candidate_id in ids:
                normalized = str(candidate_id).strip()
                if not normalized:
                    continue
                candidate_ids.append(normalized)
                current = candidate_preferences.get(normalized)
                if current is None or authority_rank >= current[1]:
                    candidate_preferences[normalized] = (field_path, authority_rank)

        # A selected TripCandidate defaults to must-visit. Explicit user overrides
        # outrank an untrusted proposal, which outranks that default.
        collect(list(payload.candidate_ids), "poi.must_candidates", 10)
        if payload.llm_proposal is not None:
            collect(payload.llm_proposal.must_candidate_ids, "poi.must_candidates", 20)
            collect(payload.llm_proposal.optional_candidate_ids, "poi.optional_candidates", 20)
            collect(payload.llm_proposal.avoid_candidate_ids, "poi.avoid_candidates", 20)
        if payload.structured_overrides is not None:
            collect(payload.structured_overrides.must_candidate_ids, "poi.must_candidates", 30)
            collect(payload.structured_overrides.optional_candidate_ids, "poi.optional_candidates", 30)
            collect(payload.structured_overrides.avoid_candidate_ids, "poi.avoid_candidates", 30)

        ordered_ids: list[str] = []
        seen: set[str] = set()
        for candidate_id in candidate_ids:
            normalized = str(candidate_id).strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                ordered_ids.append(normalized)

        if not ordered_ids:
            return [], {}, {}

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
        return candidates, states, {candidate_id: preference[0] for candidate_id, preference in candidate_preferences.items()}

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


def authoritative_safe_replace_envelope(
    *,
    base_snapshot: dict[str, Any],
    envelope: TripMutationCommandEnvelope,
) -> TripMutationCommandEnvelope:
    """Re-read provider identity and route evidence before replace preview."""

    replace_commands = [command for command in envelope.commands if isinstance(command, ReplaceStopCommand)]
    if not replace_commands:
        return envelope
    if len(replace_commands) != 1 or len(envelope.commands) != 1:
        raise MutationCommandFailedError(
            command_index=0,
            reason_code="replace_requires_single_target",
        )

    command = replace_commands[0]
    itinerary = deserialize_itinerary_snapshot(base_snapshot)
    located = find_scheduled_stop(itinerary, command.stop_id)
    if located is None:
        raise MutationCommandFailedError(
            command_index=0,
            reason_code="mutation_command_target_not_found",
        )
    _day, _block, target = located
    if (
        target.is_fixed
        or target.source_type.value not in {"auto_seeded_poi", "auto_seeded_meal", "auto_filled"}
        or target.source_label == "必去"
        or not target.canonical_place_id
        or target.verified_place is None
    ):
        raise MutationCommandFailedError(
            command_index=0,
            reason_code="replace_target_not_eligible",
        )
    if command.replacement.type != target.type.value:
        raise MutationCommandFailedError(
            command_index=0,
            reason_code="replacement_category_mismatch",
        )

    requested_identity = command.replacement.verified_place
    provider = default_poi_discovery_provider()
    try:
        provider_candidates = provider.search_text(
            keyword=requested_identity.canonical_name,
            city=target.city or "",
            offset=20,
        )
    except PoiDiscoveryUnavailable as exc:
        raise MutationCommandFailedError(
            command_index=0,
            reason_code="replacement_provider_unavailable",
        ) from exc
    selected = next(
        (
            candidate
            for candidate in provider_candidates
            if candidate.provider_place_id == requested_identity.provider_place_id
        ),
        None,
    )
    if (
        selected is None
        or not selected.provider_place_id
        or not selected.name
        or selected.latitude is None
        or selected.longitude is None
    ):
        raise MutationCommandFailedError(
            command_index=0,
            reason_code="replacement_identity_not_verified",
        )
    if selected.provider_place_id == target.canonical_place_id:
        raise MutationCommandFailedError(
            command_index=0,
            reason_code="replacement_matches_current_place",
        )
    if not replacement_candidate_category_compatible(target.type, selected):
        raise MutationCommandFailedError(
            command_index=0,
            reason_code="replacement_category_mismatch",
        )

    verified_place = VerifiedPlaceRef(
        stable_id=f"amap:{selected.provider_place_id}",
        original_name=selected.name,
        canonical_name=selected.name,
        provider="amap",
        provider_place_id=selected.provider_place_id,
        latitude=float(selected.latitude),
        longitude=float(selected.longitude),
        category=selected.type,
    )
    route_impact = replacement_route_impact(
        day=located[0],
        target=target,
        candidate_name=verified_place.canonical_name,
        candidate_latitude=verified_place.latitude,
        candidate_longitude=verified_place.longitude,
    )
    if not replacement_route_is_actionable(day=located[0], target=target, impact=route_impact):
        reason_code = {
            "fixed_event_at_risk": "replacement_breaks_fixed_event",
            "route_unavailable": "replacement_route_unavailable",
            "time_slot_conflict": "replacement_breaks_time_slot",
        }.get(route_impact.blocking_reason or "", "replacement_route_unavailable")
        raise MutationCommandFailedError(command_index=0, reason_code=reason_code)

    authoritative_replacement = command.replacement.model_copy(
        update={
            "name": verified_place.canonical_name,
            "verified_place": verified_place,
            "route_impact": route_impact,
        },
        deep=True,
    )
    authoritative_command = command.model_copy(
        update={"replacement": authoritative_replacement},
        deep=True,
    )
    return envelope.model_copy(update={"commands": [authoritative_command]}, deep=True)


def validate_restore_preserves_fixed_items(
    *,
    current_snapshot: dict[str, Any],
    target_snapshot: dict[str, Any],
) -> None:
    current_itinerary = deserialize_itinerary_snapshot(current_snapshot)
    target_itinerary = deserialize_itinerary_snapshot(target_snapshot)
    target_fixed_items = {
        item.stable_id: fixed_item_signature(day.day, block.block_type.value, item)
        for day in target_itinerary.days
        for block in day.blocks
        for item in block.items
        if item.is_fixed and item.stable_id
    }
    protected_items = [
        fixed_item_signature(day.day, block.block_type.value, item)
        for day in current_itinerary.days
        for block in day.blocks
        for item in block.items
        if item.is_fixed
    ]
    if any(
        signature[0] is None or target_fixed_items.get(signature[0]) != signature
        for signature in protected_items
    ):
        raise RestoreWouldDropFixedItemsError(protected_item_count=len(protected_items))


def fixed_item_signature(day: int, block_type: str, item: Any) -> tuple[str | None, int, str, str, str, str]:
    return (
        item.stable_id,
        day,
        block_type,
        item.name,
        item.start_time.isoformat(),
        item.end_time.isoformat(),
    )


def validate_restore_preserves_must_visit_places(
    *,
    current_snapshot: dict[str, Any],
    target_snapshot: dict[str, Any],
) -> None:
    current_itinerary = deserialize_itinerary_snapshot(current_snapshot)
    target_itinerary = deserialize_itinerary_snapshot(target_snapshot)
    target_place_ids = {
        item.canonical_place_id
        for day in target_itinerary.days
        for block in day.blocks
        for item in block.items
        if item.canonical_place_id
    }
    protected_place_ids = [
        item.canonical_place_id
        for day in current_itinerary.days
        for block in day.blocks
        for item in block.items
        if is_must_visit_item(item)
    ]
    if any(place_id is None or place_id not in target_place_ids for place_id in protected_place_ids):
        raise RestoreWouldDropMustVisitPlacesError(protected_item_count=len(protected_place_ids))


def is_must_visit_item(item: Any) -> bool:
    if item.source_label == "必去":
        return True
    provenance = item.candidate_provenance or {}
    field_path = provenance.get("intent_field_path")
    field_prefix = "formal_contract.must_visit_places"
    return isinstance(field_path, str) and (
        field_path == field_prefix
        or field_path.startswith(f"{field_prefix}.")
        or field_path.startswith(f"{field_prefix}[")
    )


def validate_restore_preserves_availability_windows(
    *,
    current_snapshot: dict[str, Any],
    target_snapshot: dict[str, Any],
) -> None:
    current_windows = persisted_availability_window_signatures(current_snapshot)
    if not current_windows:
        return
    target_windows = persisted_availability_window_signatures(target_snapshot)
    missing_windows = current_windows - target_windows
    if missing_windows:
        raise RestoreWouldDropAvailabilityWindowsError(
            protected_window_count=len(missing_windows),
        )


def persisted_availability_window_signatures(snapshot: dict[str, Any]) -> set[tuple[int | None, str | None, str | None]]:
    itinerary = deserialize_itinerary_snapshot(snapshot)
    intent = (
        itinerary.trip_intent.current_intent
        if itinerary.trip_intent is not None
        else itinerary.planning_assumptions.regeneration_intent
        if itinerary.planning_assumptions is not None
        else None
    )
    if intent is None:
        return set()
    return {
        (window.day, window.available_start, window.available_end)
        for window in intent.availability_windows
    }


def serialize_itinerary_snapshot(itinerary: ItineraryResponse) -> dict[str, Any]:
    return itinerary.model_dump(mode="json")


def deserialize_itinerary_snapshot(snapshot: dict[str, Any]) -> ItineraryResponse:
    version = TRIP_SNAPSHOT_SCHEMA_VERSION
    if not version.startswith("1."):
        raise SnapshotSchemaUnsupportedError(version)
    itinerary = ItineraryResponse.model_validate(snapshot)
    # Older persisted snapshots predate per-day execution loads. Rebuild this
    # derived, deterministic view on the server so clients never invent it.
    if itinerary.planner_realism is not None and not itinerary.planner_realism.daily_loads:
        from app.services.planner_realism_analyzer import build_daily_route_loads

        itinerary = itinerary.model_copy(
            update={
                "planner_realism": itinerary.planner_realism.model_copy(
                    update={
                        "daily_loads": build_daily_route_loads(
                            itinerary,
                            itinerary.planner_realism.issues,
                        )
                    }
                )
            }
        )
    return itinerary


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


def _field_updates_from_clarification(
    question: ClarificationQuestion,
    answer: Any,
) -> IntentStructuredOverrides:
    if question.resolution_kind != IntentClarificationResolutionKind.INLINE_ANSWER:
        raise InvalidRevisionOperationError(
            "This clarification does not accept a free-form answer."
        )
    definition = CLARIFICATION_REGISTRY.get(question.reason_code)
    if definition is None:
        raise InvalidRevisionOperationError("Unsupported clarification issue code.")
    return definition.handler(answer)


ClarificationHandler = Callable[[Any], IntentStructuredOverrides]


@dataclass(frozen=True)
class ClarificationDefinition:
    issue_code: str
    impact: str
    response_schema: str
    assumption_allowed: bool
    handler: ClarificationHandler


def _clarify_city(answer: Any) -> IntentStructuredOverrides:
    value = str(answer).strip() if answer is not None else ""
    if not value:
        raise InvalidRevisionOperationError("Clarification answer is required.")
    return IntentStructuredOverrides(city=value)


def _clarify_trip_days(answer: Any) -> IntentStructuredOverrides:
    try:
        value = int(answer)
    except (TypeError, ValueError):
        raise InvalidRevisionOperationError("Trip days clarification must be an integer.") from None
    return IntentStructuredOverrides(trip_days=value)


def _clarify_pace(answer: Any) -> IntentStructuredOverrides:
    value = str(answer).strip()
    if value not in {"relaxed", "balanced", "intensive"}:
        raise InvalidRevisionOperationError("Pace clarification must be relaxed, balanced, or intensive.")
    return IntentStructuredOverrides(pace=value)  # type: ignore[arg-type]


def _clarify_transport(answer: Any) -> IntentStructuredOverrides:
    values = answer if isinstance(answer, list) else [answer]
    normalized = unique_preserve_order([str(value) for value in values])
    if not normalized:
        raise InvalidRevisionOperationError("Transport clarification answer is required.")
    return IntentStructuredOverrides(transport_preferences=normalized)


CLARIFICATION_REGISTRY: dict[str, ClarificationDefinition] = {
    "missing_destination": ClarificationDefinition("missing_destination", "blocking", "string", False, _clarify_city),
    "destination_missing": ClarificationDefinition("destination_missing", "blocking", "string", False, _clarify_city),
    "missing_trip_length": ClarificationDefinition("missing_trip_length", "blocking", "integer", False, _clarify_trip_days),
    "trip_length_missing": ClarificationDefinition("trip_length_missing", "blocking", "integer", False, _clarify_trip_days),
    "transport_preference_conflict": ClarificationDefinition("transport_preference_conflict", "high", "string_list", True, _clarify_transport),
}


def candidate_assumption_codes(candidate) -> list[str]:
    codes: list[str] = []
    if candidate.location_state == "assumed":
        codes.append("LOCATION_ASSUMED")
    if candidate.duration_state == "assumed":
        codes.append("DURATION_ASSUMED")
    return codes
