from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.runtime_config import parse_cors_allow_origins
from app.trips.access import capability_cookie_name
from app.trips.dependencies import get_trip_persistence_service, get_trip_repository
from app.trips.errors import TripError
from app.trips.schemas import (
    ApplyPersistedReplanProposalRequest,
    PersistedCompletionTaskActionRequest,
    PersistedCompletionTaskActionResponse,
    PersistedReplanRequest,
    PersistedReplanPreviewResponse,
    PersistedReplanResponse,
    RestoreRevisionRequest,
    RestoreRevisionResponse,
    TripCurrentResponse,
    TripPlanRequest,
    TripPlanResponse,
    TripRevisionDetailResponse,
    TripRevisionListResponse,
    UndoPersistedMutationRequest,
    UndoPersistedMutationResponse,
)

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("/plan", response_model=TripPlanResponse, status_code=status.HTTP_201_CREATED)
def create_persisted_plan(payload: TripPlanRequest, response: Response) -> TripPlanResponse:
    try:
        result = get_trip_persistence_service().create_persisted_plan(payload)
        set_trip_capability_cookie(response, result.response.trip.id, result.capability)
        return result.response
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}", response_model=TripCurrentResponse)
def get_trip(
    trip_id: str,
    request: Request,
) -> TripCurrentResponse | JSONResponse:
    try:
        return get_trip_persistence_service().get_current_trip(
            trip_id,
            get_trip_capability_from_request(request, trip_id),
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/revisions", response_model=TripRevisionListResponse)
def list_trip_revisions(
    trip_id: str,
    request: Request,
) -> TripRevisionListResponse | JSONResponse:
    try:
        return get_trip_persistence_service().list_revisions(
            trip_id,
            get_trip_capability_from_request(request, trip_id),
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/revisions/{revision_id}", response_model=TripRevisionDetailResponse)
def get_trip_revision(
    trip_id: str,
    revision_id: str,
    request: Request,
) -> TripRevisionDetailResponse | JSONResponse:
    try:
        return get_trip_persistence_service().get_revision_detail(
            trip_id,
            revision_id,
            get_trip_capability_from_request(request, trip_id),
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/completion-task",
    response_model=PersistedCompletionTaskActionResponse,
)
def apply_persisted_completion_task(
    trip_id: str,
    payload: PersistedCompletionTaskActionRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> PersistedCompletionTaskActionResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().apply_completion_task(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/replan/preview",
    response_model=PersistedReplanPreviewResponse,
)
def preview_persisted_replan(
    trip_id: str,
    payload: PersistedReplanRequest,
    request: Request,
) -> PersistedReplanPreviewResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().preview_replan(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/replan/proposals/{proposal_id}/apply",
    response_model=PersistedReplanResponse,
)
def apply_persisted_replan_proposal(
    trip_id: str,
    proposal_id: str,
    payload: ApplyPersistedReplanProposalRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> PersistedReplanResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().apply_replan_proposal(
            trip_id=trip_id,
            proposal_id=proposal_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/revisions/{target_revision_id}/undo",
    response_model=UndoPersistedMutationResponse,
)
def undo_persisted_revision(
    trip_id: str,
    target_revision_id: str,
    payload: UndoPersistedMutationRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> UndoPersistedMutationResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().undo_revision(
            trip_id=trip_id,
            target_revision_id=target_revision_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            base_revision_id=payload.base_revision_id,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/revisions/{target_revision_id}/restore",
    response_model=RestoreRevisionResponse,
)
def restore_trip_revision(
    trip_id: str,
    target_revision_id: str,
    payload: RestoreRevisionRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> RestoreRevisionResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().restore_revision(
            trip_id=trip_id,
            target_revision_id=target_revision_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            base_revision_id=payload.base_revision_id,
        )
    except TripError as exc:
        return trip_error_response(exc)


def trip_error_response(exc: TripError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_error_payload())


def get_trip_capability_from_request(request: Request, trip_id: str) -> str | None:
    return request.cookies.get(capability_cookie_name(trip_id))


def set_trip_capability_cookie(response: Response, trip_id: str, capability: str) -> None:
    secure = os.getenv("TRIP_CAPABILITY_COOKIE_SECURE", "false").strip().lower() == "true"
    response.set_cookie(
        key=capability_cookie_name(trip_id),
        value=capability,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )


def validate_write_origin(request: Request) -> JSONResponse | None:
    origin = request.headers.get("origin")
    if origin is None:
        return None
    allowed = parse_cors_allow_origins(os.getenv("TRIP_ALLOWED_ORIGINS") or os.getenv("CORS_ALLOW_ORIGINS"))
    if "*" in allowed or origin in allowed:
        return None
    return trip_error_response(
        TripError(
            code="trip_access_denied",
            message="Write origin is not allowed.",
            status_code=403,
        )
    )


def persistence_readiness() -> dict:
    return get_trip_repository().health_check()
