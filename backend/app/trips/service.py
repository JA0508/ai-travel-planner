from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from app.api.routes.itinerary import (
    build_itinerary_request_from_parsed_intent,
    build_itinerary_response,
    build_planner_input_snapshot,
    build_planner_result_summary,
    execute_completion_task_action,
    infer_travel_mode_from_text,
)
from app.planner.trace import PlannerTraceCollector, planner_trace_digest
from app.schemas import (
    CompletionTaskActionRequest,
    CompletionTaskActionResponse,
    ItineraryResponse,
    TripIntentEnvelopeSource,
)
from app.services.intent_disambiguation import disambiguate_trip_intent
from app.services.nl_parser import normalize_parsed_trip_intent, parse_trip_text
from app.services.planning_state_transformer import build_planning_input_state
from .access import (
    generate_capability,
    hash_capability,
    hash_idempotency_key,
    verify_capability,
)
from .digests import TRIP_SNAPSHOT_SCHEMA_VERSION, request_digest
from .errors import SnapshotSchemaUnsupportedError, TripAccessDeniedError
from .models import RevisionSourceType
from .repository import TripRepository
from .schemas import (
    PersistedCompletionTaskActionRequest,
    PersistedCompletionTaskActionResponse,
    RestoreRevisionResponse,
    TripCurrentResponse,
    TripMetadata,
    TripPersistenceInfo,
    TripPlanRequest,
    TripPlanResponse,
    TripRevisionDetailResponse,
    TripRevisionListResponse,
    TripRevisionMetadata,
)


class CreatedTripResult:
    def __init__(self, *, response: TripPlanResponse, capability: str) -> None:
        self.response = response
        self.capability = capability


class TripPersistenceService:
    def __init__(self, repository: TripRepository) -> None:
        self.repository = repository

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
